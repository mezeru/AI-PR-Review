from app.rag.models import SymbolMetadata
from app.rag.symbol_extractor import extract_symbol_metadata


def _by_symbol(metadata: list[SymbolMetadata]) -> dict[str, SymbolMetadata]:
    return {item["symbol"]: item for item in metadata}


def test_python_functions_classes_docs_nested_scopes_and_multiline_signatures() -> None:
    source = (
        "async def fetch_users(\n"
        "    limit: int = 10,\n"
        ") -> list:\n"
        '    """Fetches users."""\n'
        "    return [limit]\n"
        "\n"
        "@register\n"
        "def make_user(name: str) -> str:\n"
        "    return name\n"
        "\n"
        "class UserService:\n"
        "    def delete_user(self, user_id: int) -> bool:\n"
        '        """Deletes a user."""\n'
        "        return True\n"
        "\n"
        "    def no_docs(self):\n"
        "        return None\n"
        "\n"
        "    class Nested:\n"
        "        async def run(self, value: str = 'x') -> str:\n"
        "            return value\n"
    )

    metadata = extract_symbol_metadata(source, "app/services/user.py")
    symbols = _by_symbol(metadata)

    assert set(symbols) == {
        "fetch_users",
        "make_user",
        "UserService",
        "UserService.delete_user",
        "UserService.no_docs",
        "UserService.Nested",
        "UserService.Nested.run",
    }
    assert symbols["fetch_users"]["signature"] == (
        "async def fetch_users(\n    limit: int = 10,\n) -> list:"
    )
    assert symbols["fetch_users"]["docstring"] == "Fetches users."
    assert symbols["make_user"]["signature"] == "def make_user(name: str) -> str:"
    assert symbols["make_user"]["start_line"] == 7
    assert symbols["make_user"]["end_line"] == 9
    assert symbols["UserService.delete_user"]["signature"] == (
        "def delete_user(self, user_id: int) -> bool:"
    )
    assert symbols["UserService.delete_user"]["docstring"] == "Deletes a user."
    assert symbols["UserService.no_docs"]["docstring"] is None
    assert symbols["UserService.Nested.run"]["signature"].startswith("async def run(")
    assert all(item["parse_status"] == "parsed" for item in metadata)
    assert all("return True" not in str(item) for item in metadata)


def test_python_decorators_are_in_ranges_but_not_callable_signatures() -> None:
    source = "@cache\n@retry\nasync def load():\n    return 1\n"

    item = extract_symbol_metadata(source, "load.py")[0]

    assert item["symbol"] == "load"
    assert item["signature"] == "async def load():"
    assert (item["start_line"], item["end_line"]) == (1, 4)


def test_python_module_constants_and_unicode_line_locations() -> None:
    source = (
        'GREETING = "caf\u00e9 \u2603"\n'
        "LIMIT: int = 20\n"
        "\n"
        "def greet():\n"
        "    return GREETING\n"
    )

    metadata = extract_symbol_metadata(source, "messages.py")
    symbols = _by_symbol(metadata)

    assert symbols["GREETING"]["symbol_type"] == "variable"
    assert symbols["GREETING"]["signature"] == "GREETING"
    assert symbols["GREETING"]["start_line"] == symbols["GREETING"]["end_line"] == 1
    assert symbols["LIMIT"]["signature"] == "LIMIT: int"
    assert (symbols["greet"]["start_line"], symbols["greet"]["end_line"]) == (4, 5)
    assert "\u2603" not in str(metadata)


def test_javascript_exports_arrow_functions_methods_and_jsdoc() -> None:
    source = (
        "/** Loads a user. */\n"
        "export function loadUser(id) {\n"
        "  return id;\n"
        "}\n"
        "\n"
        "export const lookup = async (id) => {\n"
        "  return id;\n"
        "};\n"
        "\n"
        "class Service {\n"
        "  async deleteUser(id) {\n"
        "    return id;\n"
        "  }\n"
        "}\n"
    )

    metadata = extract_symbol_metadata(source, "service.js")
    symbols = _by_symbol(metadata)

    assert symbols["loadUser"]["signature"] == "export function loadUser(id)"
    assert symbols["loadUser"]["docstring"] == "Loads a user."
    assert symbols["lookup"]["signature"] == "export const lookup = async (id)"
    assert symbols["lookup"]["symbol_type"] == "function"
    assert symbols["Service.deleteUser"]["signature"] == "async deleteUser(id)"
    assert symbols["Service.deleteUser"]["symbol_type"] == "method"
    assert (symbols["Service.deleteUser"]["start_line"], symbols["Service.deleteUser"]["end_line"]) == (
        11,
        13,
    )
    assert all("return id" not in str(item) for item in metadata)


def test_typescript_interface_signatures_and_exported_arrow_signature() -> None:
    source = (
        "export interface UserRepository {\n"
        "  /** Finds a user. */\n"
        "  find(id: number): Promise<User>;\n"
        "}\n"
        "export const findUser = (id: number): Promise<User> => repository.find(id);\n"
    )

    symbols = _by_symbol(extract_symbol_metadata(source, "users.ts"))

    assert symbols["UserRepository"]["symbol_type"] == "interface"
    assert symbols["UserRepository.find"]["symbol_type"] == "method"
    assert symbols["UserRepository.find"]["signature"] == "find(id: number): Promise<User>"
    assert symbols["UserRepository.find"]["docstring"] == "Finds a user."
    assert symbols["findUser"]["signature"] == (
        "export const findUser = (id: number): Promise<User>"
    )
    assert symbols["findUser"]["end_line"] == 5


def test_tsx_component_is_indexed_without_jsx_body() -> None:
    source = "export const Panel = (name: string) => <section>{name}</section>;\n"

    item = extract_symbol_metadata(source, "Panel.tsx")[0]

    assert item["symbol"] == "Panel"
    assert item["language"] == "tsx"
    assert item["signature"] == "export const Panel = (name: string)"
    assert "section" not in str(item)


def test_default_export_arrow_has_a_stable_identity_and_body_free_signature() -> None:
    source = "export default async (userId) => fetchUser(userId);\n"

    item = extract_symbol_metadata(source, "lookup.js")[0]

    assert item["symbol"] == "default"
    assert item["symbol_type"] == "function"
    assert item["signature"] == "export default async (userId)"
    assert (item["start_line"], item["end_line"]) == (1, 1)
    assert "fetchUser" not in str(item)


def test_java_class_methods_constructor_interface_and_javadoc() -> None:
    source = (
        "/** User service API. */\n"
        "public class UserService {\n"
        "  /** Deletes one user. */\n"
        "  public boolean delete(Long id) {\n"
        "    return true;\n"
        "  }\n"
        "  private final String token = \"secret\";\n"
        "  public UserService() { }\n"
        "}\n"
        "interface UserRepository {\n"
        "  User find(Long id);\n"
        "}\n"
    )

    symbols = _by_symbol(extract_symbol_metadata(source, "UserService.java"))

    assert symbols["UserService"]["docstring"] == "User service API."
    assert symbols["UserService.delete"]["signature"] == "public boolean delete(Long id)"
    assert symbols["UserService.delete"]["docstring"] == "Deletes one user."
    assert symbols["UserService.UserService"]["symbol_type"] == "constructor"
    assert symbols["UserRepository"]["symbol_type"] == "interface"
    assert symbols["UserRepository.find"]["symbol_type"] == "method"
    assert symbols["UserRepository.find"]["signature"] == "User find(Long id);"
    assert symbols["UserService.token"]["signature"] == "private final String token"
    assert all("return true" not in str(item) for item in symbols.values())


def test_large_function_has_one_record_and_full_source_range() -> None:
    source = "def process():\n" + "".join(f"    step({n})\n" for n in range(500))

    metadata = extract_symbol_metadata(source, "batch.py")

    assert [item["symbol"] for item in metadata] == ["process"]
    assert (metadata[0]["start_line"], metadata[0]["end_line"]) == (1, 501)


def test_malformed_syntax_keeps_valid_metadata_and_marks_parse_status() -> None:
    source = "def okay():\n    return 1\n\ndef broken(:\n    pass\n"

    metadata = extract_symbol_metadata(source, "broken.py")

    assert [item["symbol"] for item in metadata] == ["okay"]
    assert metadata[0]["parse_status"] == "syntax_error"
    assert (metadata[0]["start_line"], metadata[0]["end_line"]) == (1, 2)


def test_file_fallbacks_for_unsupported_empty_and_configuration_files() -> None:
    unsupported_source = "settings:\n  theme: dark\n"
    unsupported = extract_symbol_metadata(unsupported_source, "config/settings.yml")
    config = extract_symbol_metadata("TIMEOUT = 30\n", "settings.py")

    assert unsupported == [
        {
            "filename": "config/settings.yml",
            "language": None,
            "symbol": "config/settings.yml",
            "symbol_type": "file",
            "signature": None,
            "docstring": None,
            "start_line": 1,
            "end_line": 2,
            "parse_status": "unsupported",
        }
    ]
    assert extract_symbol_metadata("", "empty.py") == []
    assert [item["symbol"] for item in config] == ["TIMEOUT"]
    assert "30" not in str(config)


def test_documentation_is_bounded_and_missing_or_empty_docs_are_none() -> None:
    long_doc = "x" * 1_200
    python_metadata = extract_symbol_metadata(
        f'def documented():\n    """{long_doc}"""\n    pass\n',
        "docs.py",
    )
    js_metadata = extract_symbol_metadata(
        "/** */\nfunction emptyDocs() { return 1; }\n"
        "function noDocs() { return 2; }\n",
        "docs.js",
    )

    assert len(python_metadata[0]["docstring"]) <= 1_000
    assert js_metadata[0]["docstring"] is None
    assert js_metadata[1]["docstring"] is None


def test_metadata_has_no_body_field_and_one_entry_per_declaration() -> None:
    source = "export const run = () => { return 'secret-value'; };\n"

    metadata = extract_symbol_metadata(source, "run.js")

    assert len(metadata) == 1
    assert set(metadata[0]) == {
        "filename",
        "language",
        "symbol",
        "symbol_type",
        "signature",
        "docstring",
        "start_line",
        "end_line",
        "parse_status",
    }
    assert "secret-value" not in str(metadata)
