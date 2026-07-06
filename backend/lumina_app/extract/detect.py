import fnmatch
from pathlib import PurePosixPath

EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hxx": "cpp",
    ".rb": "ruby",
    ".cs": "csharp",
    ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".r": "r", ".R": "r",
    ".sh": "shell", ".bash": "shell",
    ".ps1": "powershell",
    ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang",
    ".zig": "zig",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv",
    "venv", "dist", "build", "target", ".next",
    "vendor", "third_party", ".pytest_cache",
}

SKIP_FILES_PATTERNS = [
    "*.min.js", "*.bundle.js", "*.generated.*",
    "*.pb.go", "*_pb2.py",  # protobuf generated
    "*/migrations/*.py",  # Django migrations
]


def _is_in_skip_dir(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return any(part in SKIP_DIRS for part in parts)


def _matches_skip_pattern(path: str) -> bool:
    normalized = path.replace("\\", "/")
    name = PurePosixPath(normalized).name
    for pattern in SKIP_FILES_PATTERNS:
        if "/" in pattern:
            if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(f"/{normalized}", pattern):
                return True
        elif fnmatch.fnmatch(name, pattern):
            return True
    return False


def detect_language(filepath: str) -> str | None:
    ext = PurePosixPath(filepath.replace("\\", "/")).suffix
    return EXTENSION_TO_LANGUAGE.get(ext) or EXTENSION_TO_LANGUAGE.get(ext.lower())


def detect_files(files: dict[str, str]) -> dict[str, tuple[str, str]]:
    """
    Returns {filepath: (language, content)}
    for all recognized files, skipping generated/vendor files.
    """
    detected: dict[str, tuple[str, str]] = {}
    for filepath, content in files.items():
        if _is_in_skip_dir(filepath) or _matches_skip_pattern(filepath):
            continue
        language = detect_language(filepath)
        if language is None:
            continue
        detected[filepath] = (language, content)
    return detected
