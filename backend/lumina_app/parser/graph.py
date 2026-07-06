from pathlib import Path

from lumina_app.parser.base import CodebaseGraph, Edge
from lumina_app.parser.python import PythonParser
from lumina_app.parser.typescript import TypeScriptParser

_PARSERS = {
    ".py": PythonParser(),
    ".ts": TypeScriptParser(),
    ".tsx": TypeScriptParser(),
    ".js": TypeScriptParser(),  # JS parser is subset of TS
    ".jsx": TypeScriptParser(),
}

_LAYER_PATTERNS: dict[str, tuple[str, ...]] = {
    "api": ("route", "endpoint", "controller", "handler"),
    "models": ("model", "schema", "entity", "migration"),
    "services": ("service", "manager", "processor"),
    "tests": ("test", "spec", "__test__"),
    "config": ("config", "setting", "env"),
    "frontend": ("frontend", "ui", "component", "page", "src/"),
}


def build_graph(files: dict[str, str]) -> CodebaseGraph:
    """
    Parse all files and build a CodebaseGraph.
    No AI calls — pure static analysis.
    """
    graph = CodebaseGraph()

    # First pass: parse each file
    for filepath, content in files.items():
        ext = Path(filepath).suffix.lower()
        parser = _PARSERS.get(ext)
        if not parser:
            continue
        try:
            node = parser.parse(filepath, content)
            graph.files[filepath] = node
            lang = ext.lstrip(".")
            graph.language_summary[lang] = graph.language_summary.get(lang, 0) + 1
        except Exception:
            continue  # skip unparseable files

    # Second pass: resolve imports to actual file paths
    _resolve_imports(graph, set(files.keys()))

    # Third pass: detect architectural layers
    _detect_layers(graph)

    return graph


def _resolve_imports(graph: CodebaseGraph, known_paths: set[str]) -> None:
    """
    Resolve each file's raw import strings to actual file paths within the
    codebase, adding an "imports" edge for every match found.
    """
    stems: dict[str, str] = {}
    for path in known_paths:
        p = Path(path)
        stems[str(p.with_suffix(""))] = path
        stems[str(p.parent / p.stem)] = path

    for path, node in graph.files.items():
        base_dir = Path(path).parent
        for raw_import in node.imports:
            candidates = [
                raw_import,
                str((base_dir / raw_import).as_posix()),
                str((base_dir / raw_import.lstrip("./")).as_posix()),
            ]
            for candidate in candidates:
                normalized = candidate.replace("\\", "/").lstrip("./")
                target = stems.get(normalized) or stems.get(candidate)
                if target and target != path:
                    graph.edges.append(Edge(source=path, target=target, kind="imports"))
                    break


def _detect_layers(graph: CodebaseGraph) -> None:
    """
    Group files into architectural layers based on
    path patterns and content:
    - api / routes
    - models / database
    - services / business logic
    - utils / helpers
    - frontend / ui
    - tests
    - config
    """
    layers: dict[str, list[str]] = {
        "api": [],
        "models": [],
        "services": [],
        "utils": [],
        "frontend": [],
        "tests": [],
        "config": [],
    }

    for path in graph.files:
        p = path.lower()
        matched = False
        for layer, patterns in _LAYER_PATTERNS.items():
            if any(pattern in p for pattern in patterns):
                layers[layer].append(path)
                matched = True
                break
        if not matched:
            layers["utils"].append(path)

    graph.layers = {k: v for k, v in layers.items() if v}
