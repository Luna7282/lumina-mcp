import tree_sitter_php as tsphp
from tree_sitter import Node

from lumina_app.extract.extractors.ruby import SimpleClassMethodExtractor
from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode


class PhpExtractor(SimpleClassMethodExtractor):
    language_name = "php"
    class_types = ("class_declaration",)
    function_types = ("method_declaration", "function_definition")

    def get_language_capsule(self):
        return tsphp.language_php()

    def _handle_imports(
        self, root: Node, filepath: str, module_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        for expr in self.find_descendants_by_type(
            root, "require_expression", "require_once_expression", "include_expression", "include_once_expression"
        ):
            strings = self.find_descendants_by_type(expr, "string", "encapsed_string")
            if not strings:
                continue
            path = self.node_text(strings[0], source).strip("'\"")
            import_id = self.make_node_id(filepath, "import", path)
            result.nodes.append(
                SchemaNode(
                    id=import_id, label=path, type="import",
                    source_file=filepath, source_location=self.node_location(expr),
                )
            )
            result.edges.append(
                Edge(source=module_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = path.rsplit("/", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )

        for use in self.find_descendants_by_type(root, "namespace_use_declaration"):
            names = self.find_descendants_by_type(use, "qualified_name", "name")
            if not names:
                continue
            path = self.node_text(names[0], source)
            import_id = self.make_node_id(filepath, "import", path)
            result.nodes.append(
                SchemaNode(
                    id=import_id, label=path, type="import",
                    source_file=filepath, source_location=self.node_location(use),
                )
            )
            result.edges.append(
                Edge(source=module_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = path.rsplit("\\", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )
