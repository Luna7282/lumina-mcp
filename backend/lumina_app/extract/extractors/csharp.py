import tree_sitter_c_sharp as tscsharp
from tree_sitter import Node

from lumina_app.extract.extractors.ruby import SimpleClassMethodExtractor
from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode


class CSharpExtractor(SimpleClassMethodExtractor):
    language_name = "csharp"
    class_types = ("class_declaration",)
    function_types = ("method_declaration",)

    def get_language_capsule(self):
        return tscsharp.language()

    def _handle_imports(
        self, root: Node, filepath: str, module_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        for using in self.find_descendants_by_type(root, "using_directive"):
            idents = self.find_descendants_by_type(using, "identifier", "qualified_name")
            if not idents:
                continue
            path = self.node_text(idents[0], source)
            import_id = self.make_node_id(filepath, "import", path)
            result.nodes.append(
                SchemaNode(
                    id=import_id, label=path, type="import",
                    source_file=filepath, source_location=self.node_location(using),
                )
            )
            result.edges.append(
                Edge(source=module_id, target=import_id, relation="contains", confidence="EXTRACTED")
            )
            target_label = path.rsplit(".", 1)[-1]
            result.edges.append(
                Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED")
            )
