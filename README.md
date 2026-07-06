# Lumina

Codebase intelligence platform that analyzes codebases, builds dependency
graphs, and generates animated explainer videos using the manimstudio
rendering API.

## Structure

- `backend/` — FastAPI service: static analysis (`lumina_app/parser`), AI
  pipeline (`lumina_app/ai`), rendering (`lumina_app/renderer.py`).
- `frontend/` — React/Vite scaffold (build out later).
- `infra/` — local dev infrastructure (Postgres + Redis via Docker Compose).

## Backend quickstart

```bash
cd backend
cp .env.example .env   # fill in ANTHROPIC_API_KEY / MANIMSTUDIO_API_KEY
uv sync --extra dev
uv run uvicorn lumina_app.main:app --reload
```

Health check: `GET http://localhost:8000/health`

### Tests

```bash
cd backend
uv run pytest tests/ -q
```

### Database

```bash
cd infra
docker compose up -d
```

Then, from `backend/`:

```bash
uv run alembic upgrade head
```

## API (stubs — implemented incrementally)

- `POST /api/analyze` — accept files, build a `CodebaseGraph`, persist it, return a `codebase_id`.
- `POST /api/explain` — generate an animated video explanation for a codebase.
- `POST /api/docs` — generate markdown documentation for a codebase.
- `GET /api/codebase/{codebase_id}` — fetch codebase graph and metadata.

## How analysis works

1. `lumina_app.parser.build_graph` statically parses each file (Python via
   `ast`, TS/JS/TSX/JSX via `tree-sitter`) into a `CodebaseGraph` — no AI
   calls.
2. `lumina_app.ai.summarizer` calls a fast model (`claude-haiku-4-5`) to
   summarize individual files.
3. `lumina_app.ai.planner` calls a smart model (`claude-sonnet-5`) to turn the
   graph into a scene-by-scene video storyboard.
4. `lumina_app.ai.generator` turns the storyboard into Manim scene code.
5. `lumina_app.renderer.ManimRenderer` submits that code to the manimstudio
   rendering API and polls for the resulting video.
