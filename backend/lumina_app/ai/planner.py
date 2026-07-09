import json
import re
from collections import Counter
from dataclasses import dataclass, field

import anthropic

from lumina_app.settings import settings


def _extract_text(message) -> str:
    """Return the first text block's content.

    claude-sonnet-5 runs adaptive thinking by default, so content[0] is
    often a `thinking` block rather than the answer — content[0].text is
    then None, not a "no response" signal. Find the first block that's
    actually type=="text" instead of assuming position 0.
    """
    for block in message.content:
        if block.type == "text":
            return block.text
    return ""


@dataclass
class ScenePlan:
    scene_name: str
    title: str
    description: str
    relevant_files: list[str] = field(default_factory=list)
    community_id: int | None = None


async def plan_visualization(
    graph: dict,
    summaries: dict[str, str],
    focus: str | None = None,
    custom_instructions: str | None = None,
) -> list[ScenePlan]:
    god_nodes = graph.get("god_nodes", [])[:5]
    community_summary = graph.get("community_summary", {})
    language_summary = graph.get("language_summary", {})

    lang_str = ", ".join(f"{lang}: {count} file(s)" for lang, count in language_summary.items())

    god_str = "\n".join(
        f"  - {n['label']} ({n['type']}, degree {n['degree']}, in {n['source_file']})" for n in god_nodes
    )

    community_str = "\n".join(
        f"  Community {cid}: {info['size']} nodes, "
        f"top: {', '.join(info['top_nodes'][:3])}, "
        f"files: {', '.join(info['files'][:3])}"
        for cid, info in community_summary.items()
    )

    summaries_str = "\n".join(f"  {path}: {summary}" for path, summary in list(summaries.items())[:20])

    focus_hint = f"\nFocus on: {focus}" if focus else ""

    user_message = f"""Languages: {lang_str}

Architectural hubs (god nodes):
{god_str}

Code communities (Leiden clusters):
{community_str}

File summaries:
{summaries_str}{focus_hint}

Return a JSON array of 3-5 scene plans. Each element:
{{
  "scene_name": "ValidPythonClassName",
  "title": "Human Readable Title",
  "description": "What this scene shows and why it matters",
  "relevant_files": ["file1.py", "file2.ts"],
  "community_id": 0
}}"""

    if custom_instructions:
        user_message += f"\n\nAdditional instructions from the user:\n{custom_instructions}"

    system = """You are a technical animation director. Plan Manim scenes
that explain a codebase visually. Each scene must be distinct and
illuminate a different architectural concept.

SCENE TYPE GUIDELINES:
- Scene 1: ALWAYS an architecture overview showing layers/structure
- Scene 2: A data flow or request lifecycle if routes/APIs exist
- Scene 3: Data models / class hierarchy if models exist
- Scene 4: A specific community or subsystem detail
- Scene 5: Optional — only if there's a truly distinct concept

NAMING CONVENTION:
- Use descriptive names: ArchitectureOverview, AuthRequestFlow,
  UserModelHierarchy, DatabaseLayer, ServiceCommunity
- NOT generic names like: Overview, Scene1, CodeScene

For each scene, relevant_files should contain ONLY the files
directly involved in that concept (2-5 files max, not all files).

Return ONLY a valid JSON array. No markdown. No explanation.
Each element: {
  "scene_name": "DescriptivePythonClassName",
  "title": "Human Readable Title (max 40 chars)",
  "description": "Specific description of what to animate and how.
                  Mention specific class names, route paths, or
                  relationships from the summaries.",
  "relevant_files": ["only", "relevant", "files"],
  "community_id": 0
}"""

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model_smart,
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = _extract_text(message).strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        plans_data = json.loads(raw)
        return [ScenePlan(**p) for p in plans_data]

    except Exception:
        # Fallback: one overview scene
        all_files = list(summaries.keys())[:5]
        top_labels = [n["label"] for n in god_nodes[:3]]
        return [
            ScenePlan(
                scene_name="CodebaseOverview",
                title="Codebase Architecture Overview",
                description=(
                    f"High-level overview showing the main components: {', '.join(top_labels)}"
                ),
                relevant_files=all_files,
                community_id=None,
            )
        ]


# (min, max) number of onboarding videos per package_type.
PACKAGE_VIDEO_LIMITS = {"full": (3, 5), "quick": (1, 1), "technical": (2, 3)}


def _sanitize_scene_name(label: str, fallback: str) -> str:
    """Turn an arbitrary label into a valid Python class name."""
    name = re.sub(r"[^0-9a-zA-Z]", "", label) or fallback
    if not name or name[0].isdigit():
        name = f"Scene{name}"
    return name


def _unique_name(candidate: str, used_names: set[str]) -> str:
    name = candidate
    n = 2
    while name in used_names:
        name = f"{candidate}{n}"
        n += 1
    return name


def _pad_with_default_plans(
    plans: list[ScenePlan],
    graph: dict,
    summaries: dict[str, str],
    min_videos: int,
) -> list[ScenePlan]:
    """Top up `plans` with community/god-node-derived scene plans until it
    reaches min_videos.

    The AI is asked to plan enough videos, but a small codebase, a thin
    community structure, or a degenerate response can leave it short —
    this guarantees the package still meets its minimum by falling back to
    the same god_nodes/community_summary data the AI itself was given.
    """
    if len(plans) >= min_videos:
        return plans

    used_names = {p.scene_name for p in plans}
    used_communities = {p.community_id for p in plans if p.community_id is not None}

    community_summary = graph.get("community_summary", {})
    god_nodes = graph.get("god_nodes", [])

    # Prefer padding from distinct communities not already covered.
    for cid, info in community_summary.items():
        if len(plans) >= min_videos:
            break
        if cid in used_communities:
            continue
        top_nodes = info.get("top_nodes", [])
        label = top_nodes[0] if top_nodes else f"Community{cid}"
        scene_name = _unique_name(_sanitize_scene_name(label, f"Community{cid}"), used_names)
        used_names.add(scene_name)
        used_communities.add(cid)
        files = info.get("files", [])[:6] or list(summaries.keys())[:5]
        plans.append(
            ScenePlan(
                scene_name=scene_name,
                title=f"{label} Overview"[:40],
                description=f"Overview of the {label} subsystem: {', '.join(top_nodes[:3])}",
                relevant_files=files,
                community_id=cid,
            )
        )

    # Still short? Draw on god nodes not yet used as a scene basis.
    for node in god_nodes:
        if len(plans) >= min_videos:
            break
        label = node["label"]
        scene_name = _sanitize_scene_name(label, "KeyComponent")
        if scene_name in used_names:
            continue
        used_names.add(scene_name)
        source_file = node.get("source_file")
        plans.append(
            ScenePlan(
                scene_name=scene_name,
                title=f"{label} Deep Dive"[:40],
                description=(
                    f"Focused look at {label}, a key {node.get('type', 'component')} "
                    f"in {source_file or 'the codebase'}."
                ),
                relevant_files=[source_file] if source_file else list(summaries.keys())[:3],
                community_id=None,
            )
        )

    # Still short (tiny codebase, no communities/god nodes left to draw
    # on) — pad with additional overview videos as a last resort.
    while len(plans) < min_videos:
        scene_name = _unique_name("ArchitectureOverview", used_names)
        used_names.add(scene_name)
        plans.append(
            ScenePlan(
                scene_name=scene_name,
                title="Architecture Overview",
                description="High-level overview of the codebase's main components.",
                relevant_files=list(summaries.keys())[:5],
                community_id=None,
            )
        )

    return plans


async def plan_onboarding_videos(
    graph: dict,
    summaries: dict[str, str],
    package_type: str = "full",
) -> list[ScenePlan]:
    """Plan one focused onboarding video per major architectural community.

    Unlike plan_visualization (which plans a handful of scenes for a single
    combined video), this plans multiple *separate* videos — one per
    subsystem — so each can be rendered and reviewed independently.
    """
    min_videos, max_videos = PACKAGE_VIDEO_LIMITS.get(package_type, (3, 5))

    god_nodes = graph.get("god_nodes", [])[:8]
    community_summary = graph.get("community_summary", {})
    language_summary = graph.get("language_summary", {})

    lang_str = ", ".join(f"{lang}: {count} file(s)" for lang, count in language_summary.items())

    god_str = "\n".join(
        f"  - {n['label']} ({n['type']}, degree {n['degree']}, in {n['source_file']})" for n in god_nodes
    )

    community_str = "\n".join(
        f"  Community {cid}: {info['size']} nodes, "
        f"top: {', '.join(info['top_nodes'][:5])}, "
        f"files: {', '.join(info['files'][:6])}"
        for cid, info in community_summary.items()
    )

    summaries_str = "\n".join(f"  {path}: {summary}" for path, summary in list(summaries.items())[:30])

    user_message = f"""Languages: {lang_str}

Architectural hubs (god nodes):
{god_str}

Code communities (Leiden clusters):
{community_str}

File summaries:
{summaries_str}

Return a JSON array of BETWEEN {min_videos} AND {max_videos} video plans —
one per major architectural community/layer. Each element:
{{
  "scene_name": "ValidPythonClassName",
  "title": "Human Readable Title",
  "description": "What this video shows and why it matters",
  "relevant_files": ["file1.py", "file2.ts"],
  "community_id": 0
}}"""

    system = f"""You are planning an onboarding video package for a codebase.
Unlike a single explainer video, this package produces SEPARATE focused
videos — one per architectural layer/subsystem — using the Leiden
community structure as your guide to what's actually a distinct subsystem.

NAMING CONVENTION — name each video by what it IS, never by community
number:
  Good: "AuthenticationFlow", "RenderPipeline", "DataModels",
        "APIEndpoints", "FrontendArchitecture"
  Bad:  "Community0", "Overview", "Scene1", "Part2"

RULES:
- Return AT LEAST {min_videos} and AT MOST {max_videos} video plans.
- Each video must focus on ONE specific subsystem — never repeat the same
  subsystem twice.
- relevant_files: ONLY the files directly involved in that subsystem,
  3-6 files max (not all files in the community).
- If there aren't {min_videos} naturally distinct communities, add focused
  deep-dive videos on the most important god nodes/files to reach the
  minimum — do not fall short of {min_videos}.
- If min_videos == max_videos == 1, make the single video an
  architecture-overview video covering the whole codebase.

Return ONLY a valid JSON array. No markdown. No explanation.
Each element: {{
  "scene_name": "DescriptivePythonClassName",
  "title": "Human Readable Title (max 40 chars)",
  "description": "Specific description of what to animate and how.
                  Mention specific class names, route paths, or
                  relationships from the summaries.",
  "relevant_files": ["only", "relevant", "files"],
  "community_id": 0
}}"""

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model_smart,
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = _extract_text(message).strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        plans_data = json.loads(raw)
        plans = [ScenePlan(**p) for p in plans_data][:max_videos]
        return _pad_with_default_plans(plans, graph, summaries, min_videos)

    except Exception:
        # Fallback: one overview video, padded up to min_videos if needed.
        all_files = list(summaries.keys())[:5]
        top_labels = [n["label"] for n in god_nodes[:3]]
        fallback = [
            ScenePlan(
                scene_name="ArchitectureOverview",
                title="Architecture Overview",
                description=(
                    f"High-level overview showing the main components: {', '.join(top_labels)}"
                ),
                relevant_files=all_files,
                community_id=None,
            )
        ]
        return _pad_with_default_plans(fallback, graph, summaries, min_videos)


def detect_folders(graph: dict) -> list[str]:
    """Detect top-level folders from the graph nodes, most files first.

    Skips single-file "folders" — a folder needs 2+ files to be worth its
    own deep-dive video; root-level files (no folder at all) never count.
    """
    folder_counts: Counter[str] = Counter()
    for node in graph.get("nodes", []):
        path = node.get("source_file", "")
        parts = path.replace("\\", "/").split("/")
        if len(parts) > 1:
            folder_counts[parts[0]] += 1
    return [folder for folder, count in folder_counts.most_common() if count >= 2]


def _folder_matches(path: str, folder: str) -> bool:
    norm = path.replace("\\", "/")
    return norm == folder or norm.startswith(folder + "/")


async def plan_folder_videos(
    graph: dict,
    summaries: dict[str, str],
    folders: list[str],
) -> list[ScenePlan]:
    """Plan one focused video per top-level folder — a deterministic
    deep-dive into each folder's internals. Folder boundaries are
    unambiguous, so unlike plan_visualization/plan_onboarding_videos this
    needs no AI call.
    """
    folder_plans = []
    used_names: set[str] = set()

    for idx, folder in enumerate(folders[:5]):  # max 5 folder videos
        folder_nodes = [n for n in graph.get("nodes", []) if _folder_matches(n.get("source_file", ""), folder)]
        folder_files = list({n["source_file"] for n in folder_nodes})[:8]

        classes = [n["label"] for n in folder_nodes if n["type"] == "class"][:5]
        routes = [n["label"] for n in folder_nodes if n["type"] == "route"][:5]

        scene_name = _unique_name(
            _sanitize_scene_name(folder.title(), f"Folder{idx}") + "FolderOverview", used_names
        )
        used_names.add(scene_name)

        folder_plans.append(
            ScenePlan(
                scene_name=scene_name,
                title=f"{folder.title()} — Internal Architecture"[:40],
                description=(
                    f"FolderOverview: Deep dive into {folder}/. "
                    f"Tell the story of this folder: show its {len(folder_files)} "
                    f"files as colored rectangles, animate the key relationships "
                    f"between them"
                    + (f" (key classes: {', '.join(classes[:3])})" if classes else "")
                    + (f" (routes: {', '.join(routes[:3])})" if routes else "")
                    + f", then show how {folder}/ connects to other parts "
                    f"of the system. "
                    f"End with a slide: 'See docs/{folder}/README.md for more.' "
                    f"Duration: 30-50 seconds. Use the folder_overview visual pattern."
                ),
                relevant_files=folder_files or list(summaries.keys())[:5],
            )
        )

    return folder_plans
