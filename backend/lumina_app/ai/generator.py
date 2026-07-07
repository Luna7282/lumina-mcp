import anthropic

from lumina_app.ai.planner import ScenePlan
from lumina_app.settings import settings


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


def _fallback_scene(scene_name: str, title: str) -> str:
    return f'''from manim import *

class {scene_name}(Scene):
    def construct(self):
        title = Text("{title}", font_size=36)
        self.play(Write(title))
        self.wait(1)
        self.play(FadeOut(title))
        self.wait(0.5)
'''


async def generate_scene(
    plan: ScenePlan,
    summaries: dict[str, str],
    graph: dict,
) -> str:
    relevant_summaries = "\n".join(
        f"  {f}: {summaries.get(f, 'No summary available')}" for f in plan.relevant_files
    )

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    relevant_nodes = [n for n in nodes if n["source_file"] in plan.relevant_files]
    key_classes = [n["label"] for n in relevant_nodes if n["type"] == "class"][:5]
    key_functions = [n["label"] for n in relevant_nodes if n["type"] in ("function", "method")][:5]
    key_routes = [n["label"] for n in relevant_nodes if n["type"] == "route"][:5]

    relevant_edges = [
        e
        for e in edges
        if any(e["source"].startswith(f) or e["target"].startswith(f) for f in plan.relevant_files)
        and e["relation"] in ("calls", "inherits", "handles", "implements")
    ]
    edge_str = "\n".join(
        f"  {e['source'].split('::')[-1]} "
        f"--{e['relation']}--> "
        f"{e['target'].split('::')[-1]}"
        for e in relevant_edges[:10]
    )

    user_message = f"""Scene: {plan.scene_name}
Title: {plan.title}
Description: {plan.description}

File summaries:
{relevant_summaries}

Key classes: {', '.join(key_classes) or 'none'}
Key functions: {', '.join(key_functions) or 'none'}
Key routes: {', '.join(key_routes) or 'none'}

Key relationships:
{edge_str or '  (none found)'}"""

    system = f"""You are a Manim CE expert. Generate ONE Manim scene.
STRICT RULES:
- Output ONLY valid Python code, zero markdown, zero backticks
- Class name must be exactly: {plan.scene_name}
- Inherit from Scene only: class {plan.scene_name}(Scene):
- First line must be: from manim import *
- NEVER use MathTex or Tex — use Text() only
- Use: Text, VGroup, Arrow, Rectangle, Circle,
       FadeIn, FadeOut, Write, Create, Transform
- Animate architecture as flowing diagrams
- Keep total duration under 30 seconds
- End with self.wait(1)"""

    for attempt in range(2):
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            message = await client.messages.create(
                model=settings.anthropic_model_smart,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            code = _strip_fences(message.content[0].text)
            if f"class {plan.scene_name}(Scene):" in code:
                return code
            # Scene name not found — retry once
        except Exception:
            break

    return _fallback_scene(plan.scene_name, plan.title)
