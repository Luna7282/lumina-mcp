import anthropic

from lumina_app.settings import settings

DOC_TYPES = {
    "readme": {
        "title": "README.md",
        "description": "Project overview, setup instructions, and quick start",
        "sections": [
            "Project Overview",
            "Architecture",
            "Prerequisites",
            "Installation",
            "Quick Start",
            "Project Structure",
            "Key Components",
        ],
    },
    "architecture": {
        "title": "ARCHITECTURE.md",
        "description": "Detailed technical architecture documentation",
        "sections": [
            "System Overview",
            "Component Breakdown",
            "Data Flow",
            "Key Design Decisions",
            "Dependencies",
            "Architectural Layers",
        ],
    },
    "api": {
        "title": "API.md",
        "description": "API endpoints and usage documentation",
        "sections": [
            "Base URL",
            "Authentication",
            "Endpoints",
            "Request/Response Examples",
            "Error Codes",
        ],
    },
    "onboarding": {
        "title": "ONBOARDING.md",
        "description": "New developer onboarding guide",
        "sections": [
            "Welcome",
            "Codebase Overview",
            "Key Files to Know",
            "How Requests Flow",
            "Common Tasks",
            "Where to Start",
        ],
    },
}


async def generate_docs(
    graph: dict,
    summaries: dict[str, str],
    doc_type: str = "readme",
    custom_instructions: str | None = None,
) -> str:
    """Generate markdown documentation from graph + summaries.

    Uses claude-sonnet for quality output. Returns a markdown string.
    """
    doc_config = DOC_TYPES.get(doc_type, DOC_TYPES["readme"])

    # Build context from graph
    god_nodes = graph.get("god_nodes", [])[:5]
    language_summary = graph.get("language_summary", {})
    community_summary = graph.get("community_summary", {})
    nodes = graph.get("nodes", [])

    # Extract routes for API docs
    routes = [n for n in nodes if n["type"] == "route"]

    # Extract models
    models = [n for n in nodes if n["type"] == "model"]

    # Build context string
    lang_str = ", ".join(f"{lang}: {count} file(s)" for lang, count in language_summary.items())

    god_str = "\n".join(
        f"- {n['label']} ({n['type']}) in {n['source_file']} — degree {n['degree']}" for n in god_nodes
    )

    community_str = "\n".join(
        f"- Community {cid}: {info['size']} components, top: {', '.join(info['top_nodes'][:3])}"
        for cid, info in community_summary.items()
    )

    summaries_str = "\n".join(f"### {path}\n{summary}" for path, summary in list(summaries.items())[:30])

    routes_str = (
        "\n".join(f"- {n['label']} ({n['source_file']} {n['source_location']})" for n in routes[:20])
        or "No routes detected"
    )

    models_str = "\n".join(f"- {n['label']} ({n['source_file']})" for n in models[:20]) or "No models detected"

    custom_note = f"\n\nAdditional requirements:\n{custom_instructions}" if custom_instructions else ""

    user_message = f"""Generate {doc_config['title']} documentation.

Languages: {lang_str}

Most important components (god nodes):
{god_str}

Architectural communities:
{community_str}

API Routes:
{routes_str}

Data Models:
{models_str}

File summaries:
{summaries_str}{custom_note}

Required sections: {', '.join(doc_config['sections'])}"""

    system = f"""You are a technical writer generating {doc_config['title']}.
Purpose: {doc_config['description']}

Rules:
- Output ONLY valid markdown, no preamble
- Use proper markdown headers (# ## ###)
- Be specific — use actual class names, file names, route paths
- Do not make up information not present in the summaries
- Keep it concise but complete
- For code examples, use ```language fences
- Generate all required sections even if some have limited data"""

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model_smart,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        # Handle thinking blocks — content[0] may be a `thinking` block
        # rather than the answer, so find the first type=="text" block.
        for block in message.content:
            if block.type == "text":
                return block.text.strip()
        return "# Documentation\n\nFailed to generate documentation."
    except Exception as e:
        return f"# Documentation\n\nError generating docs: {str(e)}"
