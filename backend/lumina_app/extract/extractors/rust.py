import tree_sitter_rust as tsrust
from tree_sitter import Node

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor


class RustExtractor(TreeSitterExtractor):
    language_name = "rust"

    def get_language_capsule(self):
        return tsrust.language()

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language="rust")
        try:
            tree = self.parse(content)
        except (SyntaxError, ValueError):
            return result

        source = content.encode("utf-8")
        module_id = self.make_node_id(filepath)
        result.nodes.append(
            SchemaNode(
                id=module_id,
                label=filepath,
                type="module",
                source_file=filepath,
                source_location=self.node_location(tree.root_node),
            )
        )

        symbols: dict[str, str] = {}
        self._walk(tree.root_node.children, filepath, module_id, source, result, symbols)
        return result

    def _walk(
        self,
        nodes: list[Node],
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
    ) -> None:
        for node in nodes:
            kind = node.type
            if kind == "mod_item":
                self._handle_mod(node, filepath, parent_id, source, result, symbols)
            elif kind == "struct_item":
                self._handle_named(node, filepath, parent_id, source, result, symbols, "class", "")
            elif kind == "enum_item":
                self._handle_named(node, filepath, parent_id, source, result, symbols, "class", "enum")
            elif kind == "trait_item":
                self._handle_named(node, filepath, parent_id, source, result, symbols, "model", "")
            elif kind == "impl_item":
                self._handle_impl(node, filepath, parent_id, source, result, symbols)
            elif kind == "fn_item" or kind == "function_item":
                self._handle_fn(node, filepath, parent_id, source, result, symbols, None)
            elif kind == "use_declaration":
                self._handle_use(node, filepath, parent_id, source, result)

    def _handle_mod(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        mod_id = self.make_node_id(filepath, name)
        result.nodes.append(
            SchemaNode(
                id=mod_id, label=name, type="module",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=mod_id, relation="contains", confidence="EXTRACTED"))
        body = node.child_by_field_name("body")
        if body is not None:
            self._walk(body.children, filepath, mod_id, source, result, symbols)

    def _handle_named(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        node_type: str,
        docstring: str,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        node_id = self.make_node_id(filepath, name)
        symbols[name] = node_id
        result.nodes.append(
            SchemaNode(
                id=node_id, label=name, type=node_type,
                source_file=filepath, source_location=self.node_location(node), docstring=docstring,
            )
        )
        result.edges.append(Edge(source=parent_id, target=node_id, relation="contains", confidence="EXTRACTED"))

    def _handle_impl(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
    ) -> None:
        trait_node = node.child_by_field_name("trait")
        type_node = node.child_by_field_name("type")
        struct_name = self.node_text(type_node, source) if type_node is not None else None
        struct_id = symbols.get(struct_name, self.make_node_id(filepath, struct_name)) if struct_name else parent_id

        if trait_node is not None and struct_name is not None:
            trait_name = self.node_text(trait_node, source)
            trait_id = symbols.get(trait_name, trait_name)
            result.edges.append(
                Edge(source=struct_id, target=trait_id, relation="implements", confidence="EXTRACTED")
            )

        body = node.child_by_field_name("body")
        if body is None:
            return
        for child in body.children:
            if child.type in ("function_item", "fn_item"):
                self._handle_fn(child, filepath, struct_id, source, result, symbols, struct_name)

    def _handle_fn(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        owner: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        parts = [owner, name] if owner else [name]
        func_id = self.make_node_id(filepath, *parts)
        symbols[name] = func_id
        result.nodes.append(
            SchemaNode(
                id=func_id, label=name, type="method" if owner else "function",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=func_id, relation="contains", confidence="EXTRACTED"))
        body = node.child_by_field_name("body")
        if body is not None:
            for call in self.find_descendants_by_type(body, "call_expression"):
                func = call.child_by_field_name("function")
                if func is None:
                    continue
                if func.type == "identifier":
                    called = self.node_text(func, source)
                elif func.type == "field_expression":
                    field = func.child_by_field_name("field")
                    called = self.node_text(field, source) if field is not None else self.node_text(func, source)
                else:
                    continue
                if called in symbols:
                    result.edges.append(
                        Edge(source=func_id, target=symbols[called], relation="calls", confidence="EXTRACTED")
                    )
                else:
                    result.edges.append(
                        Edge(source=func_id, target=called, relation="calls", confidence="INFERRED")
                    )

    def _handle_use(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        arg = node.child_by_field_name("argument")
        if arg is None:
            return
        path = self.node_text(arg, source)
        import_id = self.make_node_id(filepath, "import", path)
        result.nodes.append(
            SchemaNode(
                id=import_id, label=path, type="import",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=import_id, relation="contains", confidence="EXTRACTED"))
        target_label = path.rsplit("::", 1)[-1]
        result.edges.append(Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED"))
