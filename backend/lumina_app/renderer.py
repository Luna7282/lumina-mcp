import asyncio
from uuid import UUID

from lumina_app.settings import settings


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
    from lumina_app.database import AsyncSessionLocal
    from lumina_app.models import CodebaseVideo

    try:
        from manimstudio import ManimStudio

        client = ManimStudio(
            api_key=settings.manimstudio_api_key,
            base_url=settings.manimstudio_base_url,
        )

        # ManimStudio's render()/wait() are blocking synchronous calls
        # (they poll over time.sleep) — run them in a thread pool so they
        # don't block the event loop.
        def blocking_render():
            job = client.render(code, quality=quality)
            job.wait(timeout=1800)  # 30 min max
            return job.url, job.job_id

        url, job_id = await asyncio.get_event_loop().run_in_executor(None, blocking_render)

        async with AsyncSessionLocal() as db:
            video = await db.get(CodebaseVideo, UUID(video_id))
            if video:
                video.status = "done"
                video.video_url = url
                video.render_job_id = job_id
                await db.commit()

    except Exception:
        async with AsyncSessionLocal() as db:
            video = await db.get(CodebaseVideo, UUID(video_id))
            if video:
                video.status = "error"
                await db.commit()
