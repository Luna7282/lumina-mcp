from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FileNode:
    path: str
    language: str
    exports: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    complexity_score: float = 0.0


@dataclass
class Edge:
    source: str  # file path
    target: str  # file path
    kind: str  # "imports" | "calls" | "inherits" | "uses_model"


@dataclass
class CodebaseGraph:
    files: dict[str, FileNode] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    layers: dict[str, list[str]] = field(default_factory=dict)
    language_summary: dict[str, int] = field(default_factory=dict)


class FileParser(Protocol):
    def parse(self, path: str, content: str) -> FileNode: ...
