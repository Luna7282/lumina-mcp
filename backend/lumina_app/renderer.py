import asyncio
import http.client
import logging
import time
import urllib.error
from uuid import UUID

from lumina_app.settings import settings

logger = logging.getLogger(__name__)


async def submit_render(
    code: str,
    quality: str,
    scene: str | None = None,
    timeout: float = 1800.0,
) -> tuple[str, str, list[str]]:
    """Submit a Manim scene to ManimStudio and block until it's done.

    Polls the job manually (rather than the SDK's own job.wait()) so we can
    retry when Cloudflare drops the idle HTTP connection mid-poll
    (RemoteDisconnected) — the SDK's wait()/poll() has no retry of its own,
    so a single dropped connection would otherwise crash the whole render.
    Runs in a thread pool since it's a blocking, time.sleep-based poll loop.
    Returns (url, job_id, output_urls) — output_urls covers every rendered
    scene (a multi-scene file renders one output per Scene class), with
    `url` guaranteed to be its first element. Raises RenderError/
    RenderTimeoutError on failure.
    """
    from manimstudio import ManimStudio, RenderError

    client = ManimStudio(
        api_key=settings.manimstudio_api_key,
        base_url=settings.manimstudio_base_url,
        timeout=120.0,  # SDK default (30s) is too short for a slow poll round-trip
    )

    def blocking_render() -> tuple[str, str, list[str]]:
        job = client.render(code, quality=quality, scene=scene)

        deadline = time.time() + timeout
        max_retries = 5
        retry_count = 0

        while time.time() < deadline:
            try:
                result = job.poll()
                if result.status == "done":
                    urls = list(job.output_urls) if job.output_urls else []
                    if job.url and job.url not in urls:
                        urls = [job.url] + urls
                    return job.url, job.job_id, urls
                if result.status == "error":
                    raise RenderError(result.error or "Render failed", logs=result.logs or "")
                time.sleep(3)
                retry_count = 0  # reset only on a successful poll, not on every loop
            except (http.client.RemoteDisconnected, ConnectionResetError, urllib.error.URLError) as e:
                retry_count += 1
                if retry_count > max_retries:
                    raise
                wait = min(5 * retry_count, 30)
                logger.warning(
                    "Connection error polling render status (attempt %d/%d): %s. Retrying in %ds...",
                    retry_count, max_retries, e, wait,
                )
                time.sleep(wait)

        raise RenderError(f"Render timed out after {timeout}s")

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
        url, job_id, output_urls = await submit_render(code, quality)

        async with AsyncSessionLocal() as db:
            video = await db.get(CodebaseVideo, UUID(video_id))
            if video:
                video.status = "done"
                video.video_url = url
                video.output_urls = output_urls
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
