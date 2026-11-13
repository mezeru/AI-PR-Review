import pytest

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
        "app/services/user.py",
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

    assert [item["symbol"] for item in metadata] == ["process", "batch.py"]
    assert (metadata[0]["start_line"], metadata[0]["end_line"]) == (1, 501)


def test_malformed_syntax_keeps_valid_metadata_and_marks_parse_status() -> None:
    source = "def okay():\n    return 1\n\ndef broken(:\n    pass\n"

    metadata = extract_symbol_metadata(source, "broken.py")

    assert [item["symbol"] for item in metadata] == ["okay", "broken.py"]
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
    assert [item["symbol"] for item in config] == ["TIMEOUT", "settings.py"]
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

    assert [(item["symbol"], item["symbol_type"]) for item in metadata] == [
        ("run", "function"), ("run.js", "file"),
    ]
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


def test_python_attributes_are_qualified_and_local_variables_are_excluded() -> None:
    source = (
        "GLOBAL = 30\n"
        "class Config:\n"
        '    TOKEN = "attribute-secret"\n'
        '    NAME: str = "annotated-secret"\n'
        "    TIMEOUT: int\n"
        "    class Database:\n"
        "        MAX_CONNECTIONS: int = 40\n"
        "    def connect(self):\n"
        "        local = 1\n"
        "        self.instance_value = local\n"
    )

    metadata = extract_symbol_metadata(source, "config.py")
    attributes = [item for item in metadata if item["symbol_type"] == "variable"]

    assert [(item["symbol"], item["signature"]) for item in attributes] == [
        ("GLOBAL", "GLOBAL"),
        ("Config.TOKEN", "TOKEN"),
        ("Config.NAME", "NAME: str"),
        ("Config.TIMEOUT", "TIMEOUT: int"),
        ("Config.Database.MAX_CONNECTIONS", "MAX_CONNECTIONS: int"),
    ]
    assert [(item["start_line"], item["end_line"]) for item in attributes] == [
        (1, 1), (3, 3), (4, 4), (5, 5), (7, 7),
    ]
    assert _by_symbol(metadata)["Config.connect"]["symbol_type"] == "method"
    assert "secret" not in repr(metadata)


def test_python_nested_functions_include_async_and_method_local_definitions() -> None:
    source = (
        "def outer():\n"
        "    local: int = 1\n"
        "    async def inner(value):\n"
        "        def leaf():\n"
        "            return value\n"
        "        return leaf()\n"
        "    return inner(local)\n"
        "class Service:\n"
        "    def run(self):\n"
        "        @checked\n"
        "        async def validate():\n"
        "            return True\n"
        "        return validate()\n"
    )

    metadata = extract_symbol_metadata(source, "scopes.py")

    assert [
        (item["symbol"], item["symbol_type"], item["start_line"], item["end_line"])
        for item in metadata
    ] == [
        ("outer", "function", 1, 7),
        ("outer.inner", "function", 3, 6),
        ("outer.inner.leaf", "function", 4, 5),
        ("Service", "class", 8, 13),
        ("Service.run", "method", 9, 13),
        ("Service.run.validate", "function", 10, 12),
        ("scopes.py", "file", 1, 13),
    ]
    assert _by_symbol(metadata)["Service.run.validate"]["signature"] == "async def validate():"


def test_javascript_nested_function_declarations_exclude_anonymous_callbacks() -> None:
    source = (
        "function outer() {\n"
        "  const ordinary = 1;\n"
        "  async function inner() { return ordinary; }\n"
        "  register(() => { function callbackLocal() {} });\n"
        "}\n"
    )

    metadata = extract_symbol_metadata(source, "scopes.js")

    assert [item["symbol"] for item in metadata] == ["outer", "outer.inner", "scopes.js"]
    assert metadata[1]["signature"] == "async function inner()"
    assert (metadata[1]["start_line"], metadata[1]["end_line"]) == (3, 3)


@pytest.mark.parametrize(
    ("filename", "parameter", "result_type", "body", "language"),
    [
        ("controller.js", "id", "", "lookup(id)", "javascript"),
        ("controller.jsx", "id", "", "<div>{id}</div>", "javascript"),
        ("controller.ts", "id: number", ": Promise<number>", "lookup(id)", "typescript"),
        ("controller.tsx", "id: number", ": Promise<JSX.Element>", "<div>{id}</div>", "tsx"),
    ],
)
def test_callable_class_fields_are_methods_in_the_javascript_family(
    filename: str, parameter: str, result_type: str, body: str, language: str
) -> None:
    source = (
        "class UserController {\n"
        f"  static load = async ({parameter}){result_type} => {{\n"
        f"    return {body};\n"
        "  };\n"
        "  #save = function named(value) { return value; };\n"
        "  reset() { return 1; }\n"
        '  token = "field-secret";\n'
        "}\n"
    )

    metadata = extract_symbol_metadata(source, filename)
    symbols = _by_symbol(metadata)

    assert [item["symbol"] for item in metadata] == [
        "UserController", "UserController.load", "UserController.#save", "UserController.reset",
        filename,
    ]
    load = symbols["UserController.load"]
    assert load["language"] == language
    assert load["symbol_type"] == "method"
    assert load["signature"] == f"static load = async ({parameter}){result_type}"
    assert (load["start_line"], load["end_line"]) == (2, 4)
    assert symbols["UserController.#save"]["signature"] == "#save = function named(value)"
    assert symbols["UserController.reset"]["symbol_type"] == "method"
    assert all(item["parse_status"] == "parsed" for item in metadata)
    assert "field-secret" not in repr(metadata)
    assert "return " not in repr(metadata)


@pytest.mark.parametrize(
    ("filename", "param", "result_type"),
    [("api.js", "id", ""), ("api.ts", "id: number", ": number")],
)
def test_object_methods_use_binding_and_nested_property_names(
    filename: str, param: str, result_type: str
) -> None:
    source = (
        "export const handlers = {\n"
        f"  deleteUser({param}){result_type} {{ return id; }},\n"
        "  createUser: async (data) => {\n"
        "    return store.create(data);\n"
        "  },\n"
        '  "admin-v2": {\n'
        '    "reset-user": function resetAccount() { resetInternal(); },\n'
        "    enabled: true,\n"
        "  },\n"
        "  alias: createUser,\n"
        '  token: "property-secret",\n'
        '  [(() => "dynamic-key-secret")()]() {},\n'
        "};\n"
        "register({ incidental() {} });\n"
    )

    metadata = extract_symbol_metadata(source, filename)

    assert [(item["symbol"], item["symbol_type"], item["signature"]) for item in metadata] == [
        ("handlers", "variable", "export const handlers"),
        ("handlers.deleteUser", "method", f"deleteUser({param}){result_type}"),
        ("handlers.createUser", "method", "createUser: async (data)"),
        ("handlers.admin-v2.reset-user", "method", '"reset-user": function resetAccount()'),
        (filename, "file", None),
    ]
    assert [(item["start_line"], item["end_line"]) for item in metadata[1:4]] == [
        (2, 2), (3, 5), (7, 7),
    ]
    assert "property-secret" not in repr(metadata)
    assert "dynamic-key-secret" not in repr(metadata)
    assert "resetInternal" not in repr(metadata)


def test_typescript_object_retains_bounded_methods_with_unreliable_signatures() -> None:
    source = (
        "const api = {\n"
        "  broken(value: ): void {},\n"
        "  alsoBroken: (value: ) => {},\n"
        "  valid() {},\n"
        "};\n"
    )

    metadata = extract_symbol_metadata(source, "api.ts")

    assert [(item["symbol"], item["signature"]) for item in metadata] == [
        ("api", "const api"),
        ("api.broken", None),
        ("api.alsoBroken", None),
        ("api.valid", "valid()"),
        ("api.ts", None),
    ]
    assert (metadata[1]["start_line"], metadata[1]["end_line"]) == (2, 2)
    assert all(item["parse_status"] == "syntax_error" for item in metadata)


def test_python_keeps_a_function_when_recovery_places_suite_error_before_block() -> None:
    source = (
        "def process_payment(amount):\n"
        "    if amount > 0\n"
        "        charge(amount)\n"
        "\n"
        "def valid():\n"
        "    pass\n"
    )

    metadata = extract_symbol_metadata(source, "payments.py")

    assert [item["symbol"] for item in metadata] == ["process_payment", "valid", "payments.py"]
    assert metadata[0]["signature"] == "def process_payment(amount):"
    assert (metadata[0]["start_line"], metadata[0]["end_line"]) == (1, 3)
    assert all(item["parse_status"] == "syntax_error" for item in metadata)


def test_typescript_keeps_class_methods_with_body_errors_and_valid_siblings() -> None:
    source = (
        "export class Service {\n"
        "  broken(id: number): number {\n"
        "    const value = ;\n"
        "    return id;\n"
        "  }\n"
        "  okay() {}\n"
        "}\n"
        "export function elsewhere() {}\n"
    )

    metadata = extract_symbol_metadata(source, "service.ts")

    assert [item["symbol"] for item in metadata] == [
        "Service", "Service.broken", "Service.okay", "elsewhere", "service.ts",
    ]
    assert metadata[1]["signature"] == "broken(id: number): number"
    assert (metadata[1]["start_line"], metadata[1]["end_line"]) == (2, 5)
    assert all(item["parse_status"] == "syntax_error" for item in metadata)


@pytest.mark.parametrize(
    ("filename", "source"),
    [("bad.py", "def broken(a)\n    pass\n"), ("bad.js", "function broken( { return 3; }")],
)
def test_completely_invalid_declarations_only_emit_file_metadata(filename: str, source: str) -> None:
    metadata = extract_symbol_metadata(source, filename)

    assert [(item["symbol"], item["symbol_type"], item["parse_status"]) for item in metadata] == [
        (filename, "file", "syntax_error"),
    ]


def test_file_record_spans_route_registrations_without_storing_route_arguments() -> None:
    filename = "src/payments.js"
    source = (
        "const router = express.Router();\r\n"
        "\r\n"
        "function authenticate(req, res, next) { next(); }\r\n"
        "\r\n"
        'router.post("/v1/payments", authenticate, paymentHandler);'
    )

    metadata = extract_symbol_metadata(source, filename)

    assert [item["symbol"] for item in metadata] == ["router", "authenticate", filename]
    assert metadata[-1] == {
        "filename": filename,
        "symbol": filename,
        "language": "javascript",
        "symbol_type": "file",
        "signature": None,
        "docstring": None,
        "start_line": 1,
        "end_line": 5,
        "parse_status": "parsed",
    }
    assert "/v1/payments" not in repr(metadata)
    assert "paymentHandler" not in repr(metadata)


def test_parser_failure_emits_one_file_record(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_language: str) -> None:
        raise RuntimeError("parser unavailable")

    monkeypatch.setattr("app.rag.symbol_extractor.get_parser", fail)
    metadata = extract_symbol_metadata("\n\n", "blank.py")

    assert len(metadata) == 1
    assert metadata[0]["symbol_type"] == "file"
    assert metadata[0]["parse_status"] == "parser_error"
    assert (metadata[0]["start_line"], metadata[0]["end_line"]) == (1, 2)


def test_python_redacts_default_expressions_and_preserves_names_and_annotations() -> None:
    source = (
        'def connect(cl\u00e9: str = "caf\u00e9-secret", limit: int = 10,\n'
        '            config = {"key": "nested-secret"}) -> bool:\n'
        "    return True\n"
    )

    record = extract_symbol_metadata(source, "connect.py")[0]

    assert record["signature"] == (
        "def connect(cl\u00e9: str = ..., limit: int = 10,\n"
        "            config = ...) -> bool:"
    )
    assert "secret" not in repr(record)


def test_js_and_ts_redact_defaults_in_destructured_parameters_and_callable_fields() -> None:
    js = 'export default async ({key = "key-secret"} = {key: `outer-secret`}) => key;\n'
    ts = (
        "class Service {\n"
        '  load = async (id: string = "typed-secret"): Promise<string> => id;\n'
        "}\n"
    )

    js_record = extract_symbol_metadata(js, "connect.js")[0]
    ts_record = _by_symbol(extract_symbol_metadata(ts, "service.ts"))["Service.load"]

    assert js_record["signature"] == "export default async ({key = ...} = ...)"
    assert ts_record["signature"] == "load = async (id: string = ...): Promise<string>"
    assert "secret" not in repr([js_record, ts_record])


def test_variable_metadata_excludes_destructuring_defaults_and_earlier_initializers() -> None:
    js = 'const { key: local = "js-secret", token = "token-secret" } = config;\n'
    java = (
        "class Config {\n"
        '  private String first = "first-secret",\n'
        '                 second = "second-secret";\n'
        "}\n"
    )

    js_metadata = extract_symbol_metadata(js, "config.js")
    java_metadata = extract_symbol_metadata(java, "Config.java")

    assert [item["signature"] for item in js_metadata] == ["const local", "const token", None]
    second = _by_symbol(java_metadata)["Config.second"]
    assert second["signature"] == "private String second"
    assert (second["start_line"], second["end_line"]) == (3, 3)
    assert "secret" not in repr([js_metadata, java_metadata])
