from unittest.mock import MagicMock

import httpx
import pytest

import server


def _response(json_data=None, ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data if json_data is not None else {}
    if ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=404)
        )
    return resp


def _mock_client(mocker, post_side_effect=None, get_side_effect=None):
    """Patch server.httpx.Client so `with _client() as client:` yields a
    mock whose .post()/.get() follow the given side_effects (a single
    response, a list to return in sequence, or an exception to raise)."""
    mock_client = MagicMock()
    if post_side_effect is not None:
        mock_client.post.side_effect = post_side_effect
    if get_side_effect is not None:
        mock_client.get.side_effect = get_side_effect
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mocker.patch("server.httpx.Client", return_value=mock_client)
    return mock_client


ANALYZE_RESULT = {"codebase_id": "cb-1", "node_count": 5, "cached": False}
EXPLAIN_RESULT = {"video_id": "vid-1", "status": "rendering", "scenes": ["Scene1"]}
DOCS_RESULT = {
    "codebase_id": "cb-1",
    "doc_type": "readme",
    "filename": "README.md",
    "content": "# Project\n\nOverview.",
    "word_count": 3,
}


class TestAnalyzeCodebase:
    def test_calls_post_api_analyze_with_files_and_name(self, mocker):
        client = _mock_client(mocker, post_side_effect=[_response(ANALYZE_RESULT)])
        result = server.analyze_codebase(files={"main.py": "pass"}, name="proj")

        client.post.assert_called_once_with(
            "/api/analyze", json={"files": {"main.py": "pass"}, "name": "proj"}
        )
        assert result == ANALYZE_RESULT

    def test_raises_on_http_error(self, mocker):
        _mock_client(mocker, post_side_effect=[_response(ok=False)])
        with pytest.raises(httpx.HTTPStatusError):
            server.analyze_codebase(files={"main.py": "pass"})


class TestExplainCodebase:
    def test_with_files_calls_analyze_then_explain(self, mocker):
        client = _mock_client(
            mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(EXPLAIN_RESULT)]
        )
        result = server.explain_codebase(files={"main.py": "pass"}, wait_for_video=False)

        assert client.post.call_count == 2
        first_call, second_call = client.post.call_args_list
        assert first_call.args[0] == "/api/analyze"
        assert second_call.args[0] == "/api/explain"
        assert second_call.kwargs["json"]["codebase_id"] == "cb-1"
        assert result == EXPLAIN_RESULT

    def test_with_codebase_id_skips_analyze(self, mocker):
        client = _mock_client(mocker, post_side_effect=[_response(EXPLAIN_RESULT)])
        result = server.explain_codebase(codebase_id="cb-1", wait_for_video=False)

        client.post.assert_called_once()
        assert client.post.call_args.args[0] == "/api/explain"
        assert result == EXPLAIN_RESULT

    def test_returns_immediately_when_wait_for_video_false(self, mocker):
        client = _mock_client(mocker, post_side_effect=[_response(EXPLAIN_RESULT)])
        result = server.explain_codebase(codebase_id="cb-1", wait_for_video=False)

        client.get.assert_not_called()
        assert result == EXPLAIN_RESULT

    def test_polls_until_done(self, mocker):
        mocker.patch("server.time.sleep")
        client = _mock_client(
            mocker,
            post_side_effect=[_response(EXPLAIN_RESULT)],
            get_side_effect=[
                _response({"status": "rendering", "video_url": None}),
                _response({"status": "done", "video_url": "https://example.com/v.mp4"}),
            ],
        )
        result = server.explain_codebase(codebase_id="cb-1", wait_for_video=True)

        assert client.get.call_count == 2
        assert result["status"] == "done"
        assert result["video_url"] == "https://example.com/v.mp4"

    def test_returns_timeout_after_max_wait_seconds(self, mocker):
        # Force the deadline to have already passed on the loop's first
        # check, so no real waiting happens and no GET is ever made.
        mocker.patch("server.time.time", side_effect=[0.0, 1000.0])
        client = _mock_client(mocker, post_side_effect=[_response(EXPLAIN_RESULT)])

        result = server.explain_codebase(
            codebase_id="cb-1", wait_for_video=True, max_wait_seconds=60
        )

        client.get.assert_not_called()
        assert result["status"] == "timeout"
        assert result["video_id"] == "vid-1"


class TestAnalyzeLocalPath:
    def test_reads_files_from_temp_directory(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        (tmp_path / "app.js").write_text("console.log('hi')")

        files = server._read_local_path(str(tmp_path))

        assert files == {"main.py": "print('hi')", "app.js": "console.log('hi')"}

    def test_skips_node_modules_and_git_dirs(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        node_modules = tmp_path / "node_modules" / "pkg"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text("module.exports = {}")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")

        files = server._read_local_path(str(tmp_path))

        assert files == {"main.py": "print('hi')"}

    def test_skips_pyc_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        (tmp_path / "main.pyc").write_bytes(b"\x00\x01")

        files = server._read_local_path(str(tmp_path))

        assert files == {"main.py": "print('hi')"}

    def test_skips_files_over_max_file_size(self, tmp_path):
        (tmp_path / "small.py").write_text("x = 1")
        (tmp_path / "big.py").write_text("x = 1\n" * 20_000)  # > MAX_FILE_SIZE

        files = server._read_local_path(str(tmp_path))

        assert "small.py" in files
        assert "big.py" not in files

    def test_generate_video_false_skips_explain(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        client = _mock_client(mocker, post_side_effect=[_response(ANALYZE_RESULT)])

        result = server.analyze_local_path(str(tmp_path), generate_video=False)

        client.post.assert_called_once()
        assert client.post.call_args.args[0] == "/api/analyze"
        assert result["codebase_id"] == "cb-1"
        assert result["files_read"] == 1

    def test_generate_video_true_calls_explain_and_polls(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        _mock_client(mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(EXPLAIN_RESULT)])
        mock_poll = mocker.patch(
            "server._poll_video", return_value={"status": "done", "video_url": "https://x/v.mp4"}
        )

        result = server.analyze_local_path(str(tmp_path), generate_video=True, focus="overview")

        mock_poll.assert_called_once()
        assert mock_poll.call_args.args[1:] == ("vid-1", ["Scene1"], "cb-1", "overview")
        assert result == {"status": "done", "video_url": "https://x/v.mp4"}

    def test_returns_error_for_nonexistent_path(self):
        result = server.analyze_local_path("/definitely/does/not/exist/xyz")
        assert "error" in result


class TestGenerateDocs:
    def test_calls_post_api_docs_correctly(self, mocker):
        client = _mock_client(mocker, post_side_effect=[_response(DOCS_RESULT)])

        result = server.generate_docs(codebase_id="cb-1", doc_type="readme")

        client.post.assert_called_once_with(
            "/api/docs",
            json={"codebase_id": "cb-1", "doc_type": "readme", "custom_instructions": None},
            timeout=120.0,
        )
        assert result == DOCS_RESULT

    def test_saves_to_file_when_save_to_file_provided(self, mocker, tmp_path):
        _mock_client(mocker, post_side_effect=[_response(DOCS_RESULT)])
        target = tmp_path / "docs" / "README.md"

        result = server.generate_docs(codebase_id="cb-1", save_to_file=str(target))

        assert target.read_text(encoding="utf-8") == DOCS_RESULT["content"]
        assert result["saved_to"] == str(target.resolve())


class TestGetVideoStatus:
    def test_calls_get_api_video(self, mocker):
        client = _mock_client(mocker, get_side_effect=[_response({"status": "done"})])
        result = server.get_video_status("vid-1")

        client.get.assert_called_once_with("/api/video/vid-1")
        assert result == {"status": "done"}


class TestGetCodebaseGraph:
    def test_calls_get_api_codebase(self, mocker):
        graph = {"nodes": [], "edges": []}
        client = _mock_client(mocker, get_side_effect=[_response(graph)])
        result = server.get_codebase_graph("cb-1")

        client.get.assert_called_once_with("/api/codebase/cb-1")
        assert result == graph


class TestListSupportedLanguages:
    def test_returns_expected_structure(self):
        result = server.list_supported_languages()

        assert "python" in result["languages"]
        assert result["extensions"][".py"] == "python"
        assert "note" in result
