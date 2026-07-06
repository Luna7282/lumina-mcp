import tree_sitter_scala as tsscala
from tree_sitter import Node

from lumina_app.extract.extractors.ruby import SimpleClassMethodExtractor
from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode


class ScalaExtractor(SimpleClassMethodExtractor):
    language_name = "scala"
    class_types = ("class_definition",)
    function_types = ("function_definition",)

    def get_language_capsule(self):
        return tsscala.language()

    def _handle_imports(
        self, root: Node, filepath: str, module_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        for imp in self.find_descendants_by_type(root, "import_declaration"):
            idents = self.find_descendants_by_type(imp, "identifier")
            if not idents:
                continue
            path = ".".join(self.node_text(i, source) for i in idents)
            import_id = self.make_node_id(filepath, "import", path)
            result.nodes.append(
                SchemaNode(
                    id=import_id, label=path, type="import",
                    source_file=filepath, source_location=self.node_location(imp),
                )
            )
            result.edges.append(
                Edge(source=module_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = path.rsplit(".", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )
