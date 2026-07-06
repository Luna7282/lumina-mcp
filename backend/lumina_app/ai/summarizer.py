import anthropic

from lumina_app.parser.base import FileNode
from lumina_app.settings import settings

_SYSTEM_PROMPT = (
    "You summarize a single source file for a codebase-intelligence tool. "
    "Given the file's parsed metadata and a content excerpt, write a concise "
    "1-3 sentence summary of what the file does. Do not restate the metadata "
    "verbatim — explain its purpose and role in the codebase."
)


def _build_prompt(node: FileNode, content: str, max_chars: int = 4000) -> str:
    excerpt = content[:max_chars]
    return (
        f"Path: {node.path}\n"
        f"Language: {node.language}\n"
        f"Classes: {', '.join(node.classes) or 'none'}\n"
        f"Functions: {', '.join(node.functions) or 'none'}\n"
        f"Routes: {', '.join(node.routes) or 'none'}\n"
        f"Models: {', '.join(node.models) or 'none'}\n\n"
        f"Content excerpt:\n{excerpt}"
    )


async def summarize_file(node: FileNode, content: str) -> str:
    """Generate a short natural-language summary of a file using the fast model."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_model_fast,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_prompt(node, content)}],
    )
    return next((b.text for b in response.content if b.type == "text"), "").strip()
