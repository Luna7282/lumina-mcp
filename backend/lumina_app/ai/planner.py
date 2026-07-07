import json
from dataclasses import dataclass, field

import anthropic

from lumina_app.settings import settings


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

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model_smart,
            max_tokens=1000,
            system=(
                "You are a technical visualization expert. "
                "Plan 3-5 Manim animation scenes that explain "
                "a codebase's architecture. Each scene should "
                "illuminate one key concept. "
                "Return ONLY valid JSON array, no markdown, "
                "no explanation."
            ),
            messages=[{"role": "user", "content": user_message}],
        )
        raw = message.content[0].text.strip()
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
