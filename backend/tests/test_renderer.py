import http.client
from unittest.mock import MagicMock

from lumina_app.renderer import submit_render


class FakeResult:
    def __init__(self, status, error=None, logs=None):
        self.status = status
        self.error = error
        self.logs = logs


def _mock_manimstudio(mocker, job):
    mock_client = MagicMock()
    mock_client.render.return_value = job
    mocker.patch("manimstudio.ManimStudio", return_value=mock_client)
    return mock_client


class TestSubmitRender:
    async def test_returns_url_job_id_and_output_urls(self, mocker):
        job = MagicMock()
        job.job_id = "job-123"
        job.url = "https://x/scene1.mp4"
        job.output_urls = ["https://x/scene1.mp4", "https://x/scene2.mp4"]
        job.poll.return_value = FakeResult(status="done")
        _mock_manimstudio(mocker, job)

        url, job_id, output_urls = await submit_render("code", "low", scene="MyScene")

        assert url == "https://x/scene1.mp4"
        assert job_id == "job-123"
        assert output_urls == ["https://x/scene1.mp4", "https://x/scene2.mp4"]

    async def test_prepends_url_when_not_already_in_output_urls(self, mocker):
        job = MagicMock()
        job.job_id = "job-456"
        job.url = "https://x/main.mp4"
        job.output_urls = ["https://x/other.mp4"]
        job.poll.return_value = FakeResult(status="done")
        _mock_manimstudio(mocker, job)

        _url, _job_id, output_urls = await submit_render("code", "low")

        assert output_urls == ["https://x/main.mp4", "https://x/other.mp4"]

    async def test_empty_output_urls_falls_back_to_just_url(self, mocker):
        job = MagicMock()
        job.job_id = "job-789"
        job.url = "https://x/only.mp4"
        job.output_urls = []
        job.poll.return_value = FakeResult(status="done")
        _mock_manimstudio(mocker, job)

        _url, _job_id, output_urls = await submit_render("code", "low")

        assert output_urls == ["https://x/only.mp4"]

    async def test_raises_on_error_status(self, mocker):
        job = MagicMock()
        job.poll.return_value = FakeResult(status="error", error="boom", logs="sandbox trace")
        _mock_manimstudio(mocker, job)

        from manimstudio import RenderError

        try:
            await submit_render("code", "low")
            raise AssertionError("expected RenderError")
        except RenderError as exc:
            assert str(exc) == "boom"
            assert exc.logs == "sandbox trace"

    async def test_retries_on_remote_disconnected_then_succeeds(self, mocker):
        job = MagicMock()
        job.job_id = "job-999"
        job.url = "https://x/v.mp4"
        job.output_urls = ["https://x/v.mp4"]
        job.poll.side_effect = [
            http.client.RemoteDisconnected("connection reset"),
            FakeResult(status="done"),
        ]
        _mock_manimstudio(mocker, job)
        mocker.patch("lumina_app.renderer.time.sleep")  # don't actually sleep in tests

        url, job_id, output_urls = await submit_render("code", "low")

        assert url == "https://x/v.mp4"
        assert job_id == "job-999"
        assert output_urls == ["https://x/v.mp4"]
        assert job.poll.call_count == 2
