import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from lumina_app.ai.documenter import generate_docs
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

SAMPLE_GRAPH = {
    "nodes": [
        {
            "id": "main.py::list_users",
            "label": "list_users",
            "type": "route",
            "source_file": "main.py",
            "source_location": "L4",
        },
        {
            "id": "models.py::User",
            "label": "User",
            "type": "model",
            "source_file": "models.py",
            "source_location": "L1",
        },
    ],
    "god_nodes": [
        {"label": "list_users", "type": "route", "source_file": "main.py", "degree": 3},
    ],
    "language_summary": {"python": 2},
    "community_summary": {
        0: {"size": 2, "top_nodes": ["list_users", "User"], "files": ["main.py", "models.py"]},
    },
}

SAMPLE_SUMMARIES = {
    "main.py": "Defines the FastAPI app and the /users route.",
    "models.py": "Defines the User model.",
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
    """Patch anthropic.AsyncAnthropic so generate_docs() gets back a mock
    whose messages.create() returns `text` (or raises `side_effect`)."""
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
    adaptive thinking (on by default) triggers."""
    mock_client_class = mocker.patch("anthropic.AsyncAnthropic")
    mock_client = mock_client_class.return_value
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(type="thinking", text=None, thinking="reasoning about the docs..."),
        MagicMock(type="text", text=text),
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    return mock_client


SAMPLE_MARKDOWN = "# My Project\n\n## Project Overview\n\nA small FastAPI service."


class TestDocsEndpoint:
    def test_valid_codebase_id_returns_markdown(self, client, mocker):
        _mock_anthropic_client(mocker, SAMPLE_MARKDOWN)
        analyze_response = client.post(
            "/api/analyze", json={"name": "test-project", "files": SAMPLE_FILES}
        )
        codebase_id = analyze_response.json()["codebase_id"]

        response = client.post("/api/docs", json={"codebase_id": codebase_id, "doc_type": "readme"})
        assert response.status_code == 200
        data = response.json()
        assert data["codebase_id"] == codebase_id
        assert data["doc_type"] == "readme"
        assert data["filename"] == "README.md"
        assert data["content"] == SAMPLE_MARKDOWN
        assert data["content"].startswith("#")
        assert data["word_count"] == len(SAMPLE_MARKDOWN.split())

    def test_invalid_doc_type_rejected(self, client, mocker):
        _mock_anthropic_client(mocker, SAMPLE_MARKDOWN)
        analyze_response = client.post(
            "/api/analyze", json={"name": "test-project", "files": SAMPLE_FILES}
        )
        codebase_id = analyze_response.json()["codebase_id"]

        response = client.post(
            "/api/docs", json={"codebase_id": codebase_id, "doc_type": "not-a-real-type"}
        )
        assert response.status_code == 422

    def test_unknown_codebase_id_returns_404(self, client, mocker):
        _mock_anthropic_client(mocker, SAMPLE_MARKDOWN)
        random_id = "00000000-0000-0000-0000-000000000000"
        response = client.post("/api/docs", json={"codebase_id": random_id, "doc_type": "readme"})
        assert response.status_code == 404


class TestGenerateDocs:
    async def test_returns_markdown_string(self, mocker):
        _mock_anthropic_client(mocker, SAMPLE_MARKDOWN)
        result = await generate_docs(SAMPLE_GRAPH, SAMPLE_SUMMARIES, doc_type="readme")
        assert result == SAMPLE_MARKDOWN

    async def test_handles_thinking_block_before_text(self, mocker):
        _mock_anthropic_client_with_thinking(mocker, SAMPLE_MARKDOWN)
        result = await generate_docs(SAMPLE_GRAPH, SAMPLE_SUMMARIES, doc_type="architecture")
        assert result == SAMPLE_MARKDOWN

    async def test_custom_instructions_appended_to_user_message(self, mocker):
        mock_client = _mock_anthropic_client(mocker, SAMPLE_MARKDOWN)
        await generate_docs(
            SAMPLE_GRAPH,
            SAMPLE_SUMMARIES,
            doc_type="readme",
            custom_instructions="Target audience: non-technical stakeholders",
        )
        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_message = call_kwargs["messages"][0]["content"]
        assert "Target audience: non-technical stakeholders" in user_message
