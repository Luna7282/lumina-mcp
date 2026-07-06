import tree_sitter_go as tsgo
from tree_sitter import Node

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor


class GoExtractor(TreeSitterExtractor):
    language_name = "go"

    def get_language_capsule(self):
        return tsgo.language()

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language="go")
        try:
            tree = self.parse(content)
        except (SyntaxError, ValueError):
            return result

        source = content.encode("utf-8")
        module_id = self.make_node_id(filepath)
        package_name = filepath
        for child in tree.root_node.children:
            if child.type == "package_clause":
                ident = self.find_children_by_type(child, "package_identifier")
                if ident:
                    package_name = self.node_text(ident[0], source)

        result.nodes.append(
            SchemaNode(
                id=module_id,
                label=package_name,
                type="module",
                source_file=filepath,
                source_location=self.node_location(tree.root_node),
            )
        )

        symbols: dict[str, str] = {}
        interfaces: dict[str, list[str]] = {}
        structs: list[str] = []

        for child in tree.root_node.children:
            if child.type == "import_declaration":
                self._handle_import(child, filepath, module_id, source, result)
            elif child.type == "type_declaration":
                self._handle_type(child, filepath, module_id, source, result, symbols, interfaces, structs)

        for child in tree.root_node.children:
            if child.type == "function_declaration":
                self._handle_function(child, filepath, module_id, source, result, symbols)
            elif child.type == "method_declaration":
                self._handle_method(child, filepath, module_id, source, result, symbols)

        # struct "implements" interface (INFERRED) when the struct's method
        # set is a superset of the interface's declared methods.
        struct_methods: dict[str, set[str]] = {s: set() for s in structs}
        for method_name, method_id in symbols.items():
            for struct in structs:
                if method_id.startswith(f"{filepath}::{struct}::"):
                    struct_methods[struct].add(method_name)
        for struct in structs:
            for iface, methods in interfaces.items():
                if methods and set(methods).issubset(struct_methods.get(struct, set())):
                    result.edges.append(
                        Edge(
                            source=self.make_node_id(filepath, struct),
                            target=self.make_node_id(filepath, iface),
                            relation="implements",
                            confidence="INFERRED",
                        )
                    )

        return result

    def _handle_import(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        for spec in self.find_descendants_by_type(node, "import_spec"):
            path_node = spec.child_by_field_name("path")
            if path_node is None:
                continue
            path = self.node_text(path_node, source).strip('"')
            import_id = self.make_node_id(filepath, "import", path)
            result.nodes.append(
                SchemaNode(
                    id=import_id,
                    label=path,
                    type="import",
                    source_file=filepath,
                    source_location=self.node_location(spec),
                )
            )
            result.edges.append(
                Edge(source=parent_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = path.rsplit("/", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )

    def _handle_type(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        interfaces: dict[str, list[str]],
        structs: list[str],
    ) -> None:
        for spec in self.find_children_by_type(node, "type_spec"):
            name_node = spec.child_by_field_name("name")
            type_node = spec.child_by_field_name("type")
            if name_node is None or type_node is None:
                continue
            name = self.node_text(name_node, source)
            node_id = self.make_node_id(filepath, name)
            symbols[name] = node_id

            if type_node.type == "struct_type":
                structs.append(name)
                result.nodes.append(
                    SchemaNode(
                        id=node_id, label=name, type="class",
                        source_file=filepath, source_location=self.node_location(spec),
                    )
                )
            elif type_node.type == "interface_type":
                methods = [
                    self.node_text(m.child_by_field_name("name"), source)
                    for m in self.find_children_by_type(type_node, "method_elem")
                    if m.child_by_field_name("name") is not None
                ]
                interfaces[name] = methods
                result.nodes.append(
                    SchemaNode(
                        id=node_id, label=name, type="model",
                        source_file=filepath, source_location=self.node_location(spec),
                    )
                )
            else:
                result.nodes.append(
                    SchemaNode(
                        id=node_id, label=name, type="class",
                        source_file=filepath, source_location=self.node_location(spec),
                    )
                )
            result.edges.append(
                Edge(source=parent_id, target=node_id, relation="contains", confidence="EXTRACTED")
            )

    def _handle_function(
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
        func_id = self.make_node_id(filepath, name)
        symbols[name] = func_id
        result.nodes.append(
            SchemaNode(
                id=func_id, label=name, type="function",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=func_id, relation="contains", confidence="EXTRACTED"))
        body = node.child_by_field_name("body")
        if body is not None:
            self._handle_calls(body, func_id, source, result, symbols)

    def _handle_method(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
    ) -> None:
        name_node = node.child_by_field_name("name")
        receiver = node.child_by_field_name("receiver")
        if name_node is None or receiver is None:
            return
        method_name = self.node_text(name_node, source)
        receiver_types = self.find_descendants_by_type(receiver, "type_identifier")
        receiver_type = self.node_text(receiver_types[0], source) if receiver_types else None

        parts = [receiver_type, method_name] if receiver_type else [method_name]
        method_id = self.make_node_id(filepath, *parts)
        symbols[method_name] = method_id
        result.nodes.append(
            SchemaNode(
                id=method_id, label=method_name, type="method",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        struct_id = self.make_node_id(filepath, receiver_type) if receiver_type else parent_id
        result.edges.append(Edge(source=struct_id, target=method_id, relation="contains", confidence="EXTRACTED"))
        body = node.child_by_field_name("body")
        if body is not None:
            self._handle_calls(body, method_id, source, result, symbols)

    def _handle_calls(
        self, body: Node, caller_id: str, source: bytes, result: ExtractionResult, symbols: dict[str, str]
    ) -> None:
        for call in self.find_descendants_by_type(body, "call_expression"):
            func = call.child_by_field_name("function")
            if func is None:
                continue
            if func.type == "identifier":
                name = self.node_text(func, source)
            elif func.type == "selector_expression":
                field = func.child_by_field_name("field")
                name = self.node_text(field, source) if field is not None else self.node_text(func, source)
            else:
                continue
            if name in symbols:
                result.edges.append(
                    Edge(source=caller_id, target=symbols[name], relation="calls", confidence="EXTRACTED")
                )
            else:
                result.edges.append(Edge(source=caller_id, target=name, relation="calls", confidence="INFERRED"))
