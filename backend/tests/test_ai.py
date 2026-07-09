import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from lumina_app.ai.generator import SCENE_PATTERNS, _get_scene_pattern, _scene_pattern_key, generate_scene
from lumina_app.ai.planner import ScenePlan, plan_visualization
from lumina_app.ai.summarizer import summarize_codebase, summarize_file
from lumina_app.main import app

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


def _mock_anthropic_client_with_thinking(mocker, text: str):
    """Like _mock_anthropic_client, but prepends a `thinking` block before
    the text block — reproducing claude-sonnet-5's real response shape when
    adaptive thinking (on by default) triggers. content[0] is NOT the
    answer in this case; callers must find the first type=="text" block."""
    mock_client_class = mocker.patch("anthropic.AsyncAnthropic")
    mock_client = mock_client_class.return_value
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(type="thinking", text=None, thinking="reasoning about the answer..."),
        MagicMock(type="text", text=text),
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


class TestScenePatterns:
    def test_overview_keywords_select_overview_pattern(self):
        assert _get_scene_pattern("ArchitectureOverview", "shows the overall structure") == (
            SCENE_PATTERNS["overview"]
        )

    def test_flow_keywords_select_flow_pattern(self):
        assert _get_scene_pattern("DataFlow", "request flow through the system") == SCENE_PATTERNS["flow"]

    def test_model_keywords_select_models_pattern(self):
        assert _get_scene_pattern("UserModelHierarchy", "class inheritance") == SCENE_PATTERNS["models"]

    def test_component_keywords_select_components_pattern(self):
        assert _get_scene_pattern("ServiceCommunity", "module cluster detail") == SCENE_PATTERNS["components"]

    def test_unmatched_keywords_fall_back_to_default(self):
        assert _get_scene_pattern("SomethingElse", "no matching keywords here") == SCENE_PATTERNS["default"]

    def test_folder_overview_scene_name_selects_folder_overview_key(self):
        assert _scene_pattern_key("BackendFolderOverview", "d") == "folder_overview"

    def test_complete_architecture_overview_selects_multi_scene_key(self):
        assert _scene_pattern_key("CompleteArchitectureOverview", "d") == "multi_scene"


class TestSummarizeFile:
    async def test_returns_api_text_on_success(self, mocker):
        _mock_anthropic_client(mocker, "This file defines the FastAPI app and a route.")
        nodes = [{"type": "route", "label": "/users"}]
        summary = await summarize_file("main.py", nodes, [])
        assert summary == "This file defines the FastAPI app and a route."

    async def test_returns_api_text_when_response_leads_with_thinking_block(self, mocker):
        # claude-sonnet-5/haiku may run adaptive thinking and put a
        # `thinking` block at content[0] with text=None — the real answer
        # is the first type=="text" block, not necessarily content[0].
        _mock_anthropic_client_with_thinking(mocker, "Summary after thinking.")
        nodes = [{"type": "function", "label": "f"}]
        summary = await summarize_file("main.py", nodes, [])
        assert summary == "Summary after thinking."

    async def test_returns_fallback_on_api_error(self, mocker):
        _mock_anthropic_client(mocker, "", side_effect=Exception("network error"))
        nodes = [
            {"type": "class", "label": "User"},
            {"type": "route", "label": "/users"},
            {"type": "function", "label": "helper"},
        ]
        summary = await summarize_file("main.py", nodes, [])
        assert summary.startswith("main.py:")
        assert "class(es)" in summary
        assert "route(s)" in summary
        assert "function(s)" in summary

    async def test_fallback_with_no_nodes_says_utility_file(self, mocker):
        _mock_anthropic_client(mocker, "", side_effect=Exception("boom"))
        summary = await summarize_file("empty.py", [], [])
        assert summary == "empty.py: utility file"


class TestSummarizeCodebase:
    async def test_uses_cached_summary_without_calling_api(self, mocker):
        summarize_file_mock = mocker.patch(
            "lumina_app.ai.summarizer.summarize_file", new_callable=AsyncMock
        )
        db_file = MagicMock()
        db_file.path = "main.py"
        db_file.summary = "Already summarized."

        graph = {"nodes": [], "edges": []}
        summaries = await summarize_codebase(graph, [db_file], db=None)

        assert summaries["main.py"] == "Already summarized."
        summarize_file_mock.assert_not_called()

    async def test_calls_summarize_file_for_uncached_files(self, mocker):
        summarize_file_mock = mocker.patch(
            "lumina_app.ai.summarizer.summarize_file",
            new_callable=AsyncMock,
            return_value="Fresh summary.",
        )
        db_file = MagicMock()
        db_file.path = "main.py"
        db_file.summary = None

        graph = {"nodes": [{"source_file": "main.py", "type": "function", "label": "f"}], "edges": []}
        summaries = await summarize_codebase(graph, [db_file], db=None)

        assert summaries["main.py"] == "Fresh summary."
        assert db_file.summary == "Fresh summary."
        summarize_file_mock.assert_awaited_once()


class TestPlanVisualization:
    async def test_returns_scene_plans_on_success(self, mocker):
        plans_json = """[
            {"scene_name": "Overview", "title": "Overview", "description": "d", "relevant_files": ["main.py"], "community_id": 0}
        ]"""
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_visualization({"god_nodes": [], "community_summary": {}, "language_summary": {}}, {})
        assert isinstance(plans, list)
        assert len(plans) == 1
        assert isinstance(plans[0], ScenePlan)
        assert plans[0].scene_name == "Overview"

    async def test_strips_markdown_fences_from_json_response(self, mocker):
        plans_json = '```json\n[{"scene_name": "X", "title": "X", "description": "d", "relevant_files": []}]\n```'
        _mock_anthropic_client(mocker, plans_json)
        plans = await plan_visualization({"god_nodes": [], "community_summary": {}, "language_summary": {}}, {})
        assert plans[0].scene_name == "X"

    async def test_returns_fallback_scene_on_json_error(self, mocker):
        _mock_anthropic_client(mocker, "not valid json at all")
        graph = {
            "god_nodes": [{"label": "UserService", "type": "class", "degree": 3, "source_file": "main.py"}],
            "community_summary": {},
            "language_summary": {},
        }
        plans = await plan_visualization(graph, {"main.py": "summary"})
        assert len(plans) == 1
        assert plans[0].scene_name == "CodebaseOverview"
        assert "UserService" in plans[0].description
        assert plans[0].relevant_files == ["main.py"]

    async def test_parses_json_when_response_leads_with_thinking_block(self, mocker):
        # Regression test: claude-sonnet-5 runs adaptive thinking by default
        # and this prompt is complex enough to trigger it in practice — a
        # `thinking` block at content[0] must not be mistaken for "no
        # response" and fall back to CodebaseOverview.
        plans_json = '[{"scene_name": "RealPlan", "title": "Real", "description": "d", "relevant_files": []}]'
        _mock_anthropic_client_with_thinking(mocker, plans_json)
        plans = await plan_visualization({"god_nodes": [], "community_summary": {}, "language_summary": {}}, {})
        assert plans[0].scene_name == "RealPlan"

    async def test_custom_instructions_appended_to_user_message(self, mocker):
        plans_json = '[{"scene_name": "X", "title": "X", "description": "d", "relevant_files": []}]'
        mock_client = _mock_anthropic_client(mocker, plans_json)
        await plan_visualization(
            {"god_nodes": [], "community_summary": {}, "language_summary": {}},
            {},
            custom_instructions="Focus on the authentication flow.",
        )
        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Additional instructions from the user:" in user_content
        assert "Focus on the authentication flow." in user_content

    async def test_no_custom_instructions_not_appended(self, mocker):
        plans_json = '[{"scene_name": "X", "title": "X", "description": "d", "relevant_files": []}]'
        mock_client = _mock_anthropic_client(mocker, plans_json)
        await plan_visualization({"god_nodes": [], "community_summary": {}, "language_summary": {}}, {})
        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Additional instructions from the user:" not in user_content


class TestGenerateScene:
    async def test_strips_markdown_fences_correctly(self, mocker):
        fenced = (
            "```python\n"
            "from manim import *\n\n"
            "class MyScene(Scene):\n"
            "    def construct(self):\n"
            "        self.wait(1)\n"
            "```"
        )
        _mock_anthropic_client(mocker, fenced)
        plan = ScenePlan(scene_name="MyScene", title="My Scene", description="d", relevant_files=[])
        code = await generate_scene(plan, {}, {"nodes": [], "edges": []})
        assert not code.startswith("```")
        assert not code.endswith("```")
        assert "class MyScene(Scene):" in code

    async def test_extracts_code_when_response_leads_with_thinking_block(self, mocker):
        # Regression test for the same content[0]-is-thinking issue as
        # summarizer/planner — generator hits it too since it also uses
        # claude-sonnet-5.
        code_text = "from manim import *\n\nclass MyScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
        _mock_anthropic_client_with_thinking(mocker, code_text)
        plan = ScenePlan(scene_name="MyScene", title="My Scene", description="d", relevant_files=[])
        code = await generate_scene(plan, {}, {"nodes": [], "edges": []})
        assert "class MyScene(Scene):" in code

    async def test_returns_fallback_after_two_failed_attempts(self, mocker):
        wrong_code = "from manim import *\n\nclass WrongName(Scene):\n    def construct(self):\n        pass\n"
        mock_client = _mock_anthropic_client(mocker, wrong_code)
        plan = ScenePlan(scene_name="ExpectedScene", title="Expected", description="d", relevant_files=[])
        code = await generate_scene(plan, {}, {"nodes": [], "edges": []})
        assert "class ExpectedScene(Scene):" in code
        assert mock_client.messages.create.await_count == 2

    async def test_custom_instructions_appended_to_system_prompt(self, mocker):
        code_text = "from manim import *\n\nclass MyScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
        mock_client = _mock_anthropic_client(mocker, code_text)
        plan = ScenePlan(scene_name="MyScene", title="My Scene", description="d", relevant_files=[])
        await generate_scene(plan, {}, {"nodes": [], "edges": []}, custom_instructions="Use a dark theme.")
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "User's custom requirements:" in call_kwargs["system"]
        assert "Use a dark theme." in call_kwargs["system"]

    async def test_no_custom_instructions_not_appended_to_system(self, mocker):
        code_text = "from manim import *\n\nclass MyScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
        mock_client = _mock_anthropic_client(mocker, code_text)
        plan = ScenePlan(scene_name="MyScene", title="My Scene", description="d", relevant_files=[])
        await generate_scene(plan, {}, {"nodes": [], "edges": []})
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "User's custom requirements:" not in call_kwargs["system"]

    async def test_layout_rules_appear_in_system_prompt(self, mocker):
        code_text = "from manim import *\n\nclass MyScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
        mock_client = _mock_anthropic_client(mocker, code_text)
        plan = ScenePlan(scene_name="MyScene", title="My Scene", description="d", relevant_files=[])
        await generate_scene(plan, {}, {"nodes": [], "edges": []})
        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_prompt = call_kwargs["system"]
        assert "LAYOUT RULES" in system_prompt
        assert "Maximum 6 layers/boxes in one scene" in system_prompt
        assert "ARROW LABEL RULES" in system_prompt

    async def test_multi_scene_accepts_three_or_more_scene_classes(self, mocker):
        code_text = (
            "from manim import *\n\n"
            "class TitleScene(Scene):\n    def construct(self):\n        self.wait(1)\n\n"
            "class WebScene(Scene):\n    def construct(self):\n        self.wait(1)\n\n"
            "class JourneyScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
        )
        mock_client = _mock_anthropic_client(mocker, code_text)
        plan = ScenePlan(
            scene_name="CompleteArchitectureOverview",
            title="Complete Architecture Overview",
            description="d",
            relevant_files=[],
        )
        code = await generate_scene(plan, {}, {"nodes": [], "edges": []})
        assert code == code_text.strip()
        assert mock_client.messages.create.await_count == 1

    async def test_multi_scene_rejects_only_two_scene_classes(self, mocker):
        code_text = (
            "from manim import *\n\n"
            "class TitleScene(Scene):\n    def construct(self):\n        self.wait(1)\n\n"
            "class WebScene(Scene):\n    def construct(self):\n        self.wait(1)\n"
        )
        mock_client = _mock_anthropic_client(mocker, code_text)
        plan = ScenePlan(
            scene_name="CompleteArchitectureOverview",
            title="Complete Architecture Overview",
            description="d",
            relevant_files=[],
        )
        code = await generate_scene(plan, {}, {"nodes": [], "edges": []})
        # Both retries return the same too-short code, so it exhausts
        # retries and falls back to a trivial single scene.
        assert mock_client.messages.create.await_count == 2
        assert "class CompleteArchitectureOverview(Scene):" in code


class TestExplainEndpoint:
    def test_explain_with_valid_codebase_returns_rendering(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]

        mocker.patch(
            "lumina_app.main.summarize_codebase",
            new_callable=AsyncMock,
            return_value={"main.py": "Defines the app.", "models.py": "Defines User."},
        )
        mocker.patch(
            "lumina_app.main.plan_visualization",
            new_callable=AsyncMock,
            return_value=[
                ScenePlan(scene_name="Overview", title="Overview", description="d", relevant_files=["main.py"])
            ],
        )
        mocker.patch(
            "lumina_app.main.generate_scene",
            new_callable=AsyncMock,
            return_value="from manim import *\n\nclass Overview(Scene):\n    def construct(self):\n        self.wait(1)\n",
        )
        mocker.patch("lumina_app.renderer.render_and_save", new_callable=AsyncMock)

        response = client.post("/api/explain", json={"codebase_id": codebase_id})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rendering"
        assert data["codebase_id"] == codebase_id
        assert len(data["scenes"]) > 0
        assert data["scenes"] == ["Overview"]

    def test_explain_accepts_and_forwards_custom_instructions(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]

        summarize_mock = mocker.patch(
            "lumina_app.main.summarize_codebase",
            new_callable=AsyncMock,
            return_value={"main.py": "Defines the app.", "models.py": "Defines User."},
        )
        plan_mock = mocker.patch(
            "lumina_app.main.plan_visualization",
            new_callable=AsyncMock,
            return_value=[
                ScenePlan(scene_name="Overview", title="Overview", description="d", relevant_files=["main.py"])
            ],
        )
        generate_mock = mocker.patch(
            "lumina_app.main.generate_scene",
            new_callable=AsyncMock,
            return_value="from manim import *\n\nclass Overview(Scene):\n    def construct(self):\n        self.wait(1)\n",
        )
        mocker.patch("lumina_app.renderer.render_and_save", new_callable=AsyncMock)

        response = client.post(
            "/api/explain",
            json={"codebase_id": codebase_id, "custom_instructions": "Focus on the API layer."},
        )
        assert response.status_code == 200

        assert summarize_mock.call_args.args[-1] == "Focus on the API layer."
        assert plan_mock.call_args.args[-1] == "Focus on the API layer."
        assert generate_mock.call_args.args[-1] == "Focus on the API layer."

    def test_explain_with_nonexistent_codebase_404(self, client, mocker):
        mocker.patch("lumina_app.renderer.render_and_save", new_callable=AsyncMock)
        random_id = "00000000-0000-0000-0000-000000000000"
        response = client.post("/api/explain", json={"codebase_id": random_id})
        assert response.status_code == 404


class TestVideoEndpoint:
    def test_get_video_returns_correct_shape(self, client, mocker):
        analyze_response = client.post("/api/analyze", json={"name": "demo", "files": SAMPLE_FILES})
        codebase_id = analyze_response.json()["codebase_id"]

        mocker.patch(
            "lumina_app.main.summarize_codebase", new_callable=AsyncMock, return_value={"main.py": "s"}
        )
        mocker.patch(
            "lumina_app.main.plan_visualization",
            new_callable=AsyncMock,
            return_value=[ScenePlan(scene_name="Overview", title="Overview", description="d", relevant_files=[])],
        )
        mocker.patch(
            "lumina_app.main.generate_scene",
            new_callable=AsyncMock,
            return_value="from manim import *\n\nclass Overview(Scene):\n    def construct(self):\n        self.wait(1)\n",
        )
        mocker.patch("lumina_app.renderer.render_and_save", new_callable=AsyncMock)

        explain_response = client.post("/api/explain", json={"codebase_id": codebase_id})
        video_id = explain_response.json()["video_id"]

        response = client.get(f"/api/video/{video_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["video_id"] == video_id
        assert data["status"] in ("rendering", "done", "error")
        assert data["codebase_id"] == codebase_id
        assert "focus" in data
        assert "created_at" in data
        assert data["output_urls"] == []

    def test_get_video_nonexistent_404(self, client):
        random_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/video/{random_id}")
        assert response.status_code == 404
