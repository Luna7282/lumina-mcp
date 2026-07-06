from dataclasses import dataclass

from lumina_app.settings import settings


@dataclass
class RenderJob:
    job_id: str
    status: str
    video_url: str | None = None


class ManimRenderer:
    """Thin wrapper around the manim-studio-sdk rendering API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or settings.manimstudio_api_key
        self._base_url = base_url or settings.manimstudio_base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            import manimstudio  # imported lazily so the module can be inspected/tested

            self._client = manimstudio.Client(
                api_key=self._api_key, base_url=self._base_url
            )
        return self._client

    async def submit(self, scene_code: str) -> RenderJob:
        """Submit Manim scene source code for rendering and return the job handle."""
        client = self._get_client()
        job = await client.renders.create(code=scene_code)
        return RenderJob(job_id=job.id, status=job.status)

    async def poll(self, job_id: str) -> RenderJob:
        """Poll a render job for its current status and, once ready, video URL."""
        client = self._get_client()
        job = await client.renders.retrieve(job_id)
        return RenderJob(job_id=job.id, status=job.status, video_url=getattr(job, "video_url", None))
