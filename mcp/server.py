import os
import time
from pathlib import Path

import httpx
from fastmcp import FastMCP

mcp = FastMCP(
    "lumina",
    instructions="""Lumina analyzes codebases and generates
animated explainer videos and documentation.

Primary tools:
- explain_codebase: full pipeline → video URL
- analyze_local_path: handle large local repos efficiently
- generate_docs: generate README/architecture/API/onboarding docs

For large projects (50+ files) always use analyze_local_path
instead of reading files yourself.
""",
)

LUMINA_API_URL = os.getenv("LUMINA_API_URL", "http://localhost:8000")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".next", "vendor", "third_party",
    ".pytest_cache", "coverage", ".mypy_cache",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".cs", ".kt", ".scala",
    ".php", ".swift", ".lua", ".sh", ".bash", ".sql",
    ".toml", ".yaml", ".yml", ".json", ".md",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".ico",
    ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".tar", ".gz",
}

MAX_FILE_SIZE = 100_000
MAX_FILES = 500


def _client() -> httpx.Client:
    return httpx.Client(base_url=LUMINA_API_URL, timeout=60.0)


def _read_local_path(path: str) -> dict[str, str]:
    root = Path(path).resolve()
    if not root.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not root.is_dir():
        raise ValueError(f"Not a directory: {path}")

    files: dict[str, str] = {}

    gitignore_patterns: set[str] = set()
    gitignore = root / ".gitignore"
    if gitignore.exists():
        for line in gitignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                gitignore_patterns.add(line.rstrip("/"))

    for filepath in root.rglob("*"):
        if not filepath.is_file():
            continue
        parts = filepath.relative_to(root).parts
        if any(p.startswith(".") or p in SKIP_DIRS for p in parts[:-1]):
            continue
        if filepath.suffix.lower() in SKIP_EXTENSIONS:
            continue
        if filepath.suffix.lower() not in CODE_EXTENSIONS:
            continue
        if filepath.stat().st_size > MAX_FILE_SIZE:
            continue
        rel = str(filepath.relative_to(root))
        if any(pat in rel or filepath.name == pat for pat in gitignore_patterns):
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            files[rel] = content
        except Exception:
            continue
        if len(files) >= MAX_FILES:
            break

    return files


def _poll_video(
    client: httpx.Client,
    video_id: str,
    scenes: list,
    codebase_id: str,
    focus: str | None,
    max_wait: int = 300,
) -> dict:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = client.get(f"/api/video/{video_id}")
        r.raise_for_status()
        data = r.json()
        if data["status"] == "done":
            return {
                "video_id": video_id,
                "video_url": data["video_url"],
                "status": "done",
                "scenes": scenes,
                "codebase_id": codebase_id,
                "focus": focus or "overview",
            }
        if data["status"] == "error":
            return {"status": "error", "video_id": video_id}
        time.sleep(5)
    return {
        "status": "timeout",
        "video_id": video_id,
        "message": f"Use get_video_status('{video_id}') to check progress.",
    }


# ─── TOOL 1: analyze_codebase ────────────────────────────────────────────

@mcp.tool
def analyze_codebase(
    files: dict[str, str],
    name: str = "unnamed",
) -> dict:
    """
    Parse and analyze a codebase from file contents.
    Builds a dependency graph using tree-sitter (10+ languages),
    detects communities with Leiden clustering, finds god nodes.

    Use analyze_local_path instead for large repos (50+ files).

    Args:
        files: {filepath: content} — max 500 files, 100KB each.
        name:  Project name for reports.

    Returns:
        codebase_id (use in explain_codebase / generate_docs),
        node_count, edge_count, god_nodes, community_count,
        language_summary, cached.
    """
    with _client() as client:
        r = client.post("/api/analyze", json={"files": files, "name": name})
        r.raise_for_status()
        return r.json()


# ─── TOOL 2: explain_codebase ────────────────────────────────────────────

@mcp.tool
def explain_codebase(
    files: dict[str, str] | None = None,
    codebase_id: str | None = None,
    focus: str | None = None,
    quality: str = "low",
    name: str = "unnamed",
    custom_instructions: str | None = None,
    wait_for_video: bool = True,
    max_wait_seconds: int = 300,
) -> dict:
    """
    Generate an animated video explaining a codebase.
    Full pipeline: analyze → summarize → plan scenes → render.

    Pass files directly OR a codebase_id from analyze_codebase.

    Args:
        files:               {filepath: content}. Required if no codebase_id.
        codebase_id:         From a previous analyze_codebase call.
        focus:               What to animate. Examples:
                             "overall architecture"
                             "authentication flow"
                             "database layer and models"
                             "how API requests are processed"
                             "onboarding for new developers"
        quality:             "low" (fast), "medium", "high"
        name:                Project name.
        custom_instructions: Extra guidance for generation. Examples:
                             "Use blue for frontend, red for database"
                             "Target audience: junior developers"
                             "Emphasize security boundaries"
        wait_for_video:      True = block until done (recommended).
        max_wait_seconds:    Max wait time (default 5 min).

    Returns:
        video_url (when done), video_id, status, scenes, codebase_id.
    """
    with _client() as client:
        if not codebase_id:
            if not files:
                return {"error": "Provide files or codebase_id"}
            r = client.post("/api/analyze", json={"files": files, "name": name})
            r.raise_for_status()
            codebase_id = r.json()["codebase_id"]

        r = client.post(
            "/api/explain",
            json={
                "codebase_id": codebase_id,
                "focus": focus,
                "quality": quality,
                "custom_instructions": custom_instructions,
            },
        )
        r.raise_for_status()
        result = r.json()
        video_id = result["video_id"]

        if not wait_for_video:
            return result

        return _poll_video(
            client,
            video_id,
            result.get("scenes", []),
            codebase_id,
            focus,
            max_wait_seconds,
        )


# ─── TOOL 3: analyze_local_path ──────────────────────────────────────────

@mcp.tool
def analyze_local_path(
    path: str,
    name: str | None = None,
    focus: str | None = None,
    generate_video: bool = False,
    quality: str = "low",
    custom_instructions: str | None = None,
) -> dict:
    """
    Analyze a local project directory directly.
    Most efficient for large codebases — Lumina reads files itself.

    Use this instead of explain_codebase for any project with 50+ files,
    or when running Claude Code inside a project directory.

    Args:
        path:                Local path. Use "." for current directory.
        name:                Project name (defaults to directory name).
        focus:               What to focus on. Examples:
                             "overall architecture"
                             "onboarding for new developers"
                             "authentication system"
        generate_video:      True = analyze + generate video.
                             False = analyze only, return graph.
        quality:             "low" | "medium" | "high"
        custom_instructions: Extra guidance for video generation.

    Returns:
        Graph analysis + video_url if generate_video=True.
    """
    resolved = str(Path(path).resolve())
    project_name = name or Path(resolved).name

    try:
        files = _read_local_path(resolved)
    except ValueError as e:
        return {"error": str(e)}

    if not files:
        return {
            "error": f"No supported code files found in {resolved}",
            "tip": "Check that the path contains .py, .ts, .go, etc. files",
        }

    with _client() as client:
        r = client.post(
            "/api/analyze",
            json={"files": files, "name": project_name},
            timeout=120.0,
        )
        r.raise_for_status()
        analysis = r.json()
        analysis["path"] = resolved
        analysis["files_read"] = len(files)

        if not generate_video:
            return analysis

        r = client.post(
            "/api/explain",
            json={
                "codebase_id": analysis["codebase_id"],
                "focus": focus,
                "quality": quality,
                "custom_instructions": custom_instructions,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        result = r.json()

        return _poll_video(
            client,
            result["video_id"],
            result.get("scenes", []),
            analysis["codebase_id"],
            focus,
        )


# ─── TOOL 4: generate_docs ───────────────────────────────────────────────

@mcp.tool
def generate_docs(
    codebase_id: str,
    doc_type: str = "readme",
    custom_instructions: str | None = None,
    save_to_file: str | None = None,
) -> dict:
    """
    Generate markdown documentation for an analyzed codebase.

    Doc types:
    - "readme"       — Project overview, setup, quick start
    - "architecture" — Detailed technical architecture
    - "api"          — API endpoints and usage reference
    - "onboarding"   — New developer guide

    Args:
        codebase_id:         From analyze_codebase or analyze_local_path.
        doc_type:            readme | architecture | api | onboarding
        custom_instructions: Extra guidance. Examples:
                             "This is a payment system, emphasize security"
                             "Target audience: non-technical stakeholders"
        save_to_file:        Optional path to save the markdown file.
                             e.g. "README.md" or "docs/ARCHITECTURE.md"

    Returns:
        filename, content (full markdown), word_count,
        saved_to (if save_to_file provided).
    """
    with _client() as client:
        r = client.post(
            "/api/docs",
            json={
                "codebase_id": codebase_id,
                "doc_type": doc_type,
                "custom_instructions": custom_instructions,
            },
            timeout=120.0,
        )
        r.raise_for_status()
        result = r.json()

    if save_to_file:
        p = Path(save_to_file).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(result["content"], encoding="utf-8")
        result["saved_to"] = str(p)

    return result


# ─── TOOL 5: get_video_status ────────────────────────────────────────────

@mcp.tool
def get_video_status(video_id: str) -> dict:
    """
    Poll the status of an in-progress render.
    Use when explain_codebase was called with wait_for_video=False.

    Returns: status, video_url (when done), codebase_id, focus.
    """
    with _client() as client:
        r = client.get(f"/api/video/{video_id}")
        r.raise_for_status()
        return r.json()


# ─── TOOL 6: get_codebase_graph ──────────────────────────────────────────

@mcp.tool
def get_codebase_graph(codebase_id: str) -> dict:
    """
    Retrieve the dependency graph for a codebase.
    Returns nodes, edges, communities, god_nodes, language_summary.
    Use to inspect architecture without generating a video.
    """
    with _client() as client:
        r = client.get(f"/api/codebase/{codebase_id}")
        r.raise_for_status()
        return r.json()


# ─── TOOL 7: list_supported_languages ────────────────────────────────────

@mcp.tool
def list_supported_languages() -> dict:
    """
    List all languages Lumina can analyze via tree-sitter.
    Code is parsed locally — raw source never sent to any AI API.
    Only 2-3 sentence summaries per file go to the AI.
    """
    return {
        "languages": [
            "python", "javascript", "typescript", "go", "rust",
            "java", "c", "cpp", "ruby", "csharp", "kotlin",
            "scala", "php", "swift", "lua",
        ],
        "extensions": {
            ".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".go": "go",
            ".rs": "rust", ".java": "java", ".c": "c", ".h": "c",
            ".cpp": "cpp", ".cc": "cpp", ".rb": "ruby",
            ".cs": "csharp", ".kt": "kotlin", ".scala": "scala",
            ".php": "php", ".swift": "swift", ".lua": "lua",
        },
        "note": (
            "AST parsing is local and free. "
            "AI API is called only for summaries (2-3 sentences/file) "
            "and scene planning. Raw code never leaves your machine."
        ),
    }


# ─── Entry point ─────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
