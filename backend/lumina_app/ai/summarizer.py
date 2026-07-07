import asyncio

import anthropic

from lumina_app.settings import settings


def _extract_text(message) -> str:
    """Return the first text block's content.

    claude-sonnet-5 (and other 4.6+ models) run adaptive thinking by
    default, so content[0] is often a `thinking` block rather than the
    answer — content[0].text is then None, not a "no response" signal.
    Find the first block that's actually type=="text" instead of assuming
    position 0.
    """
    for block in message.content:
        if block.type == "text":
            return block.text
    return ""


async def summarize_file(
    path: str,
    nodes: list[dict],
    edges: list[dict],
) -> str:
    classes = [n["label"] for n in nodes if n["type"] == "class"]
    functions = [n["label"] for n in nodes if n["type"] in ("function", "method")]
    routes = [n["label"] for n in nodes if n["type"] == "route"]
    models = [n["label"] for n in nodes if n["type"] == "model"]
    calls_to = [
        e["target"].split("::")[-1]
        for e in edges
        if e["source"].startswith(path) and e["relation"] == "calls"
    ]
    inherits_from = [
        e["target"].split("::")[-1]
        for e in edges
        if e["source"].startswith(path) and e["relation"] == "inherits"
    ]

    context_parts = [f"File: {path}"]
    if classes:
        context_parts.append(f"Classes: {', '.join(classes[:5])}")
    if functions:
        context_parts.append(f"Functions: {', '.join(functions[:8])}")
    if routes:
        context_parts.append(f"API routes: {', '.join(routes[:5])}")
    if models:
        context_parts.append(f"Data models: {', '.join(models[:5])}")
    if calls_to:
        context_parts.append(f"Calls: {', '.join(set(calls_to[:5]))}")
    if inherits_from:
        context_parts.append(f"Inherits from: {', '.join(inherits_from)}")

    context = "\n".join(context_parts)

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model_fast,
            max_tokens=150,
            system=(
                "Summarize what this code file does in 2-3 sentences. "
                "Be specific about its main classes, functions, and purpose. "
                "Output only the summary, no preamble."
            ),
            messages=[{"role": "user", "content": context}],
        )
        return _extract_text(message).strip()
    except Exception:
        parts = []
        if classes:
            parts.append(f"defines {len(classes)} class(es): {', '.join(classes[:3])}")
        if routes:
            parts.append(f"exposes {len(routes)} route(s): {', '.join(routes[:3])}")
        if functions:
            parts.append(f"contains {len(functions)} function(s)")
        return f"{path}: " + ("; ".join(parts) if parts else "utility file")


async def summarize_codebase(
    graph: dict,
    db_files: list,
    db,
) -> dict[str, str]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    nodes_by_file: dict[str, list] = {}
    for node in nodes:
        fp = node["source_file"]
        nodes_by_file.setdefault(fp, []).append(node)

    semaphore = asyncio.Semaphore(5)
    summaries: dict[str, str] = {}

    async def process_file(db_file):
        path = db_file.path
        if db_file.summary:
            summaries[path] = db_file.summary
            return
        async with semaphore:
            file_nodes = nodes_by_file.get(path, [])
            summary = await summarize_file(path, file_nodes, edges)
            summaries[path] = summary
            db_file.summary = summary

    await asyncio.gather(*[process_file(f) for f in db_files])
    return summaries
