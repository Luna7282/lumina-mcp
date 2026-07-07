from pathlib import PurePosixPath

import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor

_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "use"}


class JSFamilyExtractor(TreeSitterExtractor):
    """Shared extraction logic for the TypeScript/JavaScript grammar family."""

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language=self.language_name)
        try:
            tree = self.parse_for(filepath, content)
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
        # class_name -> {method_name: method_node_id}, pre-populated per class
        # so `this.method()` calls resolve even when the call appears before
        # the method's own definition in source order.
        class_methods: dict[str, dict[str, str]] = {}
        self._walk_children(
            tree.root_node.children, filepath, module_id, source, result, symbols, None, class_methods
        )
        return result

    def parse_for(self, filepath: str, content: str):
        """Default: use this extractor's single grammar. Overridden by
        TypeScriptExtractor, which picks TS vs TSX grammar per file."""
        return self.parse(content)

    def _unwrap_export(self, node: Node) -> list[Node]:
        if node.type != "export_statement":
            return [node]
        return [c for c in node.named_children if c.type != "string"]

    def _walk_children(
        self,
        nodes: list[Node],
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_name: str | None,
        class_methods: dict[str, dict[str, str]],
    ) -> None:
        for raw in nodes:
            for node in self._unwrap_export(raw):
                self._handle_node(node, filepath, parent_id, source, result, symbols, class_name, class_methods)

    def _handle_node(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_name: str | None,
        class_methods: dict[str, dict[str, str]],
    ) -> None:
        kind = node.type
        if kind == "class_declaration":
            self._handle_class(node, filepath, parent_id, source, result, symbols, class_methods)
        elif kind in ("function_declaration", "method_definition"):
            self._handle_function(node, filepath, parent_id, source, result, symbols, class_name, class_methods)
        elif kind == "lexical_declaration" or kind == "variable_declaration":
            for declarator in node.named_children:
                if declarator.type != "variable_declarator":
                    continue
                value = declarator.child_by_field_name("value")
                name_node = declarator.child_by_field_name("name")
                if value is not None and value.type == "arrow_function" and name_node is not None:
                    self._handle_function(
                        value, filepath, parent_id, source, result, symbols, class_name, class_methods,
                        override_name=self.node_text(name_node, source),
                    )
                    self._handle_route_call(value, filepath, parent_id, source, result)
                if value is not None:
                    self._handle_route_call(value, filepath, parent_id, source, result)
        elif kind == "interface_declaration":
            self._handle_model(node, filepath, parent_id, source, result, "interface")
        elif kind == "type_alias_declaration":
            self._handle_model(node, filepath, parent_id, source, result, "type_alias")
        elif kind in ("import_statement",):
            self._handle_import(node, filepath, parent_id, source, result)
        elif kind == "expression_statement":
            for child in node.children:
                self._handle_route_call(child, filepath, parent_id, source, result)

    def _generic_suffix(self, node: Node, source: bytes) -> str:
        type_params = node.child_by_field_name("type_parameters")
        return self.node_text(type_params, source) if type_params is not None else ""

    def _handle_class(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_methods: dict[str, dict[str, str]],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        class_name = self.node_text(name_node, source)
        class_id = self.make_node_id(filepath, class_name)
        symbols[class_name] = class_id
        label = class_name + self._generic_suffix(node, source)

        result.nodes.append(
            SchemaNode(
                id=class_id,
                label=label,
                type="class",
                source_file=filepath,
                source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=class_id, relation="contains", confidence="EXTRACTED"))

        heritage = self.find_children_by_type(node, "class_heritage")
        for h in heritage:
            for extends_clause in self.find_children_by_type(h, "extends_clause"):
                for ident in self.find_children_by_type(extends_clause, "identifier"):
                    base = self.node_text(ident, source)
                    target = symbols.get(base, base)
                    confidence = "EXTRACTED" if base in symbols else "INFERRED"
                    result.edges.append(
                        Edge(source=class_id, target=target, relation="inherits", confidence=confidence)
                    )
            for impl_clause in self.find_children_by_type(h, "implements_clause"):
                for ident in self.find_children_by_type(impl_clause, "type_identifier", "identifier"):
                    base = self.node_text(ident, source)
                    result.edges.append(
                        Edge(source=class_id, target=base, relation="implements", confidence="INFERRED")
                    )

        body = node.child_by_field_name("body")
        if body is not None:
            # Pre-register this class's own methods so a `this.x()` call
            # resolves EXTRACTED even when it appears before `x` is defined.
            methods_for_class: dict[str, str] = {}
            for child in body.children:
                if child.type == "method_definition":
                    method_name_node = child.child_by_field_name("name")
                    if method_name_node is not None:
                        method_name = self.node_text(method_name_node, source)
                        methods_for_class[method_name] = self.make_node_id(filepath, class_name, method_name)
            class_methods[class_name] = methods_for_class

            self._walk_children(
                body.children, filepath, class_id, source, result, symbols, class_name, class_methods
            )

    def _handle_model(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        _kind: str,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        node_id = self.make_node_id(filepath, name)
        result.nodes.append(
            SchemaNode(
                id=node_id,
                label=name + self._generic_suffix(node, source),
                type="model",
                source_file=filepath,
                source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=node_id, relation="contains", confidence="EXTRACTED"))

    def _returns_jsx(self, node: Node) -> bool:
        if node.type in ("jsx_element", "jsx_self_closing_element", "jsx_fragment"):
            return True
        if node.type == "return_statement":
            return any(self._returns_jsx(c) for c in node.children)
        if node.type in ("statement_block", "parenthesized_expression"):
            return any(self._returns_jsx(c) for c in node.children)
        if node.type == "arrow_function":
            body = node.child_by_field_name("body")
            return body is not None and self._returns_jsx(body)
        return False

    def _handle_function(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_name: str | None,
        class_methods: dict[str, dict[str, str]],
        override_name: str | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        func_name = override_name or (self.node_text(name_node, source) if name_node else None)
        if func_name is None:
            return

        is_method = class_name is not None and node.type == "method_definition"
        parts = [class_name, func_name] if is_method else [func_name]
        func_id = self.make_node_id(filepath, *parts)
        symbols[func_name] = func_id
        node_type = "method" if is_method else "function"

        label = func_name
        body = node.child_by_field_name("body")
        if body is not None and self._returns_jsx(body):
            label = f"{func_name} (Component)"

        result.nodes.append(
            SchemaNode(
                id=func_id,
                label=label,
                type=node_type,
                source_file=filepath,
                source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=func_id, relation="contains", confidence="EXTRACTED"))

        if body is not None:
            for call in self.find_descendants_by_type(body, "call_expression"):
                self._handle_call(call, func_id, source, result, symbols, class_name, class_methods)

    def _handle_call(
        self,
        call: Node,
        caller_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_name: str | None,
        class_methods: dict[str, dict[str, str]],
    ) -> None:
        func = call.child_by_field_name("function")
        if func is None:
            return
        if func.type == "identifier":
            called_name = self.node_text(func, source)
        elif func.type == "member_expression":
            obj = func.child_by_field_name("object")
            prop = func.child_by_field_name("property")
            if obj is not None and obj.type == "this" and prop is not None:
                method_name = self.node_text(prop, source)
                target_id = class_methods.get(class_name, {}).get(method_name) if class_name else None
                if target_id:
                    result.edges.append(
                        Edge(source=caller_id, target=target_id, relation="calls", confidence="EXTRACTED")
                    )
                else:
                    result.edges.append(
                        Edge(source=caller_id, target=method_name, relation="calls", confidence="INFERRED")
                    )
                return
            called_name = self.node_text(func, source)
        else:
            return

        if called_name in symbols:
            result.edges.append(
                Edge(source=caller_id, target=symbols[called_name], relation="calls", confidence="EXTRACTED")
            )
        else:
            bare = called_name.rsplit(".", 1)[-1]
            result.edges.append(Edge(source=caller_id, target=bare, relation="calls", confidence="INFERRED"))

    def _handle_route_call(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        if node.type != "call_expression":
            return
        func = node.child_by_field_name("function")
        if func is None or func.type != "member_expression":
            return
        obj = func.child_by_field_name("object")
        prop = func.child_by_field_name("property")
        if obj is None or prop is None:
            return
        method = self.node_text(prop, source)
        if method not in _ROUTE_METHODS:
            return
        args = node.child_by_field_name("arguments")
        path = "/"
        if args is not None:
            for arg in args.children:
                if arg.type == "string":
                    path = self.node_text(arg, source).strip("'\"`")
                    break
        route_id = self.make_node_id(filepath, "route", f"{self.node_text(obj, source)}.{method}", path)
        result.nodes.append(
            SchemaNode(
                id=route_id,
                label=path,
                type="route",
                source_file=filepath,
                source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=route_id, relation="contains", confidence="EXTRACTED"))

    def _handle_import(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        source_path = None
        for child in node.children:
            if child.type == "string":
                source_path = self.node_text(child, source).strip("'\"`")
        if source_path is None:
            return
        import_id = self.make_node_id(filepath, "import", source_path)
        result.nodes.append(
            SchemaNode(
                id=import_id,
                label=source_path,
                type="import",
                source_file=filepath,
                source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=import_id, relation="contains", confidence="EXTRACTED"))
        target_label = source_path.rsplit("/", 1)[-1]
        result.edges.append(
            Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
        )


_TS_VARIANT_PARSERS: dict[str, Parser] = {}


class TypeScriptExtractor(JSFamilyExtractor):
    """Handles both .ts (plain TypeScript grammar) and .tsx (JSX-aware
    grammar) — detect.py maps both extensions to the single "typescript"
    language key, so the grammar variant is chosen here per-file."""

    language_name = "typescript"

    def get_language_capsule(self):
        return tstypescript.language_typescript()

    def parse_for(self, filepath: str, content: str):
        is_tsx = PurePosixPath(filepath.replace("\\", "/")).suffix.lower() == ".tsx"
        variant = "tsx" if is_tsx else "ts"
        if variant not in _TS_VARIANT_PARSERS:
            capsule = tstypescript.language_tsx() if is_tsx else tstypescript.language_typescript()
            _TS_VARIANT_PARSERS[variant] = Parser(Language(capsule))
        return _TS_VARIANT_PARSERS[variant].parse(content.encode("utf-8"))
