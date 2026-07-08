import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from lumina_app.ai.documenter import DOC_TYPES, generate_docs
from lumina_app.ai.generator import generate_scene
from lumina_app.ai.planner import ScenePlan
from lumina_app.renderer import submit_render

logger = logging.getLogger(__name__)

# Which doc types each package_type bundles alongside its videos.
PACKAGE_DOC_TYPES: dict[str, list[str]] = {
    "full": ["architecture", "onboarding", "api"],
    "quick": ["readme"],
    "technical": ["architecture", "api"],
}

# Onboarding videos render in parallel with several others, so each gets a
# shorter per-video timeout than a standalone /api/explain render.
VIDEO_RENDER_TIMEOUT = 600.0

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


async def _render_one_video(
    package_id: str,
    idx: int,
    plan: ScenePlan,
    summaries: dict[str, str],
    graph: dict,
    custom_instructions: str | None,
    quality: str,
) -> None:
    code: str | None = None
    try:
        code = await generate_scene(plan, summaries, graph, custom_instructions)
        combined = f"from manim import *\n\n{code}"

        url, job_id = await submit_render(
            combined, quality, scene=plan.scene_name, timeout=VIDEO_RENDER_TIMEOUT
        )

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


async def generate_package(
    package_id: str,
    graph: dict,
    summaries: dict[str, str],
    video_plans: list[ScenePlan],
    doc_types: list[str],
    custom_instructions: str | None,
    quality: str,
) -> None:
    """Render every planned video and generate every doc type in parallel,
    updating the OnboardingPackage row as each piece finishes.

    Runs as a FastAPI BackgroundTask *after* the request's response has
    already been sent, so each sub-task opens its own DB session via
    AsyncSessionLocal rather than sharing the request-scoped one.
    """
    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import OnboardingPackage

    tasks = [
        _render_one_video(package_id, i, plan, summaries, graph, custom_instructions, quality)
        for i, plan in enumerate(video_plans)
    ] + [
        _generate_one_doc(package_id, i, doc_type, graph, summaries, custom_instructions)
        for i, doc_type in enumerate(doc_types)
    ]

    await asyncio.gather(*tasks)

    async with AsyncSessionLocal() as session:
        pkg = await session.get(OnboardingPackage, UUID(package_id))
        if pkg:
            pkg.status = "done"
            pkg.completed_at = datetime.now(timezone.utc)
            await session.commit()
