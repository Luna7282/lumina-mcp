from dataclasses import dataclass, field
from typing import Literal

NodeType = Literal[
    "module", "class", "function", "method",
    "import", "route", "model", "variable", "constant",
]

Confidence = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]

Relation = Literal[
    "calls", "imports", "defines", "inherits",
    "uses", "contains", "implements", "decorates", "handles",
]


@dataclass
class Node:
    id: str  # unique: "filepath::ClassName::method_name"
    label: str  # human: "method_name"
    type: NodeType
    source_file: str
    source_location: str  # "L42" or "L42-L67"
    docstring: str = ""


@dataclass
class Edge:
    source: str  # node id
    target: str  # node id
    relation: Relation
    confidence: Confidence = "EXTRACTED"


@dataclass
class ExtractionResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    language: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "label": n.label,
                    "type": n.type,
                    "source_file": n.source_file,
                    "source_location": n.source_location,
                    "docstring": n.docstring,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation,
                    "confidence": e.confidence,
                }
                for e in self.edges
            ],
        }
