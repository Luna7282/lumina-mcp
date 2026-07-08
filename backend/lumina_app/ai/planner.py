import json
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
            max_tokens=1000,
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


# Max number of onboarding videos per package_type.
PACKAGE_VIDEO_LIMITS = {"full": 5, "quick": 1, "technical": 3}


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
    max_videos = PACKAGE_VIDEO_LIMITS.get(package_type, 5)

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

Return a JSON array of AT MOST {max_videos} video plans — one per major
architectural community/layer. Each element:
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
- Return AT MOST {max_videos} video plans.
- Merge or drop small/trivial communities rather than padding to the max —
  fewer, higher-signal videos beat many thin ones.
- Each video must focus on ONE specific subsystem.
- relevant_files: ONLY the files directly involved in that subsystem,
  3-6 files max (not all files in the community).
- If there is only one video (max_videos == 1), make it a single
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
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = _extract_text(message).strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        plans_data = json.loads(raw)
        return [ScenePlan(**p) for p in plans_data][:max_videos]

    except Exception:
        # Fallback: one overview video
        all_files = list(summaries.keys())[:5]
        top_labels = [n["label"] for n in god_nodes[:3]]
        return [
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
