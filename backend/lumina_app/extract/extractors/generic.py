import re

from lumina_app.extract.schema import Edge, ExtractionResult, Node

_CLASS_RE = re.compile(
    r"^\s*(?:pub\s+|public\s+|export\s+)?(?:class|struct|interface|type|trait|enum)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"^\s*(?:pub\s+|public\s+|export\s+|async\s+|static\s+)*"
    r"(?:def|func|function|fn|sub|proc)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_IMPORT_RE = re.compile(
    r"^\s*(?:import|require|include|use|using|from)\s+"
    r"['\"]?([A-Za-z0-9_./:-]+)['\"]?",
    re.MULTILINE,
)


class GenericExtractor:
    """Regex-based fallback for languages without a tree-sitter grammar.

    Confidence is always AMBIGUOUS — regex matching over source text can't
    guarantee correctness the way a real parse tree can.
    """

    def extract(self, filepath: str, content: str) -> ExtractionResult:
        result = ExtractionResult(language="unknown")

        module_id = filepath
        result.nodes.append(
            Node(id=module_id, label=filepath, type="module", source_file=filepath, source_location="L1")
        )

        for match in _CLASS_RE.finditer(content):
            name = match.group(1)
            line = content.count("\n", 0, match.start()) + 1
            node_id = f"{filepath}::{name}"
            result.nodes.append(
                Node(id=node_id, label=name, type="class", source_file=filepath, source_location=f"L{line}")
            )
            result.edges.append(
                Edge(source=module_id, target=node_id, relation="contains", confidence="AMBIGUOUS")
            )

        for match in _FUNCTION_RE.finditer(content):
            name = match.group(1)
            line = content.count("\n", 0, match.start()) + 1
            node_id = f"{filepath}::{name}"
            result.nodes.append(
                Node(id=node_id, label=name, type="function", source_file=filepath, source_location=f"L{line}")
            )
            result.edges.append(
                Edge(source=module_id, target=node_id, relation="contains", confidence="AMBIGUOUS")
            )

        for match in _IMPORT_RE.finditer(content):
            name = match.group(1)
            line = content.count("\n", 0, match.start()) + 1
            node_id = f"{filepath}::import::{name}"
            result.nodes.append(
                Node(id=node_id, label=name, type="import", source_file=filepath, source_location=f"L{line}")
            )
            result.edges.append(
                Edge(source=module_id, target=node_id, relation="contains", confidence="AMBIGUOUS")
            )
            target_label = name.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
            result.edges.append(
                Edge(source=node_id, target=target_label, relation="imports", confidence="AMBIGUOUS")
            )

        return result
