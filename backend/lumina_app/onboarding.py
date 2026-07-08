import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

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


async def _render_one_video(
    package_id: str,
    idx: int,
    plan: ScenePlan,
    summaries: dict[str, str],
    graph: dict,
    custom_instructions: str | None,
    quality: str,
) -> None:
    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import OnboardingPackage

    try:
        code = await generate_scene(plan, summaries, graph, custom_instructions)
        combined = f"from manim import *\n\n{code}"

        url, job_id = await submit_render(
            combined, quality, scene=plan.scene_name, timeout=VIDEO_RENDER_TIMEOUT
        )

        async with AsyncSessionLocal() as session:
            pkg = await session.get(OnboardingPackage, UUID(package_id))
            if pkg:
                videos = list(pkg.videos)
                videos[idx].update({"video_id": job_id, "video_url": url, "status": "done"})
                pkg.videos = videos
                await session.commit()

    except Exception:
        logger.exception("Onboarding video %d failed for package %s", idx, package_id)
        async with AsyncSessionLocal() as session:
            pkg = await session.get(OnboardingPackage, UUID(package_id))
            if pkg:
                videos = list(pkg.videos)
                videos[idx]["status"] = "error"
                pkg.videos = videos
                await session.commit()


async def _generate_one_doc(
    package_id: str,
    idx: int,
    doc_type: str,
    graph: dict,
    summaries: dict[str, str],
    custom_instructions: str | None,
) -> None:
    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import OnboardingPackage

    try:
        markdown = await generate_docs(
            graph=graph,
            summaries=summaries,
            doc_type=doc_type,
            custom_instructions=custom_instructions,
        )
        filename = DOC_TYPES[doc_type]["title"]

        async with AsyncSessionLocal() as session:
            pkg = await session.get(OnboardingPackage, UUID(package_id))
            if pkg:
                docs = list(pkg.docs)
                docs[idx].update({"filename": filename, "content": markdown, "status": "done"})
                pkg.docs = docs
                await session.commit()

    except Exception:
        logger.exception("Onboarding doc %s failed for package %s", doc_type, package_id)
        async with AsyncSessionLocal() as session:
            pkg = await session.get(OnboardingPackage, UUID(package_id))
            if pkg:
                docs = list(pkg.docs)
                docs[idx]["status"] = "error"
                pkg.docs = docs
                await session.commit()


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
