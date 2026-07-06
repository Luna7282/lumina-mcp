import tree_sitter_java as tsjava
from tree_sitter import Node

from lumina_app.extract.schema import Edge, ExtractionResult, Node as SchemaNode
from lumina_app.extract.tree_sitter_base import TreeSitterExtractor

_SPRING_ROUTE_ANNOTATIONS = {
    "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping",
}
_SPRING_COMPONENT_ANNOTATIONS = {"Controller", "RestController", "Service", "Repository", "Component"}


class JavaExtractor(TreeSitterExtractor):
    language_name = "java"

    def get_language_capsule(self):
        return tsjava.language()

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language="java")
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
        for child in tree.root_node.children:
            if child.type == "import_declaration":
                self._handle_import(child, filepath, module_id, source, result)
            elif child.type == "class_declaration":
                self._handle_class(child, filepath, module_id, source, result, symbols, [])
            elif child.type == "interface_declaration":
                self._handle_interface(child, filepath, module_id, source, result, symbols)
        return result

    def _annotations_before(self, node: Node) -> list[Node]:
        annotations = []
        sibling = node.prev_sibling
        while sibling is not None and sibling.type in ("marker_annotation", "annotation", "modifiers"):
            if sibling.type == "modifiers":
                annotations.extend(
                    c for c in sibling.children if c.type in ("marker_annotation", "annotation")
                )
                break
            annotations.append(sibling)
            sibling = sibling.prev_sibling
        return annotations

    def _annotation_name(self, node: Node, source: bytes) -> str:
        name_node = node.child_by_field_name("name")
        return self.node_text(name_node, source) if name_node is not None else ""

    def _annotation_path_arg(self, node: Node, source: bytes) -> str | None:
        for child in node.children:
            if child.type == "annotation_argument_list":
                for arg in self.find_descendants_by_type(child, "string_literal"):
                    return self.node_text(arg, source).strip('"')
        return None

    def _handle_import(
        self, node: Node, filepath: str, parent_id: str, source: bytes, result: ExtractionResult
    ) -> None:
        text = self.node_text(node, source)
        path = text.removeprefix("import").strip().rstrip(";").strip()
        import_id = self.make_node_id(filepath, "import", path)
        result.nodes.append(
            SchemaNode(
                id=import_id, label=path, type="import",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=import_id, relation="contains", confidence="EXTRACTED"))
        target_label = path.rsplit(".", 1)[-1]
        result.edges.append(Edge(source=import_id, target=target_label, relation="imports", confidence="EXTRACTED"))

    def _handle_class(
        self,
        node: Node,
        filepath: str,
        parent_id: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
        outer_annotations: list[Node],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        class_id = self.make_node_id(filepath, name)
        symbols[name] = class_id

        annotations = self._annotations_before(node) or outer_annotations
        is_component = any(self._annotation_name(a, source) in _SPRING_COMPONENT_ANNOTATIONS for a in annotations)

        result.nodes.append(
            SchemaNode(
                id=class_id, label=name, type="class",
                source_file=filepath, source_location=self.node_location(node),
                docstring="Spring component" if is_component else "",
            )
        )
        result.edges.append(Edge(source=parent_id, target=class_id, relation="contains", confidence="EXTRACTED"))

        superclass = node.child_by_field_name("superclass")
        if superclass is not None:
            for ident in self.find_descendants_by_type(superclass, "type_identifier"):
                base = self.node_text(ident, source)
                target = symbols.get(base, base)
                confidence = "EXTRACTED" if base in symbols else "INFERRED"
                result.edges.append(Edge(source=class_id, target=target, relation="inherits", confidence=confidence))

        interfaces = node.child_by_field_name("interfaces")
        if interfaces is not None:
            for ident in self.find_descendants_by_type(interfaces, "type_identifier"):
                iface = self.node_text(ident, source)
                target = symbols.get(iface, iface)
                confidence = "EXTRACTED" if iface in symbols else "INFERRED"
                result.edges.append(
                    Edge(source=class_id, target=target, relation="implements", confidence=confidence)
                )

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                if child.type == "method_declaration":
                    self._handle_method(child, filepath, class_id, name, source, result, symbols)

    def _handle_interface(
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
        iface_id = self.make_node_id(filepath, name)
        symbols[name] = iface_id
        result.nodes.append(
            SchemaNode(
                id=iface_id, label=name, type="model",
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=parent_id, target=iface_id, relation="contains", confidence="EXTRACTED"))

    def _handle_method(
        self,
        node: Node,
        filepath: str,
        class_id: str,
        class_name: str,
        source: bytes,
        result: ExtractionResult,
        symbols: dict[str, str],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        method_id = self.make_node_id(filepath, class_name, name)
        symbols[name] = method_id

        annotations = self._annotations_before(node)
        route_path = None
        for annotation in annotations:
            ann_name = self._annotation_name(annotation, source)
            if ann_name in _SPRING_ROUTE_ANNOTATIONS:
                route_path = self._annotation_path_arg(annotation, source) or "/"

        node_type = "route" if route_path else "method"
        result.nodes.append(
            SchemaNode(
                id=method_id, label=route_path if route_path else name, type=node_type,
                source_file=filepath, source_location=self.node_location(node),
            )
        )
        result.edges.append(Edge(source=class_id, target=method_id, relation="contains", confidence="EXTRACTED"))

        body = node.child_by_field_name("body")
        if body is not None:
            for call in self.find_descendants_by_type(body, "method_invocation"):
                name_field = call.child_by_field_name("name")
                if name_field is None:
                    continue
                called = self.node_text(name_field, source)
                if called in symbols:
                    result.edges.append(
                        Edge(source=method_id, target=symbols[called], relation="calls", confidence="EXTRACTED")
                    )
                else:
                    result.edges.append(
                        Edge(source=method_id, target=called, relation="calls", confidence="INFERRED")
                    )
