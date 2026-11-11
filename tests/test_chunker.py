from unittest.mock import patch

import pytest
from requests import Response

from app.rag.chunker import MAX_CHUNK_CHARS, MAX_CHUNK_LINES, chunk_code_file
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
    response = Response()
    response.status_code = 200
    response.headers["Content-Type"] = "application/vnd.github.raw; charset=utf-8"
    response._content = b"source text"

    with patch("app.services.github_client.requests.get", return_value=response) as get:
        contents = get_file(
            "owner",
            "repo",
            "src",
            "file name.py",
            "token",
        )

    assert contents == "source text"
    args, kwargs = get.call_args
    assert args[0] == (
        "https://api.github.com/repos/owner/repo/contents/src/file%20name.py"
    )
    assert kwargs["headers"]["Accept"] == "application/vnd.github.raw"
    assert kwargs["headers"]["Authorization"] == "Bearer token"
    assert kwargs["params"] is None
    assert kwargs["timeout"] == 10.0


def test_python_module_keeps_code_before_between_and_after_symbols() -> None:
    source = (
        "from storage import open_db\r\n"
        "DATABASE_TIMEOUT = 30\r\n"
        "\r\n"
        "@registered\r\n"
        "def connect():\r\n"
        "    return open_db(timeout=DATABASE_TIMEOUT)\r\n"
        "\r\n"
        "session = connect()\r\n"
        "\r\n"
        "def shutdown():\r\n"
        "    session.close()\r\n"
        "\r\n"
        "register_handler(shutdown)"
    )

    chunks = chunk_code_file(source, "src/connection.py")

    assert [chunk["symbol"] for chunk in chunks] == [
        "connection.py:lines 1-3",
        "connect",
        "connection.py:lines 7-9",
        "shutdown",
        "connection.py:lines 12-13",
    ]
    assert [(chunk["start_line"], chunk["end_line"]) for chunk in chunks] == [
        (1, 3), (4, 6), (7, 9), (10, 11), (12, 13),
    ]
    assert "".join(chunk["content"] for chunk in chunks) == source
    assert all(chunk["language"] == "python" for chunk in chunks)
    assert all(chunk["parse_status"] == "parsed" for chunk in chunks)


@pytest.mark.parametrize("filename", ["module.js", "module.ts"])
def test_exports_and_multiple_bindings_are_preserved_without_duplication(filename: str) -> None:
    source = (
        'import { ready } from "./config";\n'
        "export const limit = 3;\n"
        "export const first = () => limit, second = () => first();\n"
        "export function start() { return ready(); }\n"
        "start();\n"
    )

    chunks = chunk_code_file(source, filename)
    symbols = {chunk["symbol"]: chunk["content"] for chunk in chunks}

    assert symbols["first"] == "first = () => limit"
    assert symbols["second"] == "second = () => first()"
    assert symbols["start"] == "export function start() { return ready(); }\n"
    assert "".join(chunk["content"] for chunk in chunks) == source
    assert all(chunk["parse_status"] == "parsed" for chunk in chunks)


@pytest.mark.parametrize(
    ("filename", "source", "language", "status"),
    [
        ("settings.py", 'TIMEOUT = 30\nconfigure("local")\n', "python", "parsed"),
        ("settings.yaml", "database:\n  timeout: 30\n", None, "unsupported"),
    ],
)
def test_files_without_symbols_keep_all_configuration(
    filename: str, source: str, language: str | None, status: str
) -> None:
    chunks = chunk_code_file(source, filename)

    assert chunks == [{
        "filename": filename,
        "language": language,
        "parse_status": status,
        "symbol": f"{filename}:lines 1-2",
        "start_line": 1,
        "end_line": 2,
        "content": source,
    }]


def test_python_class_context_keeps_fields_docs_and_nested_classes() -> None:
    source = (
        "@service\n"
        "class Service(Base):\n"
        '    """Service documentation."""\n'
        "    count = initialize()\n"
        "    def first(self):\n"
        "        return 101\n"
        "    class Nested:\n"
        "        enabled = True\n"
        "        def run(self):\n"
        "            return 202\n"
        "    limit = 3\n"
        "    @tracked\n"
        "    def second(self):\n"
        "        return 303\n"
    )

    chunks = chunk_code_file(source, "service.py")

    assert [chunk["symbol"] for chunk in chunks] == [
        "Service", "Service.first", "Service.Nested", "Service.Nested.run",
        "Service", "Service.second",
    ]
    assert chunks[0]["content"] == "".join(source.splitlines(keepends=True)[:4])
    assert chunks[4]["content"] == "    limit = 3\n"
    assert (chunks[-1]["start_line"], chunks[-1]["end_line"]) == (12, 14)
    assert chunks[-1]["content"].startswith("    @tracked\n")
    assert "".join(chunk["content"] for chunk in chunks) == source


def test_java_class_context_keeps_initializers_and_same_line_members() -> None:
    source = (
        "/** Service docs. */\n"
        "class Service extends Base {\n"
        '    static String label = "caf\u00e9"; static { initialize(); }\n'
        "    { load(); }\n"
        "    static class Nested { void run() { execute(); } }\n"
        "    Service() { setup(); } void reset() { clear(); }\n"
        "}\n"
    )

    chunks = chunk_code_file(source, "Service.java")
    symbols = {chunk["symbol"]: chunk for chunk in chunks}
    context = "".join(chunk["content"] for chunk in chunks if chunk["symbol"] == "Service")

    assert "/** Service docs. */" in context
    assert 'label = "caf\u00e9"' in context
    assert "static { initialize(); }" in context
    assert "{ load(); }" in context
    assert symbols["Service.Nested.run"]["content"] == "void run() { execute(); } "
    assert symbols["Service.Nested.run"]["start_line"] == 5
    assert symbols["Service.Service"]["start_line"] == symbols["Service.reset"]["start_line"] == 6
    assert "".join(chunk["content"] for chunk in chunks) == source


def test_tsx_class_method_includes_decorator_and_jsx_body() -> None:
    source = (
        "export class Component {\n"
        "  @decorate\n"
        "  render() { return <div />; }\n"
        "}\n"
    )

    chunks = chunk_code_file(source, "Component.tsx")
    method = next(chunk for chunk in chunks if chunk["symbol"] == "Component.render")

    assert method["language"] == "tsx"
    assert (method["start_line"], method["end_line"]) == (2, 3)
    assert method["content"] == "  @decorate\n  render() { return <div />; }\n"
    assert "".join(chunk["content"] for chunk in chunks) == source


def test_large_function_is_split_into_overlapping_original_line_ranges() -> None:
    source = "LIMIT = 5\n\ndef process():\n" + "".join(
        f"    consume({index})\n" for index in range(550)
    )
    lines = source.splitlines(keepends=True)

    chunks = chunk_code_file(source, "batch.py")
    function = [chunk for chunk in chunks if chunk["symbol"] == "process"]

    assert [(chunk["start_line"], chunk["end_line"]) for chunk in function] == [
        (3, 102), (93, 192), (183, 282), (273, 372), (363, 462), (453, 552), (543, 553),
    ]
    for chunk in function:
        start, end = chunk["start_line"], chunk["end_line"]
        assert end - start + 1 <= MAX_CHUNK_LINES
        assert len(chunk["content"]) <= MAX_CHUNK_CHARS
        assert chunk["content"] == "".join(lines[start - 1 : end])


def test_character_limit_reduces_overlap_to_fit_new_lines() -> None:
    source = "def f():\n" + "    step(1)\n" * 4

    chunks = chunk_python_file(source, "batch.txt", max_lines=5, max_chars=24, overlap_lines=3)

    assert [(chunk["start_line"], chunk["end_line"]) for chunk in chunks] == [
        (1, 2), (2, 3), (3, 4), (4, 5),
    ]
    assert all(chunk["symbol"] == "f" and chunk["language"] == "python" for chunk in chunks)
    assert all(len(chunk["content"]) <= 24 for chunk in chunks)


@pytest.mark.parametrize("filename", ["long.py", "long.txt"])
def test_very_long_unicode_lines_are_split_without_changing_source(filename: str) -> None:
    source = 'def f():\r\n    return "' + "\U0001f408" * 80 + '"\r\n'

    chunks = chunk_code_file(source, filename, max_chars=21)

    assert chunks[0]["content"] == "def f():\r\n"
    assert len(chunks) > 2
    assert all(chunk["start_line"] == chunk["end_line"] == 2 for chunk in chunks[1:])
    assert all(0 < len(chunk["content"]) <= 21 for chunk in chunks)
    assert "".join(chunk["content"] for chunk in chunks) == source


@pytest.mark.parametrize("filename", ["blank.py", "blank.yml"])
def test_blank_windows_do_not_create_chunks(filename: str) -> None:
    assert chunk_code_file(" \n\t\n" * 200, filename) == []


@pytest.mark.parametrize("limits", [{"max_lines": 0}, {"max_chars": 0}, {"overlap_lines": -1}])
def test_invalid_chunk_limits_fail_before_splitting(limits: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="Chunk limits"):
        chunk_code_file("setting: true\n", "settings.yaml", **limits)


@pytest.mark.parametrize(
    ("filename", "source", "symbol", "malformed"),
    [
        ("broken.py", "def okay():\n    pass\n\ndef broken(:\n    pass\n", "okay", "def broken(:"),
        (
            "broken.ts",
            "export function okay(): number { return 1; }\n"
            "export const broken: number = ;\nexport const ready = true;\n",
            "okay",
            "export const broken: number = ;",
        ),
        (
            "broken.js",
            "class Service {\n  broken = ;\n  run() { return 1; }\n}\n",
            "Service.run",
            "broken = ;",
        ),
    ],
)
def test_parse_errors_keep_valid_symbols_and_malformed_text(
    filename: str, source: str, symbol: str, malformed: str
) -> None:
    chunks = chunk_code_file(source, filename, max_lines=2, overlap_lines=0)

    assert any(chunk["symbol"] == symbol for chunk in chunks)
    assert any(
        chunk["symbol"].startswith(f"{filename}:lines ") and malformed in chunk["content"]
        for chunk in chunks
    )
    assert all(chunk["parse_status"] == "syntax_error" for chunk in chunks)
    assert "".join(chunk["content"] for chunk in chunks) == source


@pytest.mark.parametrize("during_parse", [False, True])
def test_parser_exceptions_use_bounded_text_fallback(during_parse: bool) -> None:
    source = "def run():\n    return 1\n"
    with patch("app.rag.chunker.get_parser") as get_parser:
        failing = get_parser.return_value.parse if during_parse else get_parser
        failing.side_effect = RuntimeError("parser unavailable")
        chunks = chunk_code_file(source, "service.py", max_lines=1)

    assert [(chunk["start_line"], chunk["end_line"]) for chunk in chunks] == [(1, 1), (2, 2)]
    assert all(chunk["parse_status"] == "parser_error" for chunk in chunks)
    assert "".join(chunk["content"] for chunk in chunks) == source


def test_deeply_nested_tree_falls_back_when_traversal_cannot_finish() -> None:
    nested = "(" * 2_000 + "value" + ")" * 2_000
    source = f"def f():\n    return 1\n\nresult = {nested}\n"

    chunks = chunk_code_file(source, "nested.py", max_chars=500)

    assert all(chunk["parse_status"] == "parser_error" for chunk in chunks)
    assert all(len(chunk["content"]) <= 500 for chunk in chunks)
    assert "".join(chunk["content"] for chunk in chunks) == source
