import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
from tree_sitter import Node

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor


class CCppExtractor(TreeSitterExtractor):
    """Shared extractor for C and C++ — pass lang='c' or lang='cpp'."""

    def __init__(self, lang: str = "c") -> None:
        self.lang = lang
        self.language_name = "cpp" if lang == "cpp" else "c"

    def get_language_capsule(self):
        return tscpp.language() if self.lang == "cpp" else tsc.language()

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language=self.language_name)
        try:
            tree = self.parse(content)
        except (SyntaxError, ValueError):
            return result

        source = content.encode("utf-8")
        module_id = self.make_node_id(filepath)
        result.nodes.append(
            SchemaNode(
                id=module_id, label=filepath, type="module",
                source_file=filepath, source_location=self.node_location(tree.root_node),
            )
        )

        symbols: dict[str, str] = {}
        self._walk(tree.root_node.children, filepath, module_id, source, result, symbols)
        return result

    def _function_name(self, node: Node, source: bytes) -> str | None:
        declarator = node.child_by_field_name("declarator")
        while declarator is not None and declarator.type not in ("identifier", "field_identifier"):
            inner = declarator.child_by_field_name("declarator")
            if inner is None:
                return None
            declarator = inner
        return self.node_text(declarator, source) if declarator is not None else None

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
            if kind == "preproc_include":
                self._handle_include(node, filepath, parent_id, source, result)
            elif kind in ("struct_specifier", "class_specifier"):
                self._handle_struct_or_class(node, filepath, parent_id, source, result, symbols)
            elif kind == "namespace_definition":
                self._handle_namespace(node, filepath, parent_id, source, result, symbols)
            elif kind == "function_definition":
                self._handle_function(node, filepath, parent_id, source, result, symbols, None)
            elif kind == "declaration" and self.find_children_by_type(node, "struct_specifier", "class_specifier"):
                for inner in self.find_children_by_type(node, "struct_specifier", "class_specifier"):
                    self._handle_struct_or_class(inner, filepath, parent_id, source, result, symbols)

    def _handle_include(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        path_node = self.find_children_by_type(node, "string_literal", "system_lib_string")
        if not path_node:
            return
        path = self.node_text(path_node[0], source).strip('"<>')
        import_id = self.make_node_id(filepath, "import", path)
        result.nodes.append(
            SchemaNode(
                id=import_id, label=path, type="import",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=import_id, relation="contains", confidence="EXTRACTED"))
        target_label = path.rsplit("/", 1)[-1]
        result.edges.append(Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED"))

    def _handle_namespace(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
    ) -> None:
        name_node = self.find_children_by_type(node, "namespace_identifier")
        name = self.node_text(name_node[0], source) if name_node else "anonymous"
        ns_id = self.make_node_id(filepath, name)
        result.nodes.append(
            SchemaNode(
                id=ns_id, label=name, type="module",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=ns_id, relation="contains", confidence="EXTRACTED"))
        body = self.find_children_by_type(node, "declaration_list")
        if body:
            self._walk(body[0].children, filepath, ns_id, source, result, symbols)

    def _handle_struct_or_class(
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
        class_id = self.make_node_id(filepath, name)
        symbols[name] = class_id
        result.nodes.append(
            SchemaNode(
                id=class_id, label=name, type="class",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=class_id, relation="contains", confidence="EXTRACTED"))

        base_clause = self.find_children_by_type(node, "base_class_clause")
        if base_clause:
            for ident in self.find_descendants_by_type(base_clause[0], "type_identifier"):
                base = self.node_text(ident, source)
                target = symbols.get(base, base)
                confidence = "EXTRACTED" if base in symbols else "INFERRED"
                result.edges.append(Edge(source=class_id, target=target, relation="inherits", confidence=confidence))

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                if child.type == "function_definition":
                    self._handle_function(child, filepath, class_id, source, result, symbols, name)
                elif child.type == "field_declaration_list":
                    for inner in child.children:
                        if inner.type == "function_definition":
                            self._handle_function(inner, filepath, class_id, source, result, symbols, name)

    def _handle_function(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        owner: str | None,
    ) -> None:
        name = self._function_name(node, source)
        if name is None:
            return
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
                    called = self.node_text(field, source) if field is not None else None
                else:
                    called = None
                if not called:
                    continue
                if called in symbols:
                    result.edges.append(
                        Edge(source=func_id, target=symbols[called], relation="calls", confidence="EXTRACTED")
                    )
                else:
                    result.edges.append(
                        Edge(source=func_id, target=called, relation="calls", confidence="INFERRED")
                    )
