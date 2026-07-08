import os
import time
import urllib.request
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


def _poll_package(
    client: httpx.Client,
    package_id: str,
    max_wait: int = 1800,
) -> dict:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = client.get(f"/api/package/{package_id}")
        r.raise_for_status()
        data = r.json()
        if data["status"] == "done":
            return data
        time.sleep(10)
    return {
        "status": "timeout",
        "package_id": package_id,
        "message": f"Use get_package_status('{package_id}') to check progress.",
    }


def _download_file(url: str, dest: str) -> None:
    """Download a URL to a local path.

    Plain urllib.request.urlretrieve sends Python's default User-Agent
    ("Python-urllib/x.y"), which manimstudio.me's WAF blocks with a 403 —
    any normal-looking User-Agent gets through.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Lumina/1.0)"})
    with urllib.request.urlopen(req) as response, open(dest, "wb") as f:
        f.write(response.read())


def _save_package_to_disk(package_data: dict, project_path: str) -> str:
    """Download all done videos and write all done docs to
    <project_path>/project-docs/, plus an index.md linking everything.

    Mutates the video/doc dicts in package_data in place, adding
    "saved_to" (or "download_error"/"save_error" on failure) to each.
    """
    output_dir = Path(project_path).resolve() / "project-docs"
    videos_dir = output_dir / "videos"
    docs_dir = output_dir / "docs"
    videos_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    saved = {"videos": [], "docs": []}

    for video in package_data.get("videos", []):
        if video.get("status") == "done" and video.get("video_url"):
            folder = video.get("folder")
            filename = f"{folder}_overview.mp4" if folder else "00_complete_architecture.mp4"
            dest = videos_dir / filename
            try:
                _download_file(video["video_url"], str(dest))
                saved["videos"].append(str(dest))
                video["saved_to"] = str(dest)
            except Exception as e:
                video["download_error"] = str(e)

    for doc in package_data.get("docs", []):
        if doc.get("status") == "done" and doc.get("content"):
            filename = doc.get("filename") or "doc.md"
            dest = output_dir / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_text(doc["content"], encoding="utf-8")
                saved["docs"].append(str(dest))
                doc["saved_to"] = str(dest)
            except Exception as e:
                doc["save_error"] = str(e)

    index_lines = [
        "# Project Documentation Index\n",
        "Generated by Lumina\n",
        "\n## Videos\n",
    ]
    for v in saved["videos"]:
        index_lines.append(f"- [{Path(v).name}]({Path(v).name})\n")
    index_lines.append("\n## Documentation\n")
    for d in saved["docs"]:
        rel = Path(d).relative_to(output_dir)
        index_lines.append(f"- [{rel}]({rel})\n")

    (output_dir / "index.md").write_text("".join(index_lines), encoding="utf-8")

    return str(output_dir)


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


# ─── TOOL 8: create_onboarding_package ───────────────────────────────────

@mcp.tool
def create_onboarding_package(
    path: str = ".",
    package_type: str = "full",
    custom_instructions: str | None = None,
    quality: str = "low",
    wait: bool = True,
    save_to_disk: bool = True,
) -> dict:
    """
    Generate a complete onboarding package for a codebase: a long
    multi-scene overview video covering the whole architecture, one
    deep-dive video per top-level folder, and written documentation
    (including a per-folder README) — everything needed to understand
    the system.

    package_type options:
    - "full"      → overview + up to 5 folder videos + architecture/onboarding/API docs
    - "quick"     → overview video only + README (no folder deep-dives)
    - "technical" → overview + up to 3 folder videos + architecture/API docs

    Args:
        path:                Local path to analyze ("." for current dir)
        package_type:        full | quick | technical
        custom_instructions: Extra guidance. e.g.:
                             "This is a SaaS platform, emphasize
                              the billing and quota systems"
        quality:             low | medium | high
        wait:                True = block until all done (may take 10+ min)
                             False = return package_id immediately
        save_to_disk:        When wait=True, download all videos and write
                             all docs to <path>/project-docs/ once done
                             (only takes effect if wait=True).

    Returns when wait=True:
        {
          package_id, status: "done",
          videos: [{focus, scene_name, video_url, status, is_overview, folder}],
          docs: [{doc_type, filename, content, word_count, folder}],
          saved_to, message (if save_to_disk saved anything)
        }
    """
    resolved = str(Path(path).resolve())
    project_name = Path(resolved).name

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
        codebase_id = r.json()["codebase_id"]

        r = client.post(
            "/api/onboard",
            json={
                "codebase_id": codebase_id,
                "package_type": package_type,
                "custom_instructions": custom_instructions,
                "quality": quality,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        result = r.json()

        if not wait:
            return result

        data = _poll_package(client, result["package_id"])

    if save_to_disk and data.get("status") == "done":
        output_dir = _save_package_to_disk(data, resolved)
        data["saved_to"] = output_dir
        data["message"] = (
            f"All outputs saved to {output_dir}\n"
            f"Videos: {len([v for v in data['videos'] if v.get('saved_to')])} downloaded\n"
            f"Docs: {len([d for d in data['docs'] if d.get('saved_to')])} saved\n"
            f"Index: {output_dir}/index.md"
        )

    return data


# ─── TOOL 9: get_package_status ──────────────────────────────────────────

@mcp.tool
def get_package_status(package_id: str) -> dict:
    """
    Check the status of an onboarding package generation.
    Poll this after create_onboarding_package(wait=False).

    Returns all videos and docs with their current status.
    Videos and docs with status='done' include their URLs/content.
    """
    with _client() as client:
        r = client.get(f"/api/package/{package_id}")
        r.raise_for_status()
        return r.json()


# ─── TOOL 10: explain_folder ──────────────────────────────────────────────

@mcp.tool
def explain_folder(
    folder_path: str,
    codebase_id: str | None = None,
    project_path: str = ".",
    quality: str = "low",
    save_to_disk: bool = True,
) -> dict:
    """
    Generate a deep-dive video and README for one specific folder.
    Use this when you want to understand one part of the codebase
    in depth after getting the overview package.

    Args:
        folder_path:  Relative folder path to explain.
                      e.g. "backend", "worker", "frontend/src"
        codebase_id:  From a previous analyze call. If not provided,
                      will re-analyze the project_path first.
        project_path: Root of the project (default: current dir)
        quality:      low | medium | high
        save_to_disk: Save video + README to project-docs/

    Returns:
        {
          folder, codebase_id, video_url, readme_content,
          video_saved_to, readme_saved_to (if save_to_disk=True)
        }
    """
    resolved_project = str(Path(project_path).resolve())

    with _client() as client:
        if not codebase_id:
            try:
                files = _read_local_path(resolved_project)
            except ValueError as e:
                return {"error": str(e)}
            if not files:
                return {"error": f"No supported code files found in {resolved_project}"}

            r = client.post(
                "/api/analyze",
                json={"files": files, "name": Path(resolved_project).name},
                timeout=120.0,
            )
            r.raise_for_status()
            codebase_id = r.json()["codebase_id"]

        r = client.post(
            "/api/onboard",
            json={
                "codebase_id": codebase_id,
                "package_type": "quick",
                "custom_instructions": (
                    f"Focus ONLY on the {folder_path}/ folder. "
                    f"Show: what files are in it, key classes and functions, "
                    f"how they connect to each other, "
                    f"how this folder connects to the rest of the system. "
                    f"End with: 'See project-docs/docs/{folder_path}/README.md'"
                ),
                "quality": quality,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        package_id = r.json()["package_id"]

        data = _poll_package(client, package_id, max_wait=600)

    result = {
        "folder": folder_path,
        "codebase_id": codebase_id,
        "video_url": None,
        "readme_content": None,
    }

    if data.get("status") != "done":
        result["status"] = data.get("status", "unknown")
        result["message"] = data.get("message", "Package did not complete in time.")
        return result

    for v in data.get("videos", []):
        if v.get("status") == "done":
            result["video_url"] = v.get("video_url")
            break

    for d in data.get("docs", []):
        if d.get("status") == "done":
            result["readme_content"] = d.get("content")
            break

    if save_to_disk:
        if result["video_url"]:
            vid_dir = Path(resolved_project) / "project-docs" / "videos"
            vid_dir.mkdir(parents=True, exist_ok=True)
            dest = vid_dir / f"{folder_path.replace('/', '_')}_detail.mp4"
            try:
                _download_file(result["video_url"], str(dest))
                result["video_saved_to"] = str(dest)
            except Exception as e:
                result["video_download_error"] = str(e)

        if result["readme_content"]:
            doc_path = Path(resolved_project) / "project-docs" / "docs" / folder_path / "README.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text(result["readme_content"], encoding="utf-8")
            result["readme_saved_to"] = str(doc_path)

    return result


# ─── Entry point ─────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
