import anthropic

from lumina_app.ai.planner import ScenePlan
from lumina_app.settings import settings

SCENE_PATTERNS = {
    "overview": """
VISUAL PATTERN for architecture overview — show a REQUEST JOURNEY, not a static diagram:
1. Title fades in at top (about 2 seconds), staying in the title zone (see LAYOUT RULES)
2. Show components one at a time, top to bottom, each with Create():
   - Each component: RoundedRectangle + Text label inside
   - Color by type: BLUE_E=frontend, GREEN_E=API/routes, YELLOW_E=services, RED_E=database/storage
   - Spacing: exactly 1.2 units between centers (use the exact y positions in LAYOUT RULES)
   - Maximum 4 components
3. After all components are shown, animate a REQUEST PACKET traveling through them:
   - A small glowing Dot starts above the top component
   - Move it DOWN through each component in turn (MoveAlongPath or sequential
     .animate moves), pausing briefly at each one
   - At each component: briefly Indicate() it or flash a surrounding glow
   - A small label appears next to the dot at each step, e.g.:
     "Request" -> "Auth Check" -> "Quota Check" -> "Render" -> "Response"
     (choose labels that match what this codebase's components actually do)
4. Final state: all components remain visible, the dot resting at the bottom —
   the complete journey stays on screen, self.wait(1)
This tells a STORY: a request enters and travels through the system.
Do not just place static boxes and stop — the journey IS the animation.
""",
    "flow": """
VISUAL PATTERN for data/request flow — a sequence-diagram style animation:
1. Title at top (title zone from LAYOUT RULES)
2. Show 3-5 actors as vertical columns (not horizontal boxes):
   - Each actor: a labeled rectangle at the top of a vertical DashedLine
   - Arrange left to right across the screen
   - Actor width: 2.5 units, spacing: 2.8 units apart
   - First actor at x=-5, last at x=5 (for 4 actors)
3. Animate messages as horizontal arrows between actors' lifelines:
   - Each arrow appears one at a time (Create or GrowArrow)
   - A small label describing the message sits ON the arrow (see ARROW LABELS)
   - Arrows animate left-to-right or right-to-left depending on message direction
   - Use different colors: BLUE for requests, GREEN for responses, RED for errors
4. Show AT LEAST 4 message arrows so the interaction reads as a complete
   round trip, not a single call
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

LAYOUT_RULES = """
LAYOUT RULES (strictly follow these):
- Manim frame is 14.2 units wide × 8 units tall
- Reserve top 1.5 units for title (y=3.5 to y=4.5)
- Content area: y from -3.0 to 3.0 (6 units tall)
- Maximum 4 layers/boxes in one scene
- Each box height: 0.8 units, spacing: 1.2 units between centers
- First box center: y=2.0, second: y=0.8, third: y=-0.4, fourth: y=-1.6
- Box width: 8 units max
- All text font_size between 24 and 32
- Never place anything below y=-3.5 or above y=4.0
- If more than 4 items: show only the 4 most important ones
"""

ARROW_LABEL_RULES = """
ARROW LABEL RULES:
- For labels on arrows between components, place them INSIDE the arrow's
  path, not floating beside it
- Use font_size=20, color=GRAY_A
- Position at the arrow's midpoint, offset up by 0.15 units
  (e.g. label.move_to(arrow.get_center() + UP * 0.15))
- Keep label text under 15 characters
"""


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
{LAYOUT_RULES}
{ARROW_LABEL_RULES}
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
