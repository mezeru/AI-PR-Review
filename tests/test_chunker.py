from unittest.mock import Mock, patch

import pytest

from app.rag.chunker import chunk_code_file
from app.rag.chunking_python import chunk_python_file
from app.services.github_client import get_file


def test_python_chunks_include_decorators_async_functions_and_methods() -> None:
    source = (
        "@decorator\n"
        "async def fetch():\n"
        "    return 1\n"
        "\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return 2\n"
    )

    chunks = chunk_python_file(source, "service.py")

    assert [chunk["symbol"] for chunk in chunks] == [
        "fetch",
        "Service",
        "Service.run",
    ]
    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 3
    assert chunks[0]["content"] == "@decorator\nasync def fetch():\n    return 1\n"
    assert chunks[2]["start_line"] == 6


@pytest.mark.parametrize(
    ("filename", "source", "expected_symbol"),
    [
        ("module.js", "export const work = (x) => x + 1;\n", "work"),
        ("default.js", "export default () => 1;\n", "default"),
        ("module.ts", "class Service {\n  run() {}\n}\n", "Service.run"),
        ("Service.java", "class Service {\n  void run() {}\n}\n", "Service.run"),
    ],
)
def test_chunk_code_file_extracts_supported_languages(
    filename: str,
    source: str,
    expected_symbol: str,
) -> None:
    chunks = chunk_code_file(source, filename)

    assert expected_symbol in [chunk["symbol"] for chunk in chunks]
    assert all(chunk["filename"] == filename for chunk in chunks)


def test_chunk_code_file_uses_bounded_text_fallback() -> None:
    source = "".join(f"line {line}\n" for line in range(1, 202))

    chunks = chunk_code_file(source, "settings.yaml")

    assert [(chunk["start_line"], chunk["end_line"]) for chunk in chunks] == [
        (1, 100),
        (101, 200),
        (201, 201),
    ]
    assert chunks[-1]["content"] == "line 201\n"


def test_get_file_returns_raw_content_and_uses_authenticated_contents_endpoint() -> None:
    response = Mock()
    response.text = "source text"

    with patch("app.services.github_client.requests.get", return_value=response) as get:
        contents = get_file(
            "owner",
            "repo",
            "src",
            "file name.py",
            "token",
        )

    assert contents == "source text"
    response.raise_for_status.assert_called_once_with()
    args, kwargs = get.call_args
    assert args[0] == (
        "https://api.github.com/repos/owner/repo/contents/src/file%20name.py"
    )
    assert kwargs["headers"]["Accept"] == "application/vnd.github.raw"
    assert kwargs["timeout"] == 10.0
