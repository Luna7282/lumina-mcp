from pathlib import Path
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


ONBOARD_RESULT = {
    "package_id": "pkg-1",
    "status": "generating",
    "codebase_id": "cb-1",
    "videos": [{"focus": "Auth Flow", "scene_name": "AuthFlow", "video_url": None, "status": "pending"}],
    "docs": [{"doc_type": "readme", "filename": None, "content": None, "status": "pending"}],
}


class TestCreateOnboardingPackage:
    def test_calls_analyze_then_onboard(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        client = _mock_client(
            mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)]
        )

        result = server.create_onboarding_package(str(tmp_path), wait=False)

        assert client.post.call_count == 2
        first_call, second_call = client.post.call_args_list
        assert first_call.args[0] == "/api/analyze"
        assert second_call.args[0] == "/api/onboard"
        assert second_call.kwargs["json"]["codebase_id"] == "cb-1"
        assert result == ONBOARD_RESULT

    def test_returns_immediately_when_wait_false(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        client = _mock_client(
            mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)]
        )

        result = server.create_onboarding_package(str(tmp_path), wait=False)

        client.get.assert_not_called()
        assert result == ONBOARD_RESULT

    def test_polls_until_done(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        mocker.patch("server.time.sleep")
        client = _mock_client(
            mocker,
            post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)],
            get_side_effect=[
                _response({"status": "generating"}),
                _response({"status": "done", "videos": [], "docs": []}),
            ],
        )

        result = server.create_onboarding_package(str(tmp_path), wait=True)

        assert client.get.call_count == 2
        assert result["status"] == "done"

    def test_returns_error_for_nonexistent_path(self):
        result = server.create_onboarding_package("/definitely/does/not/exist/xyz")
        assert "error" in result

    def test_forwards_package_type_and_custom_instructions(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        client = _mock_client(
            mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)]
        )

        server.create_onboarding_package(
            str(tmp_path),
            package_type="technical",
            custom_instructions="Emphasize the render pipeline.",
            wait=False,
        )

        onboard_call = client.post.call_args_list[1]
        assert onboard_call.kwargs["json"]["package_type"] == "technical"
        assert onboard_call.kwargs["json"]["custom_instructions"] == "Emphasize the render pipeline."

    def test_saves_to_disk_when_wait_and_save_to_disk_true(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        _mock_client(mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)])
        done_result = {"status": "done", "videos": [], "docs": []}
        mocker.patch("server._poll_package", return_value=done_result)
        mock_save = mocker.patch(
            "server._save_package_to_disk", return_value=str(tmp_path / "project-docs")
        )

        result = server.create_onboarding_package(str(tmp_path), wait=True, save_to_disk=True)

        mock_save.assert_called_once()
        assert mock_save.call_args.args[0] is done_result
        assert result["saved_to"] == str(tmp_path / "project-docs")
        assert "message" in result

    def test_skips_save_to_disk_when_false(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        _mock_client(mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)])
        mocker.patch("server._poll_package", return_value={"status": "done", "videos": [], "docs": []})
        mock_save = mocker.patch("server._save_package_to_disk")

        result = server.create_onboarding_package(str(tmp_path), wait=True, save_to_disk=False)

        mock_save.assert_not_called()
        assert "saved_to" not in result

    def test_skips_save_to_disk_when_not_done(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        _mock_client(mocker, post_side_effect=[_response(ANALYZE_RESULT), _response(ONBOARD_RESULT)])
        mocker.patch("server._poll_package", return_value={"status": "timeout"})
        mock_save = mocker.patch("server._save_package_to_disk")

        result = server.create_onboarding_package(str(tmp_path), wait=True, save_to_disk=True)

        mock_save.assert_not_called()
        assert result["status"] == "timeout"


class TestSavePackageToDisk:
    def test_creates_project_docs_structure(self, mocker, tmp_path):
        mock_download = mocker.patch("server._download_file")
        package_data = {
            "videos": [
                {"status": "done", "video_url": "https://x/v.mp4", "folder": None},
                {"status": "done", "video_url": "https://x/backend.mp4", "folder": "backend"},
                {"status": "pending", "video_url": None, "folder": "worker"},
            ],
            "docs": [
                {"status": "done", "content": "# Arch", "filename": "ARCHITECTURE.md"},
                {"status": "done", "content": "# Backend", "filename": "docs/backend/README.md"},
                {"status": "pending", "content": None, "filename": None},
            ],
        }

        output_dir = server._save_package_to_disk(package_data, str(tmp_path))

        output_path = Path(output_dir)
        assert output_path == tmp_path / "project-docs"
        assert (output_path / "videos").is_dir()
        assert (output_path / "docs").is_dir()
        assert (output_path / "ARCHITECTURE.md").read_text() == "# Arch"
        assert (output_path / "docs" / "backend" / "README.md").read_text() == "# Backend"
        assert (output_path / "index.md").exists()
        assert mock_download.call_count == 2  # only the two "done" videos with a url

        assert package_data["videos"][0]["saved_to"].endswith("00_complete_architecture.mp4")
        assert package_data["videos"][1]["saved_to"].endswith("backend_overview.mp4")
        assert "saved_to" not in package_data["videos"][2]
        assert package_data["docs"][0]["saved_to"]
        assert package_data["docs"][1]["saved_to"]
        assert "saved_to" not in package_data["docs"][2]

    def test_records_download_error_without_crashing(self, mocker, tmp_path):
        mocker.patch("server._download_file", side_effect=OSError("network down"))
        package_data = {
            "videos": [{"status": "done", "video_url": "https://x/v.mp4", "folder": None}],
            "docs": [],
        }

        server._save_package_to_disk(package_data, str(tmp_path))

        assert "network down" in package_data["videos"][0]["download_error"]


class TestDownloadFile:
    def test_sends_non_default_user_agent(self, mocker, tmp_path):
        # manimstudio.me's WAF returns 403 for Python's default urllib
        # User-Agent ("Python-urllib/x.y") — a normal-looking one must be
        # sent, or downloads silently fail in production.
        mock_response = MagicMock()
        mock_response.read.return_value = b"video bytes"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen = mocker.patch("server.urllib.request.urlopen", return_value=mock_response)

        dest = tmp_path / "out.mp4"
        server._download_file("https://x/v.mp4", str(dest))

        request = mock_urlopen.call_args.args[0]
        assert "User-agent" in request.headers
        assert not request.get_header("User-agent").startswith("Python-urllib")
        assert dest.read_bytes() == b"video bytes"


EXPLAIN_FOLDER_ONBOARD_RESULT = {"package_id": "pkg-2", "status": "generating"}
EXPLAIN_FOLDER_PACKAGE_DONE = {
    "status": "done",
    "videos": [{"status": "done", "video_url": "https://x/folder.mp4"}],
    "docs": [{"status": "done", "content": "# Backend README"}],
}


class TestExplainFolder:
    def test_calls_analyze_then_onboard_when_no_codebase_id(self, mocker, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        client = _mock_client(
            mocker,
            post_side_effect=[_response(ANALYZE_RESULT), _response(EXPLAIN_FOLDER_ONBOARD_RESULT)],
        )
        mocker.patch("server._poll_package", return_value=EXPLAIN_FOLDER_PACKAGE_DONE)

        result = server.explain_folder("backend", project_path=str(tmp_path), save_to_disk=False)

        assert client.post.call_count == 2
        first_call, second_call = client.post.call_args_list
        assert first_call.args[0] == "/api/analyze"
        assert second_call.args[0] == "/api/onboard"
        assert second_call.kwargs["json"]["package_type"] == "quick"
        assert "backend/" in second_call.kwargs["json"]["custom_instructions"]
        assert result["video_url"] == "https://x/folder.mp4"
        assert result["readme_content"] == "# Backend README"

    def test_skips_analyze_when_codebase_id_given(self, mocker, tmp_path):
        client = _mock_client(mocker, post_side_effect=[_response(EXPLAIN_FOLDER_ONBOARD_RESULT)])
        mocker.patch("server._poll_package", return_value=EXPLAIN_FOLDER_PACKAGE_DONE)

        result = server.explain_folder(
            "backend", codebase_id="cb-1", project_path=str(tmp_path), save_to_disk=False
        )

        client.post.assert_called_once()
        assert client.post.call_args.args[0] == "/api/onboard"
        assert result["codebase_id"] == "cb-1"

    def test_saves_video_and_readme_to_disk(self, mocker, tmp_path):
        mock_download = mocker.patch("server._download_file")
        _mock_client(mocker, post_side_effect=[_response(EXPLAIN_FOLDER_ONBOARD_RESULT)])
        mocker.patch("server._poll_package", return_value=EXPLAIN_FOLDER_PACKAGE_DONE)

        result = server.explain_folder(
            "backend", codebase_id="cb-1", project_path=str(tmp_path), save_to_disk=True
        )

        mock_download.assert_called_once()
        assert result["video_saved_to"].endswith("backend_detail.mp4")
        readme_path = Path(tmp_path) / "project-docs" / "docs" / "backend" / "README.md"
        assert readme_path.read_text(encoding="utf-8") == "# Backend README"
        assert result["readme_saved_to"] == str(readme_path)

    def test_returns_status_when_package_not_done(self, mocker, tmp_path):
        _mock_client(mocker, post_side_effect=[_response(EXPLAIN_FOLDER_ONBOARD_RESULT)])
        mocker.patch("server._poll_package", return_value={"status": "timeout", "message": "still going"})

        result = server.explain_folder("backend", codebase_id="cb-1", project_path=str(tmp_path))

        assert result["status"] == "timeout"
        assert result["video_url"] is None


class TestGetPackageStatus:
    def test_calls_get_api_package(self, mocker):
        client = _mock_client(mocker, get_side_effect=[_response({"status": "done"})])
        result = server.get_package_status("pkg-1")

        client.get.assert_called_once_with("/api/package/pkg-1")
        assert result == {"status": "done"}


class TestListSupportedLanguages:
    def test_returns_expected_structure(self):
        result = server.list_supported_languages()

        assert "python" in result["languages"]
        assert result["extensions"][".py"] == "python"
        assert "note" in result
