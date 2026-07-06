import hashlib
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumina_app.database import create_all_tables, get_db
from lumina_app.models import Codebase, CodebaseFile
from lumina_app.parser.graph import build_graph
from lumina_app.schemas import AnalyzeRequest, AnalyzeResponse, CodebaseRead
from lumina_app.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — tables auto-created in dev; use alembic migrations in production
    if settings.environment != "production":
        await create_all_tables()
    yield
    # shutdown


app = FastAPI(title="Lumina API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lumina"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_codebase(
    request: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Accept files, build graph, store in DB, return codebase_id."""
    # 1. Compute content hash for deduplication (sorted for determinism)
    content = json.dumps(dict(sorted(request.files.items())), sort_keys=True)
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # 2. Check if already analyzed (return cached result)
    result = await db.execute(select(Codebase).where(Codebase.content_hash == content_hash))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return AnalyzeResponse(
            codebase_id=str(existing.id),
            name=existing.name,
            file_count=existing.file_count,
            language_summary=existing.language_summary,
            layers=existing.graph.get("layers", {}),
            cached=True,
        )

    # 3. Build graph (no AI — pure static analysis)
    graph = build_graph(request.files)

    # 4. Store in DB
    codebase = Codebase(
        name=request.name,
        source="api",
        content_hash=content_hash,
        file_count=len(graph.files),
        language_summary=graph.language_summary,
        graph={
            "layers": graph.layers,
            "edges": [
                {"source": e.source, "target": e.target, "kind": e.kind}
                for e in graph.edges
            ],
            "files": {
                path: {
                    "language": node.language,
                    "exports": node.exports,
                    "imports": node.imports,
                    "classes": node.classes,
                    "functions": node.functions,
                    "routes": node.routes,
                    "models": node.models,
                    "complexity_score": node.complexity_score,
                }
                for path, node in graph.files.items()
            },
        },
    )
    db.add(codebase)
    # Flush so codebase.id (a client-side default) is assigned before we
    # reference it as a foreign key on the per-file rows below.
    await db.flush()

    # 5. Store individual file records
    for path, node in graph.files.items():
        db.add(
            CodebaseFile(
                codebase_id=codebase.id,
                path=path,
                language=node.language,
                exports=node.exports,
                imports=node.imports,
                classes=node.classes,
                functions=node.functions,
                routes=node.routes,
                models=node.models,
                complexity_score=node.complexity_score,
            )
        )

    await db.commit()

    return AnalyzeResponse(
        codebase_id=str(codebase.id),
        name=codebase.name,
        file_count=codebase.file_count,
        language_summary=codebase.language_summary,
        layers=graph.layers,
        cached=False,
    )


@app.post("/api/explain")
async def explain_codebase():
    """Generate video explanation for a codebase."""
    return {"status": "not_implemented"}


@app.post("/api/docs")
async def generate_docs():
    """Generate markdown documentation for a codebase."""
    return {"status": "not_implemented"}


@app.get("/api/codebase/{codebase_id}", response_model=CodebaseRead)
async def get_codebase(codebase_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get codebase graph and metadata."""
    result = await db.execute(select(Codebase).where(Codebase.id == codebase_id))
    codebase = result.scalar_one_or_none()
    if codebase is None:
        raise HTTPException(status_code=404, detail="codebase not found")
    return codebase
