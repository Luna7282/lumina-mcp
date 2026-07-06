import anthropic

from lumina_app.settings import settings

_SYSTEM_PROMPT = (
    "You generate Manim (Community Edition) scene code for a codebase "
    "explainer video. Given a storyboard plan (scenes with titles, "
    "narration, and highlighted files/layers), write a single self-contained "
    "Python module defining one Manim `Scene` subclass named `ExplainerScene` "
    "that visualizes the plan — animated diagrams for architecture/layers, "
    "on-screen text for narration beats. Respond with Python code only, no "
    "markdown fences, no commentary."
)


def _plan_prompt(plan: dict) -> str:
    lines = []
    for i, scene in enumerate(plan.get("scenes", []), start=1):
        lines.append(
            f"Scene {i}: {scene.get('title', '')}\n"
            f"  Narration: {scene.get('narration', '')}\n"
            f"  Highlights: {', '.join(scene.get('highlights', []))}"
        )
    return "\n".join(lines)


async def generate_manim_scene(plan: dict) -> str:
    """Generate Manim scene source code from a storyboard plan using the smart model."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_model_smart,
        max_tokens=16000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _plan_prompt(plan)}],
    )
    return next((b.text for b in response.content if b.type == "text"), "").strip()
