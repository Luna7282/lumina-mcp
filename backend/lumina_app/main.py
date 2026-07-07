import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumina_app.database import create_all_tables, get_db
from lumina_app.extract.cache import codebase_hash, compute_hashes
from lumina_app.extract.cluster import detect_communities, get_community_summary
from lumina_app.extract.dispatch import extract_all
from lumina_app.extract.graph import build_graph, get_god_nodes, get_language_summary
from lumina_app.models import Codebase, CodebaseFile
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
    """Accept files, extract a multi-language code graph, store in DB, return codebase_id."""
    # 1. Compute content hash for deduplication
    content_hash = codebase_hash(request.files)

    # 2. Check if already analyzed (return cached result)
    result = await db.execute(select(Codebase).where(Codebase.content_hash == content_hash))
    existing = result.scalar_one_or_none()
    if existing is not None:
        stored_graph = existing.graph
        return AnalyzeResponse(
            codebase_id=str(existing.id),
            name=existing.name,
            file_count=existing.file_count,
            node_count=len(stored_graph.get("nodes", [])),
            edge_count=len(stored_graph.get("edges", [])),
            god_nodes=stored_graph.get("god_nodes", []),
            community_count=len(set(stored_graph.get("communities", {}).values())),
            language_summary=existing.language_summary,
            cached=True,
        )

    # 3. Extract, build graph, cluster (no AI — pure static + graph analysis)
    extractions = extract_all(request.files)
    G = build_graph(extractions)
    communities = detect_communities(G)
    community_summary = get_community_summary(G, communities)
    god_nodes = get_god_nodes(G)
    language_summary = get_language_summary(extractions)
    file_hashes = compute_hashes(request.files)

    nodes_payload = [{"id": node_id, **data} for node_id, data in G.nodes(data=True)]
    edges_payload = [
        # G is undirected — NetworkX may report a pair as (u, v) or (v, u)
        # depending on iteration order, so read the true direction from the
        # edge's own "source"/"target" attributes (set in build_graph)
        # rather than trusting the yielded tuple order.
        {
            "source": data["source"],
            "target": data["target"],
            "relation": data["relation"],
            "confidence": data["confidence"],
        }
        for _, _, data in G.edges(data=True)
    ]

    # 4. Store in DB
    codebase = Codebase(
        name=request.name,
        source="api",
        content_hash=content_hash,
        file_count=len(extractions),
        language_summary=language_summary,
        graph={
            "nodes": nodes_payload,
            "edges": edges_payload,
            "communities": communities,
            "community_summary": community_summary,
            "god_nodes": god_nodes,
            "language_summary": language_summary,
            "file_hashes": file_hashes,
        },
    )
    db.add(codebase)
    # Flush so codebase.id (a client-side default) is assigned before we
    # reference it as a foreign key on the per-file rows below.
    await db.flush()

    # 5. Store individual file records, grouped from the extracted nodes
    for path, extraction in extractions.items():
        classes = [n.label for n in extraction.nodes if n.type in ("class", "model")]
        functions = [n.label for n in extraction.nodes if n.type in ("function", "method")]
        routes = [n.label for n in extraction.nodes if n.type == "route"]
        imports = [n.label for n in extraction.nodes if n.type == "import"]
        db.add(
            CodebaseFile(
                codebase_id=codebase.id,
                path=path,
                language=extraction.language,
                exports=[],
                imports=imports,
                classes=classes,
                functions=functions,
                routes=routes,
                models=[n.label for n in extraction.nodes if n.type == "model"],
                complexity_score=float(len(functions)),
            )
        )

    await db.commit()

    return AnalyzeResponse(
        codebase_id=str(codebase.id),
        name=codebase.name,
        file_count=codebase.file_count,
        node_count=len(nodes_payload),
        edge_count=len(edges_payload),
        god_nodes=god_nodes,
        community_count=len(set(communities.values())),
        language_summary=language_summary,
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
