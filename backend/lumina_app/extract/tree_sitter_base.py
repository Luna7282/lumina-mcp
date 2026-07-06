from tree_sitter import Language, Node, Parser

from lumina_app.extract.schema import ExtractionResult

_PARSER_CACHE: dict[str, Parser] = {}


class TreeSitterExtractor:
    """Base class for all tree-sitter language extractors."""

    language_name: str = "unknown"

    def get_language_capsule(self):
        """Return the raw PyCapsule/object from the tree-sitter language
        binding. Override in subclasses — the exact factory function name
        differs per grammar package (e.g. `language()`, `language_php()`)."""
        raise NotImplementedError

    def get_parser(self) -> Parser:
        """Return a cached tree-sitter Parser for this language."""
        if self.language_name not in _PARSER_CACHE:
            language = Language(self.get_language_capsule())
            _PARSER_CACHE[self.language_name] = Parser(language)
        return _PARSER_CACHE[self.language_name]

    def parse(self, content: str):
        """Parse content, return tree."""
        return self.get_parser().parse(content.encode("utf-8"))

    def node_text(self, node: Node, source: bytes) -> str:
        """Extract text from a tree-sitter node."""
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def node_location(self, node: Node) -> str:
        """Return 'L{start_line}' or 'L{start}-L{end}'."""
        start = node.start_point[0] + 1
        end = node.end_point[0] + 1
        if start == end:
            return f"L{start}"
        return f"L{start}-L{end}"

    def make_node_id(self, filepath: str, *parts: str) -> str:
        """Create a unique node ID: filepath::Class::method"""
        return "::".join([filepath] + [p for p in parts if p])

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        """Override in subclass. Must return ExtractionResult."""
        raise NotImplementedError

    def find_children_by_type(self, node: Node, *types: str) -> list[Node]:
        return [c for c in node.children if c.type in types]

    def find_descendants_by_type(self, node: Node, *types: str) -> list[Node]:
        found: list[Node] = []
        for child in node.children:
            if child.type in types:
                found.append(child)
            found.extend(self.find_descendants_by_type(child, *types))
        return found
