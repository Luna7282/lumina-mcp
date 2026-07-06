import tree_sitter_ruby as tsruby
from tree_sitter import Node

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor


class SimpleClassMethodExtractor(TreeSitterExtractor):
    """Shared skeleton for the 'secondary tier' languages: real tree-sitter
    parsing, but only class/method/function extraction (no call graph or
    inheritance resolution) — subclasses configure the node type names for
    their grammar and override _handle_imports for their import syntax."""

    class_types: tuple[str, ...] = ()
    function_types: tuple[str, ...] = ()

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
        self._walk(tree.root_node.children, filepath, module_id, source, result, None)
        self._handle_imports(tree.root_node, filepath, module_id, source, result)
        return result

    def _walk(
        self,
        nodes: list[Node],
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        owner: str | None,
    ) -> None:
        for node in nodes:
            if node.type in self.class_types:
                self._handle_class(node, filepath, parent_id, source, result)
            elif node.type in self.function_types:
                self._handle_function(node, filepath, parent_id, source, result, owner)
            else:
                self._walk(node.children, filepath, parent_id, source, result, owner)

    def _handle_class(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        class_id = self.make_node_id(filepath, name)
        result.nodes.append(
            SchemaNode(
                id=class_id, label=name, type="class",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=class_id, relation="contains", confidence="EXTRACTED"))
        self._walk(node.children, filepath, class_id, source, result, name)

    def _handle_function(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        owner: str | None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        parts = [owner, name] if owner else [name]
        func_id = self.make_node_id(filepath, *parts)
        result.nodes.append(
            SchemaNode(
                id=func_id, label=name, type="method" if owner else "function",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=func_id, relation="contains", confidence="EXTRACTED"))

    def _handle_imports(
        self, root: Node, filepath: str, module_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        """Override per-language."""


class RubyExtractor(SimpleClassMethodExtractor):
    language_name = "ruby"
    class_types = ("class",)
    function_types = ("method",)

    def get_language_capsule(self):
        return tsruby.language()

    def _handle_imports(
        self, root: Node, filepath: str, module_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        for call in self.find_descendants_by_type(root, "call"):
            method = call.child_by_field_name("method")
            if method is None or self.node_text(method, source) not in ("require", "require_relative"):
                continue
            args = call.child_by_field_name("arguments")
            if args is None:
                continue
            strings = self.find_descendants_by_type(args, "string")
            if not strings:
                continue
            path = self.node_text(strings[0], source).strip("'\"")
            import_id = self.make_node_id(filepath, "import", path)
            result.nodes.append(
                SchemaNode(
                    id=import_id, label=path, type="import",
                    source_file=filepath, source_location=self.node_location(call),
                )
            )
            result.edges.append(
                Edge(source=module_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = path.rsplit("/", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )
