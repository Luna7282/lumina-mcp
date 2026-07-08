import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumina_app.ai.documenter import DOC_TYPES, generate_docs
from lumina_app.ai.generator import generate_scene
from lumina_app.ai.planner import plan_visualization
from lumina_app.ai.summarizer import summarize_codebase
from lumina_app.database import create_all_tables, get_db
from lumina_app.extract.cache import codebase_hash, compute_hashes
from lumina_app.extract.cluster import detect_communities, get_community_summary
from lumina_app.extract.dispatch import extract_all
from lumina_app.extract.graph import build_graph, get_god_nodes, get_language_summary
from lumina_app.models import Codebase, CodebaseFile, CodebaseVideo, OnboardingPackage
from lumina_app.onboarding import generate_package
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


class ExplainRequest(BaseModel):
    codebase_id: str
    focus: str | None = None
    quality: str = "low"
    custom_instructions: str | None = None


class ExplainResponse(BaseModel):
    video_id: str
    status: str
    video_url: str | None = None
    scenes: list[str]
    codebase_id: str


@app.post("/api/explain", response_model=ExplainResponse)
async def explain_codebase(
    request: ExplainRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Generate video explanation for a codebase: summarize files, plan
    scenes, generate Manim code, then render in the background."""
    codebase = await db.get(Codebase, uuid.UUID(request.codebase_id))
    if not codebase:
        raise HTTPException(404, "Codebase not found")

    # Load file records from DB
    files_result = await db.execute(select(CodebaseFile).where(CodebaseFile.codebase_id == codebase.id))
    db_files = files_result.scalars().all()

    # Summarize (uses cache)
    summaries = await summarize_codebase(codebase.graph, db_files, db, request.custom_instructions)
    await db.commit()

    # Plan scenes
    scene_plans = await plan_visualization(
        codebase.graph, summaries, request.focus, request.custom_instructions
    )

    # Generate Manim code
    scene_codes = []
    for plan in scene_plans:
        code = await generate_scene(plan, summaries, codebase.graph, request.custom_instructions)
        scene_codes.append(code)

    # Combine — remove duplicate "from manim import *" lines
    combined_parts = []
    header_added = False
    for code in scene_codes:
        lines = code.split("\n")
        for line in lines:
            if line.strip() == "from manim import *":
                if not header_added:
                    combined_parts.append(line)
                    header_added = True
                # skip duplicate imports
            else:
                combined_parts.append(line)
        combined_parts.append("")  # blank line between scenes

    combined = "\n".join(combined_parts)

    # Create video record
    video = CodebaseVideo(
        codebase_id=codebase.id,
        focus=request.focus or "overview",
        manim_code=combined,
        status="rendering",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    # Render in background. render_and_save opens its own DB session rather
    # than reusing this request's `db` — by the time a BackgroundTask runs,
    # the request-scoped session from Depends(get_db) has already been
    # closed, so passing it through here would risk an intermittent
    # "session is closed" failure once rendering actually completes.
    video_id = str(video.id)
    quality = request.quality

    async def do_render():
        from lumina_app.renderer import render_and_save

        await render_and_save(video_id, combined, quality)

    background_tasks.add_task(do_render)

    return ExplainResponse(
        video_id=video_id,
        status="rendering",
        scenes=[p.scene_name for p in scene_plans],
        codebase_id=request.codebase_id,
    )


@app.get("/api/video/{video_id}")
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await db.get(CodebaseVideo, uuid.UUID(video_id))
    if not video:
        raise HTTPException(404, "Video not found")
    return {
        "video_id": str(video.id),
        "status": video.status,
        "video_url": video.video_url,
        "focus": video.focus,
        "codebase_id": str(video.codebase_id),
        "created_at": video.created_at.isoformat(),
        "error_message": video.error_message,
    }


class DocsRequest(BaseModel):
    codebase_id: str
    doc_type: str = "readme"  # readme|architecture|api|onboarding
    custom_instructions: str | None = None

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v):
        if v not in DOC_TYPES:
            raise ValueError(f"doc_type must be one of: {list(DOC_TYPES.keys())}")
        return v


class DocsResponse(BaseModel):
    codebase_id: str
    doc_type: str
    filename: str
    content: str  # the generated markdown
    word_count: int


@app.post("/api/docs", response_model=DocsResponse)
async def generate_documentation(
    request: DocsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate markdown documentation for a codebase."""
    codebase = await db.get(Codebase, uuid.UUID(request.codebase_id))
    if not codebase:
        raise HTTPException(404, "Codebase not found")

    # Load cached file summaries
    files_result = await db.execute(select(CodebaseFile).where(CodebaseFile.codebase_id == codebase.id))
    db_files = files_result.scalars().all()

    # Use cached summaries, generate missing ones
    summaries = await summarize_codebase(codebase.graph, db_files, db)
    await db.commit()

    # Generate docs
    doc_config = DOC_TYPES[request.doc_type]
    markdown = await generate_docs(
        graph=codebase.graph,
        summaries=summaries,
        doc_type=request.doc_type,
        custom_instructions=request.custom_instructions,
    )

    return DocsResponse(
        codebase_id=request.codebase_id,
        doc_type=request.doc_type,
        filename=doc_config["title"],
        content=markdown,
        word_count=len(markdown.split()),
    )


@app.get("/api/codebase/{codebase_id}", response_model=CodebaseRead)
async def get_codebase(codebase_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get codebase graph and metadata."""
    result = await db.execute(select(Codebase).where(Codebase.id == codebase_id))
    codebase = result.scalar_one_or_none()
    if codebase is None:
        raise HTTPException(status_code=404, detail="codebase not found")
    return codebase


class OnboardRequest(BaseModel):
    codebase_id: str
    package_type: str = "full"  # full|quick|technical
    custom_instructions: str | None = None
    quality: str = "low"

    @field_validator("package_type")
    @classmethod
    def validate_package_type(cls, v):
        if v not in ("full", "quick", "technical"):
            raise ValueError("package_type must be full|quick|technical")
        return v


class OnboardResponse(BaseModel):
    package_id: str
    status: str
    codebase_id: str
    videos: list[dict]
    docs: list[dict]


@app.post("/api/onboard", response_model=OnboardResponse)
async def create_onboarding_package(
    request: OnboardRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Kick off a full onboarding package: a multi-scene overview video
    covering the whole codebase, one deep-dive video per top-level folder,
    and the package_type's docs — all planned and generated in the
    background. Folder/video planning depends on the same graph/summaries
    the background task already needs, so it happens there rather than
    here, keeping this endpoint fast; the package starts with empty
    videos/docs lists that fill in once planning completes."""
    codebase = await db.get(Codebase, uuid.UUID(request.codebase_id))
    if not codebase:
        raise HTTPException(404, "Codebase not found")

    # Load file records and summaries (cached)
    files_result = await db.execute(select(CodebaseFile).where(CodebaseFile.codebase_id == codebase.id))
    db_files = files_result.scalars().all()
    summaries = await summarize_codebase(codebase.graph, db_files, db)
    await db.commit()

    package = OnboardingPackage(
        codebase_id=codebase.id,
        package_type=request.package_type,
        status="generating",
        videos=[],
        docs=[],
        custom_instructions=request.custom_instructions,
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)

    package_id = str(package.id)

    # Plan and generate everything in the background — see
    # render_and_save's docstring for why this can't reuse the
    # request-scoped `db` session.
    background_tasks.add_task(
        generate_package,
        package_id,
        codebase.graph,
        summaries,
        request.package_type,
        request.custom_instructions,
        request.quality,
    )

    return OnboardResponse(
        package_id=package_id,
        status="generating",
        codebase_id=request.codebase_id,
        videos=[],
        docs=[],
    )


@app.get("/api/package/{package_id}")
async def get_package(package_id: str, db: AsyncSession = Depends(get_db)):
    package = await db.get(OnboardingPackage, uuid.UUID(package_id))
    if not package:
        raise HTTPException(404, "Package not found")
    return {
        "package_id": str(package.id),
        "status": package.status,
        "codebase_id": str(package.codebase_id),
        "package_type": package.package_type,
        "videos": package.videos,
        "docs": [
            {
                "doc_type": d["doc_type"],
                "filename": d["filename"],
                "status": d["status"],
                "folder": d.get("folder"),
                # Only include content once done — could be large.
                "content": d.get("content") if d["status"] == "done" else None,
                "word_count": len(d["content"].split()) if d.get("content") else 0,
            }
            for d in package.docs
        ],
        "created_at": package.created_at.isoformat(),
        "completed_at": package.completed_at.isoformat() if package.completed_at else None,
    }
