import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from lumina_app.ai.planner import detect_folders, plan_folder_videos, plan_onboarding_videos
from lumina_app.database import AsyncSessionLocal, create_all_tables
from lumina_app.main import app
from lumina_app.models import OnboardingPackage
from lumina_app.onboarding import _update_package_item, generate_package

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


def _patch_onboard_pipeline(mocker):
    mocker.patch(
        "lumina_app.main.summarize_codebase",
        new_callable=AsyncMock,
        return_value={"main.py": "Defines the app.", "models.py": "Defines User."},
    )
    return mocker.patch("lumina_app.main.generate_package", new_callable=AsyncMock)


class TestOnboardEndpoint:
    """Planning (folders, video/doc plans) now happens inside the
    generate_package background task rather than in the request handler,
    so the immediate response only carries an empty videos/docs list —
    they fill in once the (here, mocked-out) background task runs."""

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
        assert data["videos"] == []
        assert data["docs"] == []

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

    def test_background_task_receives_package_type_and_instructions(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]
        generate_package_mock = _patch_onboard_pipeline(mocker)

        client.post(
            "/api/onboard",
            json={
                "codebase_id": codebase_id,
                "package_type": "technical",
                "custom_instructions": "Emphasize the render pipeline.",
            },
        )

        assert generate_package_mock.await_args.args[3] == "technical"
        assert generate_package_mock.await_args.args[4] == "Emphasize the render pipeline."


class TestGetPackageEndpoint:
    async def _create_package(self, package_type="full", videos=None, docs=None):
        async with AsyncSessionLocal() as session:
            pkg = OnboardingPackage(
                codebase_id=uuid.uuid4(),
                package_type=package_type,
                status="generating",
                videos=videos or [],
                docs=docs or [],
            )
            session.add(pkg)
            await session.commit()
            await session.refresh(pkg)
            return str(pkg.id), str(pkg.codebase_id)

    async def test_returns_correct_shape(self, client):
        package_id, codebase_id = await self._create_package(
            docs=[
                {"doc_type": "readme", "filename": None, "content": None, "status": "pending", "folder": None},
                {
                    "doc_type": "readme",
                    "filename": "docs/backend/README.md",
                    "content": "# Backend",
                    "status": "done",
                    "folder": "backend",
                },
            ],
        )

        response = client.get(f"/api/package/{package_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["package_id"] == package_id
        assert data["status"] == "generating"
        assert data["codebase_id"] == codebase_id
        assert data["package_type"] == "full"
        assert isinstance(data["videos"], list)
        assert data["docs"][0]["status"] == "pending"
        assert data["docs"][0]["content"] is None
        assert data["docs"][0]["word_count"] == 0
        assert data["docs"][0]["folder"] is None
        assert data["docs"][1]["status"] == "done"
        assert data["docs"][1]["content"] == "# Backend"
        assert data["docs"][1]["folder"] == "backend"
        assert data["docs"][1]["word_count"] == 2
        assert "created_at" in data
        assert data["completed_at"] is None

    def test_nonexistent_package_returns_404(self, client):
        random_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/package/{random_id}")
        assert response.status_code == 404


class TestDetectFolders:
    def test_returns_folders_sorted_by_file_count_descending(self):
        graph = {
            "nodes": [
                {"source_file": "backend/main.py"},
                {"source_file": "backend/models.py"},
                {"source_file": "backend/utils.py"},
                {"source_file": "worker/render.py"},
                {"source_file": "worker/queue.py"},
            ]
        }
        assert detect_folders(graph) == ["backend", "worker"]

    def test_skips_root_level_files(self):
        graph = {
            "nodes": [
                {"source_file": "main.py"},
                {"source_file": "README.md"},
                {"source_file": "backend/app.py"},
                {"source_file": "backend/db.py"},
            ]
        }
        folders = detect_folders(graph)
        assert folders == ["backend"]

    def test_skips_folders_with_only_one_file(self):
        graph = {
            "nodes": [
                {"source_file": "docs/README.md"},
                {"source_file": "backend/app.py"},
                {"source_file": "backend/db.py"},
            ]
        }
        folders = detect_folders(graph)
        assert folders == ["backend"]
        assert "docs" not in folders

    def test_handles_backslash_paths(self):
        graph = {
            "nodes": [
                {"source_file": "backend\\main.py"},
                {"source_file": "backend\\models.py"},
            ]
        }
        assert detect_folders(graph) == ["backend"]


class TestPlanFolderVideos:
    async def test_returns_one_plan_per_folder(self):
        graph = {
            "nodes": [
                {"source_file": "backend/main.py", "label": "f", "type": "function"},
                {"source_file": "worker/render.py", "label": "g", "type": "function"},
            ]
        }
        summaries = {"backend/main.py": "s1", "worker/render.py": "s2"}
        plans = await plan_folder_videos(graph, summaries, ["backend", "worker"])

        assert len(plans) == 2
        assert {p.scene_name for p in plans} == {"BackendFolderOverview", "WorkerFolderOverview"}
        assert all(p.relevant_files for p in plans)

    async def test_caps_at_five_even_if_more_folders_given(self):
        folders = [f"folder{i}" for i in range(8)]
        plans = await plan_folder_videos({"nodes": []}, {}, folders)
        assert len(plans) == 5


class TestGeneratePackage:
    async def test_creates_overview_and_folder_videos(self, mocker):
        _remove_test_db()
        await create_all_tables()
        try:
            mocker.patch(
                "lumina_app.onboarding.generate_scene",
                new_callable=AsyncMock,
                return_value=(
                    "from manim import *\n\nclass X(Scene):\n    def construct(self):\n        pass\n"
                ),
            )
            mocker.patch(
                "lumina_app.onboarding.submit_render",
                new_callable=AsyncMock,
                return_value=("https://example.com/v.mp4", "job-123"),
            )
            mocker.patch(
                "lumina_app.onboarding.generate_docs",
                new_callable=AsyncMock,
                return_value="# Doc",
            )

            graph = {
                "nodes": [
                    {"source_file": "backend/main.py", "label": "f", "type": "function"},
                    {"source_file": "backend/models.py", "label": "User", "type": "class"},
                    {"source_file": "worker/render.py", "label": "g", "type": "function"},
                    {"source_file": "worker/queue.py", "label": "Q", "type": "class"},
                ],
                "edges": [],
                "god_nodes": [],
                "community_summary": {},
                "language_summary": {"python": 4},
            }
            summaries = {
                "backend/main.py": "s1",
                "backend/models.py": "s2",
                "worker/render.py": "s3",
                "worker/queue.py": "s4",
            }

            async with AsyncSessionLocal() as session:
                pkg = OnboardingPackage(codebase_id=uuid.uuid4(), videos=[], docs=[])
                session.add(pkg)
                await session.commit()
                await session.refresh(pkg)
                package_id = str(pkg.id)

            await generate_package(package_id, graph, summaries, "full", None, "low")

            async with AsyncSessionLocal() as session:
                refreshed = await session.get(OnboardingPackage, uuid.UUID(package_id))

            assert refreshed.status == "done"
            assert refreshed.completed_at is not None

            videos = refreshed.videos
            assert len(videos) == 3  # overview + backend + worker
            assert videos[0]["is_overview"] is True
            assert videos[0]["folder"] is None
            assert videos[0]["status"] == "done"

            folder_videos = videos[1:]
            assert {v["folder"] for v in folder_videos} == {"backend", "worker"}
            assert all(v["is_overview"] is False for v in folder_videos)
            assert all(v["status"] == "done" for v in videos)

            docs = refreshed.docs
            main_docs = [d for d in docs if d["folder"] is None]
            folder_docs = [d for d in docs if d["folder"] is not None]
            assert {d["doc_type"] for d in main_docs} == {"architecture", "onboarding", "api"}
            assert {d["folder"] for d in folder_docs} == {"backend", "worker"}
            assert all(d["status"] == "done" for d in docs)
        finally:
            _remove_test_db()

    async def test_quick_package_skips_folder_videos_and_docs(self, mocker):
        _remove_test_db()
        await create_all_tables()
        try:
            mocker.patch(
                "lumina_app.onboarding.generate_scene",
                new_callable=AsyncMock,
                return_value=(
                    "from manim import *\n\nclass X(Scene):\n    def construct(self):\n        pass\n"
                ),
            )
            mocker.patch(
                "lumina_app.onboarding.submit_render",
                new_callable=AsyncMock,
                return_value=("https://example.com/v.mp4", "job-123"),
            )
            mocker.patch(
                "lumina_app.onboarding.generate_docs",
                new_callable=AsyncMock,
                return_value="# Doc",
            )

            graph = {
                "nodes": [
                    {"source_file": "backend/main.py", "label": "f", "type": "function"},
                    {"source_file": "backend/models.py", "label": "User", "type": "class"},
                ],
                "edges": [],
                "god_nodes": [],
                "community_summary": {},
                "language_summary": {"python": 2},
            }
            summaries = {"backend/main.py": "s1", "backend/models.py": "s2"}

            async with AsyncSessionLocal() as session:
                pkg = OnboardingPackage(codebase_id=uuid.uuid4(), videos=[], docs=[])
                session.add(pkg)
                await session.commit()
                await session.refresh(pkg)
                package_id = str(pkg.id)

            await generate_package(package_id, graph, summaries, "quick", None, "low")

            async with AsyncSessionLocal() as session:
                refreshed = await session.get(OnboardingPackage, uuid.UUID(package_id))

            assert len(refreshed.videos) == 1
            assert refreshed.videos[0]["is_overview"] is True
            assert len(refreshed.docs) == 1
            assert refreshed.docs[0]["doc_type"] == "readme"
        finally:
            _remove_test_db()


class TestPlanOnboardingVideos:
    """plan_onboarding_videos (community-based planning) is no longer
    wired into /api/onboard — generate_package uses folder-based planning
    instead — but the function itself is still intact and tested here."""

    async def test_full_returns_between_three_and_five(self, mocker):
        plans_json = "[" + ",".join(
            f'{{"scene_name": "Scene{i}", "title": "T{i}", "description": "d", "relevant_files": []}}'
            for i in range(8)
        ) + "]"
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_onboarding_videos(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}}, {}, package_type="full"
        )
        assert 3 <= len(plans) <= 5

    async def test_quick_is_exactly_one(self, mocker):
        plans_json = '[{"scene_name": "A", "title": "A", "description": "d", "relevant_files": []},' \
            '{"scene_name": "B", "title": "B", "description": "d", "relevant_files": []}]'
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_onboarding_videos(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}}, {}, package_type="quick"
        )
        assert len(plans) == 1

    async def test_technical_returns_between_two_and_three(self, mocker):
        plans_json = "[" + ",".join(
            f'{{"scene_name": "Scene{i}", "title": "T{i}", "description": "d", "relevant_files": []}}'
            for i in range(5)
        ) + "]"
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_onboarding_videos(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}}, {}, package_type="technical"
        )
        assert 2 <= len(plans) <= 3

    async def test_full_pads_up_to_minimum_when_ai_returns_fewer(self, mocker):
        # AI returns only 1 plan, but "full" requires at least 3 — the
        # remaining slots should be padded from community_summary/god_nodes.
        plans_json = '[{"scene_name": "AuthFlow", "title": "Auth", "description": "d", "relevant_files": []}]'
        _mock_anthropic_client(mocker, plans_json)
        graph = {
            "god_nodes": [{"label": "UserService", "type": "class", "degree": 3, "source_file": "main.py"}],
            "community_summary": {
                0: {"size": 3, "top_nodes": ["Renderer"], "files": ["render.py"]},
                1: {"size": 2, "top_nodes": ["Database"], "files": ["db.py"]},
            },
            "language_summary": {},
        }
        plans = await plan_onboarding_videos(graph, {"main.py": "summary"}, package_type="full")

        assert len(plans) >= 3
        assert plans[0].scene_name == "AuthFlow"
        scene_names = [p.scene_name for p in plans]
        assert len(scene_names) == len(set(scene_names))  # no duplicate names

    async def test_fallback_on_json_error_pads_to_minimum(self, mocker):
        _mock_anthropic_client(mocker, "not valid json at all")
        graph = {
            "god_nodes": [{"label": "UserService", "type": "class", "degree": 3, "source_file": "main.py"}],
            "community_summary": {},
            "language_summary": {},
        }
        plans = await plan_onboarding_videos(graph, {"main.py": "summary"}, package_type="full")
        assert len(plans) >= 3
        assert plans[0].scene_name == "ArchitectureOverview"
        scene_names = [p.scene_name for p in plans]
        assert len(scene_names) == len(set(scene_names))  # no duplicate names


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
