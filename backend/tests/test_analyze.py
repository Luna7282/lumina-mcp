import os

import pytest
from fastapi.testclient import TestClient

from lumina_app.main import app

TEST_DB_FILE = "./test.db"

SAMPLE_FILES = {
    "main.py": (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/')\n"
        "def root(): return {'hello': 'world'}"
    ),
    "models.py": "from sqlalchemy import Column, String\nclass User: pass",
    "utils.py": "def helper(): pass\ndef another(): pass",
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


class TestAnalyzeEndpoint:
    def test_analyze_three_python_files(self, client):
        response = client.post(
            "/api/analyze", json={"name": "test-project", "files": SAMPLE_FILES}
        )
        assert response.status_code == 200
        data = response.json()
        assert "codebase_id" in data
        assert data["name"] == "test-project"
        assert data["file_count"] == 3
        assert data["language_summary"] == {"python": 3}
        assert data["node_count"] > 0
        assert data["edge_count"] > 0
        assert data["community_count"] >= 1
        assert isinstance(data["god_nodes"], list)
        assert data["cached"] is False

    def test_analyze_same_files_again_is_cached(self, client):
        first = client.post(
            "/api/analyze", json={"name": "test-project", "files": SAMPLE_FILES}
        )
        assert first.status_code == 200
        first_data = first.json()

        second = client.post(
            "/api/analyze", json={"name": "test-project", "files": SAMPLE_FILES}
        )
        assert second.status_code == 200
        second_data = second.json()

        assert second_data["cached"] is True
        assert second_data["codebase_id"] == first_data["codebase_id"]

    def test_analyze_empty_files_rejected(self, client):
        response = client.post(
            "/api/analyze", json={"name": "test-project", "files": {}}
        )
        assert response.status_code == 422

    def test_analyze_too_many_files_rejected(self, client):
        files = {f"file_{i}.py": "pass\n" for i in range(501)}
        response = client.post(
            "/api/analyze", json={"name": "test-project", "files": files}
        )
        assert response.status_code == 422

    def test_analyze_oversized_file_rejected(self, client):
        files = {"big.py": "x = 1\n" * 20_000}  # 120,000 chars > 100KB cap
        response = client.post(
            "/api/analyze", json={"name": "test-project", "files": files}
        )
        assert response.status_code == 422


class TestGetCodebaseEndpoint:
    def test_get_codebase_returns_stored_graph(self, client):
        analyze_response = client.post(
            "/api/analyze", json={"name": "test-project", "files": SAMPLE_FILES}
        )
        codebase_id = analyze_response.json()["codebase_id"]

        response = client.get(f"/api/codebase/{codebase_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == codebase_id
        assert data["name"] == "test-project"
        assert data["file_count"] == 3
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert "communities" in data["graph"]
        assert "community_summary" in data["graph"]
        assert "god_nodes" in data["graph"]
        assert "file_hashes" in data["graph"]
        assert set(data["graph"]["file_hashes"].keys()) == set(SAMPLE_FILES.keys())
        source_files = {n["source_file"] for n in data["graph"]["nodes"]}
        assert source_files == set(SAMPLE_FILES.keys())

    def test_get_codebase_not_found(self, client):
        random_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/codebase/{random_id}")
        assert response.status_code == 404

    def test_get_codebase_invalid_id_rejected(self, client):
        response = client.get("/api/codebase/not-a-uuid")
        assert response.status_code == 422
