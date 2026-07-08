# Lumina MCP Server

An MCP (Model Context Protocol) server that exposes the Lumina backend as
tools for Claude Code and other MCP clients — analyze codebases, generate
animated explainer videos, and generate markdown documentation, all without
leaving your agent session.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- The Lumina backend running and reachable (defaults to `http://localhost:8000`)

## Installation

Install dependencies:

```bash
cd mcp
uv sync
```

### Add to Claude Code

Via `~/.claude.json`:

```json
{
  "mcpServers": {
    "lumina": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/absolute/path/to/lumina/mcp",
      "env": { "LUMINA_API_URL": "http://localhost:8000" }
    }
  }
}
```

Or via the CLI:

```bash
claude mcp add lumina -- uv run python /path/to/lumina/mcp/server.py
```

## Tools

| Tool | Description |
| --- | --- |
| `analyze_codebase` | Parse and analyze a codebase from in-memory file contents, returning a dependency graph. |
| `explain_codebase` | Full pipeline — analyze, summarize, plan scenes, render — returning an animated explainer video URL. |
| `analyze_local_path` | Analyze a local project directory directly (most efficient for large repos; optionally also generates a video). |
| `generate_docs` | Generate markdown documentation (readme / architecture / api / onboarding) for an analyzed codebase. |
| `get_video_status` | Poll the status of an in-progress video render. |
| `get_codebase_graph` | Retrieve the stored dependency graph for a codebase. |
| `list_supported_languages` | List the languages Lumina can parse via tree-sitter. |

## Configuration

| Env var | Default | Description |
| --- | --- | --- |
| `LUMINA_API_URL` | `http://localhost:8000` | Base URL of the Lumina backend API. |

## Development

```bash
uv run pytest tests/ -q
```
