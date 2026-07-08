import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from lumina_app.ai.planner import ScenePlan, plan_onboarding_videos
from lumina_app.database import AsyncSessionLocal, create_all_tables
from lumina_app.main import app
from lumina_app.models import OnboardingPackage
from lumina_app.onboarding import _update_package_item

TEST_DB_FILE = "./test.db"

SAMPLE_FILES = {
    "main.py": (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/users')\n"
        "def list_users(): return []\n"
    ),
    "models.py": "class User:\n    pass\n",
}


def _remove_test_db() -> None:
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)


@pytest.fixture
def client():
    _remove_test_db()
    with TestClient(app) as c:
        yield c
    _remove_test_db()


def _mock_anthropic_client(mocker, text: str, side_effect: Exception | None = None):
    """Patch anthropic.AsyncAnthropic so any of the ai/ modules that
    construct a fresh client get back a mock whose messages.create()
    returns `text` (or raises `side_effect`)."""
    mock_client_class = mocker.patch("anthropic.AsyncAnthropic")
    mock_client = mock_client_class.return_value
    if side_effect is not None:
        mock_client.messages.create = AsyncMock(side_effect=side_effect)
    else:
        mock_message = MagicMock()
        mock_message.content = [MagicMock(type="text", text=text)]
        mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


SAMPLE_VIDEO_PLANS = [
    ScenePlan(scene_name="AuthFlow", title="Auth Flow", description="d", relevant_files=["main.py"]),
]


def _patch_onboard_pipeline(mocker, video_plans=None, doc_types=None):
    mocker.patch(
        "lumina_app.main.summarize_codebase",
        new_callable=AsyncMock,
        return_value={"main.py": "Defines the app.", "models.py": "Defines User."},
    )
    mocker.patch(
        "lumina_app.main.plan_onboarding_videos",
        new_callable=AsyncMock,
        return_value=video_plans if video_plans is not None else SAMPLE_VIDEO_PLANS,
    )
    mocker.patch("lumina_app.main.generate_package", new_callable=AsyncMock)


class TestOnboardEndpoint:
    def test_valid_codebase_id_returns_generating(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]
        _patch_onboard_pipeline(mocker)

        response = client.post("/api/onboard", json={"codebase_id": codebase_id, "package_type": "full"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generating"
        assert data["codebase_id"] == codebase_id
        assert "package_id" in data
        assert data["videos"][0]["focus"] == "Auth Flow"
        assert data["videos"][0]["status"] == "pending"
        assert len(data["docs"]) == 3  # full → architecture, onboarding, api

    def test_invalid_codebase_id_returns_404(self, client, mocker):
        _patch_onboard_pipeline(mocker)
        random_id = "00000000-0000-0000-0000-000000000000"

        response = client.post("/api/onboard", json={"codebase_id": random_id})

        assert response.status_code == 404

    def test_invalid_package_type_returns_422(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]
        _patch_onboard_pipeline(mocker)

        response = client.post(
            "/api/onboard", json={"codebase_id": codebase_id, "package_type": "bogus"}
        )

        assert response.status_code == 422

    def test_quick_package_type_generates_one_doc(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]
        _patch_onboard_pipeline(mocker)

        response = client.post(
            "/api/onboard", json={"codebase_id": codebase_id, "package_type": "quick"}
        )

        data = response.json()
        assert len(data["docs"]) == 1
        assert data["docs"][0]["doc_type"] == "readme"


class TestGetPackageEndpoint:
    def test_returns_correct_shape(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]
        _patch_onboard_pipeline(mocker)

        onboard_response = client.post("/api/onboard", json={"codebase_id": codebase_id})
        package_id = onboard_response.json()["package_id"]

        response = client.get(f"/api/package/{package_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["package_id"] == package_id
        assert data["status"] == "generating"
        assert data["codebase_id"] == codebase_id
        assert data["package_type"] == "full"
        assert isinstance(data["videos"], list)
        assert isinstance(data["docs"], list)
        for doc in data["docs"]:
            assert doc["status"] == "pending"
            assert doc["content"] is None
            assert doc["word_count"] == 0
        assert "created_at" in data
        assert data["completed_at"] is None

    def test_nonexistent_package_returns_404(self, client):
        random_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/package/{random_id}")
        assert response.status_code == 404


class TestPlanOnboardingVideos:
    async def test_full_caps_at_five(self, mocker):
        plans_json = "[" + ",".join(
            f'{{"scene_name": "Scene{i}", "title": "T{i}", "description": "d", "relevant_files": []}}'
            for i in range(8)
        ) + "]"
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_onboarding_videos(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}}, {}, package_type="full"
        )
        assert len(plans) <= 5

    async def test_quick_caps_at_one(self, mocker):
        plans_json = '[{"scene_name": "A", "title": "A", "description": "d", "relevant_files": []},' \
            '{"scene_name": "B", "title": "B", "description": "d", "relevant_files": []}]'
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_onboarding_videos(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}}, {}, package_type="quick"
        )
        assert len(plans) <= 1

    async def test_technical_caps_at_three(self, mocker):
        plans_json = "[" + ",".join(
            f'{{"scene_name": "Scene{i}", "title": "T{i}", "description": "d", "relevant_files": []}}'
            for i in range(5)
        ) + "]"
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_onboarding_videos(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}}, {}, package_type="technical"
        )
        assert len(plans) <= 3

    async def test_fallback_on_json_error_returns_one_overview(self, mocker):
        _mock_anthropic_client(mocker, "not valid json at all")
        graph = {
            "god_nodes": [{"label": "UserService", "type": "class", "degree": 3, "source_file": "main.py"}],
            "community_summary": {},
            "language_summary": {},
        }
        plans = await plan_onboarding_videos(graph, {"main.py": "summary"}, package_type="full")
        assert len(plans) == 1
        assert plans[0].scene_name == "ArchitectureOverview"


class TestUpdatePackageItemConcurrency:
    """Regression test for the lost-update race: generate_package fires
    several _render_one_video / _generate_one_doc tasks concurrently, each
    updating one index of the same package's videos/docs JSON list in its
    own DB session. Without locking, each task reads the whole list before
    any of them commit, then writes its own stale copy back — the last
    commit to land wins and silently erases every other task's update."""

    async def test_concurrent_updates_do_not_clobber_each_other(self):
        _remove_test_db()
        await create_all_tables()
        try:
            async with AsyncSessionLocal() as session:
                pkg = OnboardingPackage(
                    codebase_id=uuid.uuid4(),
                    videos=[{"status": "pending"} for _ in range(5)],
                    docs=[],
                )
                session.add(pkg)
                await session.commit()
                await session.refresh(pkg)
                package_id = str(pkg.id)

            await asyncio.gather(
                *[
                    _update_package_item(
                        package_id, "videos", i, {"status": "done", "video_url": f"url{i}"}
                    )
                    for i in range(5)
                ]
            )

            async with AsyncSessionLocal() as session:
                refreshed = await session.get(OnboardingPackage, uuid.UUID(package_id))

            assert [v["status"] for v in refreshed.videos] == ["done"] * 5
            assert [v.get("video_url") for v in refreshed.videos] == [f"url{i}" for i in range(5)]
        finally:
            _remove_test_db()
