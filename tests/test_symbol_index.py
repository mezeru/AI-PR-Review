import json
from unittest.mock import call, patch

import pytest
from requests import Response, Timeout

from app.rag.symbol_index import load_repository_symbols
from app.services.github_client import fetch_repository_file_paths


SHA = "c" * 40


def _json_response(data: object, *, status: int = 200) -> Response:
    response = Response()
    response.status_code = status
    response._content = json.dumps(data).encode("utf-8")
    return response


def test_fetch_repository_file_paths_returns_blobs_from_recursive_tree() -> None:
    response = _json_response(
        {
            "truncated": False,
            "tree": [
                {"path": "src", "type": "tree"},
                {"path": "src/app.py", "type": "blob"},
                {"path": "submodule", "type": "commit"},
            ],
        }
    )

    with patch("app.services.github_client.requests.get", return_value=response) as request:
        paths = fetch_repository_file_paths("owner", "repo", SHA, token="token")

    assert paths == ["src/app.py"]
    request.assert_called_once_with(
        f"https://api.github.com/repos/owner/repo/git/trees/{SHA}",
        params={"recursive": "1"},
        headers={"Accept": "application/vnd.github+json", "Authorization": "******"},
        timeout=10.0,
    )


def test_fetch_repository_file_paths_rejects_truncated_tree() -> None:
    response = _json_response({"truncated": True, "tree": []})
    with patch("app.services.github_client.requests.get", return_value=response):
        with pytest.raises(RuntimeError, match="truncated repository tree"):
            fetch_repository_file_paths("owner", "repo", SHA)


def test_fetch_repository_file_paths_rejects_missing_truncation_status() -> None:
    response = _json_response({"tree": []})
    with patch("app.services.github_client.requests.get", return_value=response):
        with pytest.raises(ValueError, match="missing truncation status"):
            fetch_repository_file_paths("owner", "repo", SHA)


def test_fetch_repository_file_paths_preserves_request_failure() -> None:
    timeout = Timeout("timed out")
    with patch("app.services.github_client.requests.get", side_effect=timeout):
        with pytest.raises(RuntimeError, match="Failed to fetch repository tree") as exc:
            fetch_repository_file_paths("owner", "repo", SHA)

    assert exc.value.__cause__ is timeout


def test_load_repository_symbols_fetches_files_at_requested_sha() -> None:
    with (
        patch(
            "app.rag.symbol_index.fetch_repository_file_paths",
            return_value=["src/app.py", "web/view.ts"],
        ),
        patch(
            "app.rag.symbol_index.get_file",
            side_effect=["def run():\n    return 1\n", "export function view() {}"],
        ) as get_file,
    ):
        symbols = load_repository_symbols("owner", "repo", SHA)

    assert [(item["filename"], item["symbol"]) for item in symbols] == [
        ("src/app.py", "run"),
        ("src/app.py", "src/app.py"),
        ("web/view.ts", "view"),
        ("web/view.ts", "web/view.ts"),
    ]
    assert get_file.call_args_list == [
        call("owner", "repo", "", "src/app.py", None, ref=SHA),
        call("owner", "repo", "", "web/view.ts", None, ref=SHA),
    ]


def test_load_repository_symbols_skips_non_utf8_file_and_continues() -> None:
    with (
        patch(
            "app.rag.symbol_index.fetch_repository_file_paths",
            return_value=["image.png", "src/app.py"],
        ),
        patch(
            "app.rag.symbol_index.get_file",
            side_effect=[
                UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
                "def run(): pass",
            ],
        ),
    ):
        symbols = load_repository_symbols("owner", "repo", SHA)

    assert [item["symbol"] for item in symbols] == ["run", "src/app.py"]
