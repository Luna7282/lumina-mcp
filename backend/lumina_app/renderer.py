import asyncio
import logging
from uuid import UUID

from lumina_app.settings import settings

logger = logging.getLogger(__name__)


async def submit_render(
    code: str,
    quality: str,
    scene: str | None = None,
    timeout: float = 1800.0,
) -> tuple[str, str]:
    """Submit a Manim scene to ManimStudio and block until it's done.

    ManimStudio's render()/wait() are blocking synchronous calls (they poll
    over time.sleep) — run them in a thread pool so they don't block the
    event loop. Returns (url, job_id); raises RenderError/RenderTimeoutError
    on failure.
    """
    from manimstudio import ManimStudio
    from manimstudio.exceptions import RenderError

    client = ManimStudio(
        api_key=settings.manimstudio_api_key,
        base_url=settings.manimstudio_base_url,
    )

    def blocking_render():
        job = client.render(code, quality=quality, scene=scene)
        job.wait(timeout=timeout)
        return job.url, job.job_id

    try:
        return await asyncio.get_event_loop().run_in_executor(None, blocking_render)
    except Exception as exc:
        logger.exception("submit_render failed (scene=%s, quality=%s)", scene, quality)
        if isinstance(exc, RenderError) and exc.logs:
            logger.error("Sandbox logs for scene=%s:\n%s", scene, exc.logs)
        raise


async def render_and_save(
    video_id: str,
    code: str,
    quality: str,
) -> None:
    """Submit a Manim scene for rendering and persist the result.

    Runs as a FastAPI BackgroundTask *after* the request's response has
    already been sent — the request-scoped DB session from that request is
    closed by then, so this opens its own fresh session via
    AsyncSessionLocal rather than accepting one as a parameter.
    """
    from manimstudio.exceptions import RenderError

    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import CodebaseVideo

    try:
        url, job_id = await submit_render(code, quality)

        async with AsyncSessionLocal() as db:
            video = await db.get(CodebaseVideo, UUID(video_id))
            if video:
                video.status = "done"
                video.video_url = url
                video.render_job_id = job_id
                await db.commit()

    except Exception as exc:
        logger.exception("Render failed for video %s", video_id)
        error_message = str(exc)
        if isinstance(exc, RenderError) and exc.logs:
            error_message = f"{exc}\n\n{exc.logs}"

        async with AsyncSessionLocal() as db:
            video = await db.get(CodebaseVideo, UUID(video_id))
            if video:
                video.status = "error"
                video.error_message = error_message
                await db.commit()
