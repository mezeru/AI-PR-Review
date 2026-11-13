from unittest.mock import patch

import pytest
from requests import Response, Timeout
from requests.exceptions import HTTPError

from app.models.pr_model import PullRequestContext
from app.rag.ingestion import chunk_pr_files
from app.services.github_client import get_file


HEAD_SHA = "b" * 40
PR_URL = "https://github.com/Owner/Repo/pull/3"


def _response(
    content: bytes, *, status: int = 200, media_type: str = "application/vnd.github.raw"
) -> Response:
    response = Response()
    response.status_code = status
    response.headers["Content-Type"] = media_type
    response._content = content
    return response


@pytest.fixture
def pr_context() -> PullRequestContext:
    return {
        "title": "Update service",
        "description": "",
        "base_sha": "a" * 40,
        "head_sha": HEAD_SHA,
        "files": [],
    }


def test_get_file_sends_commit_sha_and_preserves_raw_utf8_source() -> None:
    source = '{"name": "caf\u00e9"}\r\n'
    response = _response(source.encode("utf-8"))

    with patch("app.services.github_client.requests.get", return_value=response) as request:
        contents = get_file("owner", "repo", "src", "caf\u00e9 #?%.json", "token", 5, ref=HEAD_SHA)

    assert contents == source
    request.assert_called_once_with(
        "https://api.github.com/repos/owner/repo/contents/src/caf%C3%A9%20%23%3F%25.json",
        headers={"Accept": "application/vnd.github.raw", "Authorization": "Bearer token"},
        params={"ref": HEAD_SHA},
        timeout=5,
    )


@pytest.mark.parametrize("status", [404, 403, 500])
def test_get_file_http_errors_do_not_retry_at_default_branch(status: int) -> None:
    response = _response(b'{"message":"request failed"}', status=status)
    with patch("app.services.github_client.requests.get", return_value=response) as request:
        with pytest.raises(RuntimeError, match="Failed to fetch file") as exc:
            get_file("owner", "repo", "", "src/app.py", None, ref=HEAD_SHA)

    assert isinstance(exc.value.__cause__, HTTPError)
    assert exc.value.__cause__.response is response
    assert request.call_count == 1
    assert request.call_args.kwargs["params"] == {"ref": HEAD_SHA}


def test_get_file_preserves_timeout_error_as_cause() -> None:
    timeout = Timeout("timed out")
    with patch("app.services.github_client.requests.get", side_effect=timeout) as request:
        with pytest.raises(RuntimeError, match="Failed to fetch file") as exc:
            get_file("owner", "repo", "", "app.py", None, ref=HEAD_SHA)

    assert exc.value.__cause__ is timeout
    assert request.call_count == 1


@pytest.mark.parametrize("content", [b'{"type":"file","content":"eA=="}', b"[]"])
def test_get_file_rejects_metadata_and_directory_responses(content: bytes) -> None:
    response = _response(content, media_type="application/json; charset=utf-8")
    with patch("app.services.github_client.requests.get", return_value=response):
        with pytest.raises(ValueError, match="raw file content"):
            get_file("owner", "repo", "", "app.py", None, ref=HEAD_SHA)


def test_get_file_rejects_non_utf8_content() -> None:
    with patch("app.services.github_client.requests.get", return_value=_response(b"\xff")):
        with pytest.raises(UnicodeDecodeError):
            get_file("owner", "repo", "", "app.py", None, ref=HEAD_SHA)


@pytest.mark.parametrize("path", ["src/../app.py", "src//app.py", "/app.py", "src\\app.py", "a\0.py"])
def test_get_file_rejects_invalid_paths_before_requesting(path: str) -> None:
    with patch("app.services.github_client.requests.get") as request:
        with pytest.raises(ValueError, match="Invalid file path"):
            get_file("owner", "repo", "", path, None, ref=HEAD_SHA)

    request.assert_not_called()


def test_chunk_pr_files_fetches_each_mixed_language_path_at_the_head_sha(
    pr_context: PullRequestContext,
) -> None:
    paths = ["src/service.py", "web/view.tsx", "settings.yaml"]
    responses = [
        _response(b"def run():\n    return 1\n"),
        _response(b"export const View = () => <div />;\n"),
        _response(b"theme: dark\n"),
    ]

    with patch("app.services.github_client.requests.get", side_effect=responses) as request:
        result = chunk_pr_files(PR_URL, pr_context, [*paths, paths[0]], token="token")

    assert (result.owner, result.repo, result.head_sha) == ("owner", "repo", HEAD_SHA)
    assert [call.args[0].split("/contents/")[1] for call in request.call_args_list] == paths
    assert all(call.kwargs["params"] == {"ref": HEAD_SHA} for call in request.call_args_list)
    assert [(c["filename"], c["language"], c["symbol"]) for c in result.chunks] == [
        ("src/service.py", "python", "run"),
        ("web/view.tsx", "tsx", "View"),
        ("settings.yaml", None, "settings.yaml:lines 1-1"),
    ]


@pytest.mark.parametrize("head_sha", ["", "main", "abc123"])
def test_chunk_pr_files_rejects_unpinned_revisions(pr_context: PullRequestContext, head_sha: str) -> None:
    pr_context["head_sha"] = head_sha
    with patch("app.services.github_client.requests.get") as request:
        with pytest.raises(ValueError, match="head_sha must be a full commit SHA"):
            chunk_pr_files(PR_URL, pr_context, ["app.py"])

    request.assert_not_called()
