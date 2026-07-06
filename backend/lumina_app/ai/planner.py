import json

import anthropic

from lumina_app.parser.base import CodebaseGraph
from lumina_app.settings import settings

_SYSTEM_PROMPT = (
    "You are a visualization planner for a codebase-explainer video tool. "
    "Given a codebase's architectural graph (files, edges, layers) and a "
    "focus area, produce a structured storyboard plan: an ordered list of "
    "scenes, each with a title, a short narration script, and the files or "
    "layers it should highlight. Respond with JSON only, matching this "
    'shape: {"scenes": [{"title": str, "narration": str, "highlights": '
    "[str]}]}."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "narration": {"type": "string"},
                    "highlights": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "narration", "highlights"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}


def _graph_summary(graph: CodebaseGraph) -> str:
    layer_lines = [f"- {layer}: {len(paths)} files" for layer, paths in graph.layers.items()]
    edge_lines = [f"- {e.source} -> {e.target} ({e.kind})" for e in graph.edges[:100]]
    return (
        f"Language summary: {json.dumps(graph.language_summary)}\n"
        f"Layers:\n" + "\n".join(layer_lines) + "\n\n"
        f"Sample edges:\n" + "\n".join(edge_lines)
    )


async def plan_video(graph: CodebaseGraph, focus: str) -> dict:
    """Produce a scene-by-scene storyboard plan for a codebase explainer video."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_model_smart,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Focus: {focus}\n\n"
                    f"Codebase graph summary:\n{_graph_summary(graph)}"
                ),
            }
        ],
    )
    text = next((b.text for b in response.content if b.type == "text"), "{}")
    return json.loads(text)
