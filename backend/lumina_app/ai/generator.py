import anthropic

from lumina_app.ai.planner import ScenePlan
from lumina_app.settings import settings

SCENE_PATTERNS = {
    "overview": """
VISUAL PATTERN for architecture overview:
- Start: project title Text fades in center, then moves to top
- Middle: show 2-4 horizontal layers as colored Rectangles stacked vertically:
    Layer colors: BLUE_E (frontend/UI), GREEN_E (API/routes),
                  YELLOW_E (services/logic), RED_E (database/models)
  Each layer: Rectangle with Text label inside, animate Create() bottom-up
  Between layers: Arrow pointing down, animate with GrowArrow()
- Highlight: the most-connected god node pulses with a surrounding Circle
- End: all elements stay visible, self.wait(1)
""",
    "flow": """
VISUAL PATTERN for data/request flow:
- Show 4-6 components as labeled rectangles arranged left-to-right
- Animate a moving dot (small Circle) traveling along arrows between them
  Use MoveAlongPath or sequential moves with rate_func=smooth
- Each arrow has a small label (calls/handles/imports) above it
- Use color coding: entry points in BLUE, processing in GREEN, storage in RED
- End with all arrows visible showing the complete flow path
""",
    "models": """
VISUAL PATTERN for data models / class hierarchy:
- Show classes as rectangles with class name at top, fields listed below
- Draw inheritance arrows (hollow arrowhead style) from child to parent
- Use WHITE for base classes, BLUE for models, GREEN for mixins
- Arrange in a tree: base class at top, subclasses below
- Animate: base appears first, then subclasses appear one by one with arrows
""",
    "components": """
VISUAL PATTERN for component/community detail:
- Arrange 3-7 files as labeled circles in a cluster
- Size each circle proportional to its degree (more connections = bigger)
- Draw edges between circles with different colors per relation type:
    calls: BLUE arrows, imports: GREEN arrows, inherits: YELLOW arrows
- The god node circle is WHITE/brightest
- Animate: circles appear, then edges draw in one by one
- End: rotate the whole cluster slowly for 2 seconds
""",
    "default": """
VISUAL PATTERN (general):
- Title at top, content in center
- Use at least 3 different Manim objects (Text, Rectangle, Arrow, Circle)
- Minimum 3 distinct animations (not just FadeIn everything at once)
- Show relationships with directional arrows
- Use color to distinguish different types of components
- Keep text labels short (max 20 chars) and legible (font_size >= 24)
""",
}


def _get_scene_pattern(scene_name: str, description: str) -> str:
    """Pick the most relevant visual pattern for this scene."""
    name_lower = scene_name.lower()
    desc_lower = description.lower()
    if any(w in name_lower + desc_lower for w in ["overview", "architecture", "structure"]):
        return SCENE_PATTERNS["overview"]
    if any(w in name_lower + desc_lower for w in ["flow", "request", "pipeline", "sequence"]):
        return SCENE_PATTERNS["flow"]
    if any(w in name_lower + desc_lower for w in ["model", "schema", "class", "inherit", "entity"]):
        return SCENE_PATTERNS["models"]
    if any(w in name_lower + desc_lower for w in ["component", "module", "community", "cluster"]):
        return SCENE_PATTERNS["components"]
    return SCENE_PATTERNS["default"]


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
    custom_instructions: str | None = None,
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

    system = f"""You are a Manim CE expert creating educational animations.
Generate ONE Manim scene class that visually explains the described concept.

STRICT RULES:
- Output ONLY valid Python code. Zero markdown. Zero backticks.
- Class name must be exactly: {plan.scene_name}
- class {plan.scene_name}(Scene):
- First line: from manim import *
- NEVER use MathTex or Tex — ONLY Text()
- NEVER use font_size below 20 (too small to read)
- Keep all text under 25 characters per label
- Total animation duration: 15-25 seconds
- End with self.wait(1)

AVAILABLE MANIM OBJECTS (use these, nothing else):
  Text, VGroup, Arrow, CurvedArrow, Rectangle, RoundedRectangle,
  Circle, Dot, Line, DashedLine, Polygon, Triangle

AVAILABLE ANIMATIONS (be creative, use at least 4 different ones):
  Create, Write, FadeIn, FadeOut, GrowArrow, Transform,
  MoveAlongPath, AnimationGroup, LaggedStart, Succession,
  Flash, Circumscribe, Indicate, ApplyWave

COLOR PALETTE (use these for visual clarity):
  BLUE_E, GREEN_E, YELLOW_E, RED_E, PURPLE_E,  # dark/background
  BLUE_C, GREEN_C, YELLOW_C, RED_C, WHITE,      # main elements
  BLUE_A, GREEN_A, YELLOW_A, RED_A, GRAY_A      # light/accent

VISUAL PATTERN TO FOLLOW:
{_get_scene_pattern(plan.scene_name, plan.description)}

QUALITY CHECKLIST (your output MUST satisfy all):
[ ] At least 4 distinct named Manim objects (not just Text everywhere)
[ ] At least 4 different animation types used
[ ] Color coding distinguishes different component types
[ ] Relationships shown as directional arrows, not just boxes
[ ] Text labels are short and readable (font_size >= 24)
[ ] Animation tells a story: introduce → show relationships → conclude
"""

    if custom_instructions:
        system += f"\n\nUser's custom requirements:\n{custom_instructions}"

    for attempt in range(2):
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            message = await client.messages.create(
                model=settings.anthropic_model_smart,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            code = _strip_fences(_extract_text(message))
            if f"class {plan.scene_name}(Scene):" not in code:
                # Scene name not found — retry once
                continue
            try:
                compile(code, f"<scene:{plan.scene_name}>", "exec")
            except SyntaxError:
                # Response likely got truncated by max_tokens — retry once
                continue
            return code
        except Exception:
            break

    return _fallback_scene(plan.scene_name, plan.title)
