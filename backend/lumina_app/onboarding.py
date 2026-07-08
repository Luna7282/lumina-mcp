import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from lumina_app.ai.documenter import DOC_TYPES, generate_docs
from lumina_app.ai.generator import generate_scene
from lumina_app.ai.planner import ScenePlan, detect_folders, plan_folder_videos
from lumina_app.renderer import submit_render

logger = logging.getLogger(__name__)

# Which main doc types each package_type bundles, beyond per-folder READMEs.
PACKAGE_DOC_TYPES: dict[str, list[str]] = {
    "full": ["architecture", "onboarding", "api"],
    "quick": ["readme"],
    "technical": ["architecture", "api"],
}

# Max top-level folders that get their own deep-dive video + README.
# "quick" skips folder deep-dives entirely — one overview video + README.
PACKAGE_FOLDER_LIMITS: dict[str, int] = {"full": 5, "quick": 0, "technical": 3}

# Folder videos render in parallel with several others, so each gets a
# shorter per-video timeout than the overview render.
VIDEO_RENDER_TIMEOUT = 600.0

# The overview is a multi-scene render covering the whole codebase — much
# bigger than a single folder video, so it gets a longer timeout.
OVERVIEW_RENDER_TIMEOUT = 1800.0

# Per-package mutex serializing videos/docs JSON updates (see
# _update_package_item). Grows by one tiny entry per package generated in
# this process's lifetime — not cleaned up, but negligible at this volume.
_package_locks: dict[str, asyncio.Lock] = {}


def _get_package_lock(package_id: str) -> asyncio.Lock:
    lock = _package_locks.get(package_id)
    if lock is None:
        lock = asyncio.Lock()
        _package_locks[package_id] = lock
    return lock


async def _update_package_item(package_id: str, field: str, idx: int, updates: dict) -> None:
    """Atomically patch one item in the package's videos/docs JSON list.

    A package's videos and docs all render/generate concurrently
    (generate_package fires them via asyncio.gather), each in its own DB
    session. Without synchronization, two sibling tasks that both read the
    list before either commits would each write back a full copy based on
    their own stale read — the later commit silently overwrites the
    earlier one's update (a lost-update race).

    generate_package's tasks all run in the same process, so an
    asyncio.Lock keyed by package_id is enough to serialize them and is
    what actually prevents the race today. SELECT ... FOR UPDATE adds a
    second layer that also holds across multiple worker processes hitting
    the same Postgres row (it no-ops on SQLite, which has no row-level
    locking — fine for tests, which rely on the asyncio.Lock instead).

    Also replaces (rather than mutates) the item dict at `idx`: JSON
    columns aren't tracked for in-place mutation, so SQLAlchemy decides
    whether to emit an UPDATE by comparing the old and new Python values.
    `items[idx].update(updates)` mutates the same dict object still
    referenced by the ORM's tracked "old" value (a shallow list copy
    doesn't copy the inner dicts) — so old and new end up identical by the
    time SQLAlchemy compares them, the column is never marked dirty, and
    the write silently never reaches the database.
    """
    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import OnboardingPackage

    async with _get_package_lock(package_id):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OnboardingPackage).where(OnboardingPackage.id == UUID(package_id)).with_for_update()
            )
            pkg = result.scalar_one_or_none()
            if pkg:
                items = list(getattr(pkg, field))
                items[idx] = {**items[idx], **updates}
                setattr(pkg, field, items)
                await session.commit()


def _folder_scope(graph: dict, summaries: dict[str, str], folder: str) -> tuple[dict, dict[str, str]]:
    """Filter a graph/summaries down to just one top-level folder's files,
    for a folder-scoped README."""

    def _in_folder(path: str) -> bool:
        norm = path.replace("\\", "/")
        return norm == folder or norm.startswith(folder + "/")

    folder_summaries = {path: s for path, s in summaries.items() if _in_folder(path)}
    folder_nodes = [n for n in graph.get("nodes", []) if _in_folder(n.get("source_file", ""))]
    folder_edges = [
        e for e in graph.get("edges", []) if _in_folder(e.get("source", "")) or _in_folder(e.get("target", ""))
    ]
    folder_graph = {**graph, "nodes": folder_nodes, "edges": folder_edges}
    return folder_graph, folder_summaries


def _build_overview_plan(
    summaries: dict[str, str],
    folders: list[str],
    custom_instructions: str | None,
) -> ScenePlan:
    custom_note = f" Custom: {custom_instructions}" if custom_instructions else ""
    return ScenePlan(
        scene_name="CompleteArchitectureOverview",
        title="Complete Architecture Overview",
        description=(
            "Generate a COMPLETE multi-scene video using the multi_scene pattern. "
            f"Cover the entire codebase: title, web diagram of all folders "
            f"({', '.join(folders[:6]) or 'the codebase'}), request journey through "
            "the system, folder-by-folder overview, and reference to generated "
            "documentation. This is a long narrative video (60-120 seconds "
            f"total).{custom_note}"
        ),
        relevant_files=list(summaries.keys())[:30],
    )


async def _render_one_video(
    package_id: str,
    idx: int,
    plan: ScenePlan,
    summaries: dict[str, str],
    graph: dict,
    custom_instructions: str | None,
    quality: str,
    scene: str | None,
    timeout: float,
) -> None:
    code: str | None = None
    try:
        code = await generate_scene(plan, summaries, graph, custom_instructions)
        combined = f"from manim import *\n\n{code}"

        url, job_id = await submit_render(combined, quality, scene=scene, timeout=timeout)

        await _update_package_item(
            package_id, "videos", idx, {"video_id": job_id, "video_url": url, "status": "done"}
        )

    except Exception:
        logger.exception("Onboarding video %d failed for package %s", idx, package_id)
        logger.error("Generated code for video %d was:\n%s", idx, code)
        await _update_package_item(package_id, "videos", idx, {"status": "error"})


async def _generate_one_doc(
    package_id: str,
    idx: int,
    doc_type: str,
    graph: dict,
    summaries: dict[str, str],
    custom_instructions: str | None,
) -> None:
    try:
        markdown = await generate_docs(
            graph=graph,
            summaries=summaries,
            doc_type=doc_type,
            custom_instructions=custom_instructions,
        )
        filename = DOC_TYPES[doc_type]["title"]

        await _update_package_item(
            package_id, "docs", idx, {"filename": filename, "content": markdown, "status": "done"}
        )

    except Exception:
        logger.exception("Onboarding doc %s failed for package %s", doc_type, package_id)
        await _update_package_item(package_id, "docs", idx, {"status": "error"})


async def _generate_one_folder_doc(
    package_id: str,
    idx: int,
    folder: str,
    graph: dict,
    summaries: dict[str, str],
    custom_instructions: str | None,
) -> None:
    try:
        folder_graph, folder_summaries = _folder_scope(graph, summaries, folder)
        folder_instructions = (
            f"This document covers ONLY the {folder}/ folder. Focus on: what files "
            "are in this folder, what each file does, how they connect to each "
            "other, and how this folder connects to the rest of the system. "
            "End with: 'For the full architecture, see ARCHITECTURE.md'"
        )
        if custom_instructions:
            folder_instructions += f"\n{custom_instructions}"

        markdown = await generate_docs(
            graph=folder_graph,
            summaries=folder_summaries,
            doc_type="readme",
            custom_instructions=folder_instructions,
        )
        filename = f"docs/{folder}/README.md"

        await _update_package_item(
            package_id, "docs", idx, {"filename": filename, "content": markdown, "status": "done"}
        )

    except Exception:
        logger.exception("Folder doc for %s failed for package %s", folder, package_id)
        await _update_package_item(package_id, "docs", idx, {"status": "error"})


async def generate_package(
    package_id: str,
    graph: dict,
    summaries: dict[str, str],
    package_type: str,
    custom_instructions: str | None,
    quality: str,
) -> None:
    """Plan and generate a full onboarding package: one long multi-scene
    overview video covering the entire codebase, one deep-dive video per
    top-level folder, the package_type's main docs, and one README per
    folder — all rendered/generated in parallel.

    Planning (folder detection, per-folder scene plans) happens here
    rather than in the request handler, since it depends on the same
    graph/summaries this background task already has and keeps the
    request handler itself fast.

    Runs as a FastAPI BackgroundTask *after* the request's response has
    already been sent, so each sub-task opens its own DB session via
    AsyncSessionLocal rather than sharing the request-scoped one.
    """
    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import OnboardingPackage

    folders = detect_folders(graph)
    folder_limit = PACKAGE_FOLDER_LIMITS.get(package_type, 5)
    selected_folders = folders[:folder_limit]
    doc_types = PACKAGE_DOC_TYPES.get(package_type, PACKAGE_DOC_TYPES["full"])

    overview_plan = _build_overview_plan(summaries, folders, custom_instructions)
    folder_plans = await plan_folder_videos(graph, summaries, selected_folders) if selected_folders else []
    all_video_plans = [overview_plan] + folder_plans

    videos_meta = [
        {
            "focus": plan.title,
            "scene_name": plan.scene_name,
            "video_id": None,
            "video_url": None,
            "status": "pending",
            "is_overview": i == 0,
            "folder": None if i == 0 else selected_folders[i - 1],
        }
        for i, plan in enumerate(all_video_plans)
    ]
    docs_meta = [
        {"doc_type": dt, "filename": None, "content": None, "status": "pending", "folder": None}
        for dt in doc_types
    ] + [
        {
            "doc_type": "readme",
            "filename": f"docs/{folder}/README.md",
            "content": None,
            "status": "pending",
            "folder": folder,
        }
        for folder in selected_folders
    ]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OnboardingPackage).where(OnboardingPackage.id == UUID(package_id)).with_for_update()
        )
        pkg = result.scalar_one_or_none()
        if pkg:
            pkg.videos = videos_meta
            pkg.docs = docs_meta
            await session.commit()

    tasks = [
        _render_one_video(
            package_id, 0, overview_plan, summaries, graph, custom_instructions, quality,
            scene=None, timeout=OVERVIEW_RENDER_TIMEOUT,
        )
    ]
    for i, plan in enumerate(folder_plans):
        tasks.append(
            _render_one_video(
                package_id, i + 1, plan, summaries, graph, custom_instructions, quality,
                scene=plan.scene_name, timeout=VIDEO_RENDER_TIMEOUT,
            )
        )
    for i, doc_type in enumerate(doc_types):
        tasks.append(_generate_one_doc(package_id, i, doc_type, graph, summaries, custom_instructions))
    for i, folder in enumerate(selected_folders):
        doc_idx = len(doc_types) + i
        tasks.append(_generate_one_folder_doc(package_id, doc_idx, folder, graph, summaries, custom_instructions))

    await asyncio.gather(*tasks)

    async with AsyncSessionLocal() as session:
        pkg = await session.get(OnboardingPackage, UUID(package_id))
        if pkg:
            pkg.status = "done"
            pkg.completed_at = datetime.now(timezone.utc)
            await session.commit()
