import tree_sitter_python as tspython
from tree_sitter import Node

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor

_MODEL_BASE_NAMES = {"Base", "DeclarativeBase", "BaseModel"}
_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


class PythonExtractor(TreeSitterExtractor):
    language_name = "python"

    def get_language_capsule(self):
        return tspython.language()

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language="python")
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

        # Same-file symbol table for EXTRACTED call/inherit resolution.
        symbols: dict[str, str] = {}

        self._walk_body(tree.root_node, filepath, module_id, source, result, symbols, class_name=None)
        return result

    def _docstring(self, body: Node, source: bytes) -> str:
        for child in body.children:
            if child.type == "expression_statement" and child.children:
                expr = child.children[0]
                if expr.type == "string":
                    text = self.node_text(expr, source)
                    return text.strip("\"'").strip()
            if child.type not in ("comment",):
                break
        return ""

    def _unwrap_decorated(self, node: Node) -> tuple[Node, list[Node]]:
        """Given a decorated_definition, return (inner def node, decorators)."""
        decorators = self.find_children_by_type(node, "decorator")
        inner = None
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                inner = child
                break
        return inner or node, decorators

    def _decorator_call_name(self, decorator: Node, source: bytes) -> str | None:
        # decorator -> '@' + (call | attribute | identifier)
        target = None
        for child in decorator.children:
            if child.type in ("call", "attribute", "identifier"):
                target = child
                break
        if target is None:
            return None
        if target.type == "call":
            func = target.child_by_field_name("function")
            return self.node_text(func, source) if func else None
        return self.node_text(target, source)

    def _decorator_route_path(self, decorator: Node, source: bytes) -> str | None:
        for child in decorator.children:
            if child.type == "call":
                args = child.child_by_field_name("arguments")
                if args:
                    for arg in args.children:
                        if arg.type == "string":
                            return self.node_text(arg, source).strip("\"'")
        return None

    def _is_route_decorator(self, name: str) -> bool:
        if "." not in name:
            return False
        method = name.rsplit(".", 1)[-1]
        return method in _ROUTE_METHODS

    def _walk_body(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_name: str | None,
    ) -> None:
        body = node.child_by_field_name("body") if node.type in ("module", "class_definition") else node
        children = body.children if body is not None else node.children

        for child in children:
            if child.type == "class_definition":
                self._handle_class(child, filepath, parent_id, source, result, symbols)
            elif child.type == "function_definition":
                self._handle_function(child, filepath, parent_id, source, result, symbols, class_name, [])
            elif child.type == "decorated_definition":
                inner, decorators = self._unwrap_decorated(child)
                if inner.type == "class_definition":
                    self._handle_class(inner, filepath, parent_id, source, result, symbols)
                elif inner.type == "function_definition":
                    self._handle_function(
                        inner, filepath, parent_id, source, result, symbols, class_name, decorators
                    )
            elif child.type in ("import_statement", "import_from_statement"):
                self._handle_import(child, filepath, parent_id, source, result)

    def _handle_class(
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
        class_name = self.node_text(name_node, source)
        class_id = self.make_node_id(filepath, class_name)
        symbols[class_name] = class_id

        base_names: list[str] = []
        superclasses = node.child_by_field_name("superclasses")
        if superclasses is not None:
            for child in superclasses.children:
                if child.type == "identifier":
                    base_names.append(self.node_text(child, source))
                elif child.type == "keyword_argument":
                    continue

        node_type = "model" if _MODEL_BASE_NAMES.intersection(base_names) else "class"
        body = node.child_by_field_name("body")
        docstring = self._docstring(body, source) if body else ""

        result.nodes.append(
            SchemaNode(
                id=class_id,
                label=class_name,
                type=node_type,
                source_file=filepath,
                source_location=self.node_location(node),
                docstring=docstring,
            )
        )
        result.edges.append(Edge(source=parent_id, target=class_id, relation="contains", confidence="EXTRACTED"))

        for base in base_names:
            if base in _MODEL_BASE_NAMES:
                continue
            target = symbols.get(base, base)
            confidence = "EXTRACTED" if base in symbols else "INFERRED"
            result.edges.append(
                Edge(source=class_id, target=target, relation="inherits", confidence=confidence)
            )

        if body is not None:
            self._walk_body(node, filepath, class_id, source, result, symbols, class_name=class_name)

    def _handle_function(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        class_name: str | None,
        decorators: list[Node],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        func_name = self.node_text(name_node, source)
        is_method = class_name is not None
        parts = [class_name, func_name] if is_method else [func_name]
        func_id = self.make_node_id(filepath, *parts)
        symbols[func_name] = func_id
        if is_method:
            symbols[f"self.{func_name}"] = func_id

        node_type = "method" if is_method else "function"
        route_path = None
        for decorator in decorators:
            deco_name = self._decorator_call_name(decorator, source)
            if deco_name and self._is_route_decorator(deco_name):
                route_path = self._decorator_route_path(decorator, source) or "/"
                node_type = "route"

        body = node.child_by_field_name("body")
        docstring = self._docstring(body, source) if body else ""

        result.nodes.append(
            SchemaNode(
                id=func_id,
                label=route_path if route_path is not None else func_name,
                type=node_type,
                source_file=filepath,
                source_location=self.node_location(node),
                docstring=docstring,
            )
        )
        result.edges.append(Edge(source=parent_id, target=func_id, relation="contains", confidence="EXTRACTED"))

        if body is not None:
            for call in self.find_descendants_by_type(body, "call"):
                self._handle_call(call, func_id, source, result, symbols)

    def _handle_call(
        self, call: Node, caller_id: str, source: bytes, result: ExtractionResult, symbols: dict[str, str]
    ) -> None:
        func = call.child_by_field_name("function")
        if func is None:
            return
        called_name: str | None = None
        if func.type == "identifier":
            called_name = self.node_text(func, source)
        elif func.type == "attribute":
            full = self.node_text(func, source)
            called_name = full
        if not called_name:
            return

        if called_name in symbols:
            result.edges.append(
                Edge(source=caller_id, target=symbols[called_name], relation="calls", confidence="EXTRACTED")
            )
        else:
            bare = called_name.rsplit(".", 1)[-1]
            result.edges.append(Edge(source=caller_id, target=bare, relation="calls", confidence="INFERRED"))

    def _handle_import(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        names: list[str] = []
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    names.append(self.node_text(child, source))
                elif child.type == "aliased_import":
                    dotted = self.find_children_by_type(child, "dotted_name")
                    if dotted:
                        names.append(self.node_text(dotted[0], source))
        else:  # import_from_statement
            module_node = node.child_by_field_name("module_name")
            module_name = self.node_text(module_node, source) if module_node else ""
            for child in node.children:
                if child.type == "dotted_name" and child != module_node:
                    names.append(self.node_text(child, source))
                elif child.type == "aliased_import":
                    dotted = self.find_children_by_type(child, "dotted_name")
                    if dotted:
                        names.append(self.node_text(dotted[0], source))
                elif child.type == "wildcard_import":
                    names.append(f"{module_name}.*")
            if not names and module_name:
                names.append(module_name)

        for name in names:
            import_id = self.make_node_id(filepath, "import", name)
            result.nodes.append(
                SchemaNode(
                    id=import_id,
                    label=name,
                    type="import",
                    source_file=filepath,
                    source_location=self.node_location(node),
                )
            )
            result.edges.append(
                Edge(source=parent_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = name.rsplit(".", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )
