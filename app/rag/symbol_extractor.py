import ast
import logging
import re
from pathlib import PurePath

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.rag.chunker import (
    _EXTRACTORS,
    _EXTENSIONS,
    _FUNCTION_VALUES,
    _declaration,
    _symbol_name,
)
from app.rag.models import ParseStatus, SymbolMetadata, SymbolType

MAX_DOCSTRING_CHARS = 1_000
MAX_SIGNATURE_CHARS = 1_000

logger = logging.getLogger(__name__)

_CLASS_TYPES: dict[str, SymbolType] = {
    "class_definition": "class",
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "interface",
}
_PYTHON_ASSIGNMENTS = frozenset({"assignment", "augmented_assignment"})
_JAVADOC_MARKER = re.compile(r"^\s*(?:/\*\*?|\*/|\* ?)")


def _line_range(node: Node) -> tuple[int, int]:
    return node.start_point.row + 1, node.end_point.row + 1


def _bounded(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def _body_start(node: Node) -> int | None:
    body = node.child_by_field_name("body")
    return body.start_byte if body is not None else None


def _signature(
    node: Node,
    declaration: Node,
    source: bytes,
    *,
    variable_name: str | None = None,
) -> str | None:
    if node.has_error or declaration.has_error:
        return None

    start = (
        declaration.start_byte
        if declaration.type == "export_statement"
        else node.start_byte
    )
    if variable_name is not None:
        parent = node.parent
        if parent is None:
            return None
        kind_prefix = ""
        lexical = parent
        if lexical.type in {"lexical_declaration", "variable_declaration"}:
            first = lexical.named_children[0] if lexical.named_children else None
            prefix_end = first.start_byte if first is not None else lexical.end_byte
            kind_prefix = source[lexical.start_byte:prefix_end].decode("utf-8").strip()
            if declaration.type == "export_statement":
                if kind_prefix.startswith("export "):
                    kind_prefix = kind_prefix[len("export ") :]
                kind_prefix = "export " + kind_prefix.strip()
            start = node.start_byte
        else:
            prefix = source[parent.start_byte:node.start_byte].decode("utf-8").strip()
            signature = f"{prefix} {variable_name}".strip()
            return _bounded(signature, MAX_SIGNATURE_CHARS) or None
        value = node.child_by_field_name("value")
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        if value is not None and value.type in _FUNCTION_VALUES:
            body_start = _body_start(value)
            if body_start is None:
                body_start = value.end_byte
            binding = source[node.start_byte:body_start].decode("utf-8")
            binding = re.sub(r"\s*=>\s*$", "", binding).strip()
            if start != node.start_byte:
                binding = source[start:node.start_byte].decode("utf-8") + binding
            signature = f"{kind_prefix} {binding}".strip()
        else:
            signature = f"{kind_prefix} {variable_name}".strip()
    else:
        body_start = _body_start(node)
        if body_start is None:
            if node.type not in {"method_signature", "method_declaration"}:
                return None
            body_start = node.end_byte
        signature = source[start:body_start].decode("utf-8").strip()
        signature = re.sub(r"\s*=>\s*$", "", signature)

    signature = _bounded(signature, MAX_SIGNATURE_CHARS)
    return signature or None


def _clean_comment(raw: str) -> str | None:
    lines = raw.splitlines()
    if lines and lines[0].lstrip().startswith("/**"):
        lines[0] = lines[0].replace("/**", "", 1)
    elif lines and lines[0].lstrip().startswith("/*"):
        lines[0] = lines[0].replace("/*", "", 1)
    if lines and "*/" in lines[-1]:
        lines[-1] = lines[-1].rsplit("*/", 1)[0]
    cleaned = "\n".join(_JAVADOC_MARKER.sub("", line, count=1) for line in lines)
    return _bounded(cleaned, MAX_DOCSTRING_CHARS) or None


def _attached_comment(node: Node, source: bytes) -> str | None:
    previous = node.prev_named_sibling
    while previous is not None and previous.type in {"decorator"}:
        previous = previous.prev_named_sibling
    if previous is None or previous.type not in {"comment", "block_comment"}:
        return None
    raw = source[previous.start_byte:previous.end_byte].decode("utf-8")
    if not raw.lstrip().startswith("/**"):
        return None
    gap = source[previous.end_byte:node.start_byte]
    if gap.count(b"\n") > 2:
        return None
    return _clean_comment(raw)


def _python_docstring(node: Node, source: bytes) -> str | None:
    body = node.child_by_field_name("body")
    if body is None or not body.named_children:
        return None
    first = body.named_children[0]
    expression = first
    if first.type == "expression_statement":
        if not first.named_children:
            return None
        expression = first.named_children[0]
    if expression.type not in {"string", "concatenated_string"}:
        return None
    raw = source[expression.start_byte:expression.end_byte].decode("utf-8")
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return _bounded(raw, MAX_DOCSTRING_CHARS) or None
    return _bounded(value, MAX_DOCSTRING_CHARS) if isinstance(value, str) else None


def _docstring(node: Node, declaration: Node, language: str, source: bytes) -> str | None:
    if language == "python":
        return _python_docstring(node, source)
    return _attached_comment(declaration, source)


def _metadata(
    filename: str,
    language: str | None,
    symbol: str,
    symbol_type: SymbolType,
    signature: str | None,
    docstring: str | None,
    node: Node,
    status: ParseStatus,
) -> SymbolMetadata:
    start_line, end_line = _line_range(node)
    return {
        "filename": filename,
        "language": language,
        "symbol": symbol,
        "symbol_type": symbol_type,
        "signature": signature,
        "docstring": docstring,
        "start_line": start_line,
        "end_line": end_line,
        "parse_status": status,
    }


def _file_metadata(
    source: str, filename: str, language: str | None, status: ParseStatus
) -> SymbolMetadata:
    return {
        "filename": filename,
        "language": language,
        "symbol": filename,
        "symbol_type": "file",
        "signature": None,
        "docstring": None,
        "start_line": 1,
        "end_line": max(1, len(source.splitlines())),
        "parse_status": status,
    }


def extract_symbol_metadata(source: str, filename: str) -> list[SymbolMetadata]:
    """Extract body-free symbol metadata from a source file using Tree-sitter."""
    language = _EXTENSIONS.get(PurePath(filename).suffix.lower())
    if not source:
        return []
    if language is None:
        return [_file_metadata(source, filename, None, "unsupported")]

    encoded = source.encode("utf-8")
    try:
        root = get_parser(language).parse(encoded).root_node
    except Exception as exc:
        logger.warning("Tree-sitter failed to analyze %s as %s: %s", filename, language, exc)
        return [_file_metadata(source, filename, language, "parser_error")]

    status: ParseStatus = "syntax_error" if root.has_error else "parsed"
    extractor = _EXTRACTORS[language]
    variable_types = extractor.variables | ({"variable_declarator"} if language == "java" else set())
    results: list[SymbolMetadata] = []
    seen: set[tuple[str, SymbolType, int, int]] = set()

    def add(
        node: Node,
        declaration: Node,
        symbol: str,
        symbol_type: SymbolType,
        signature: str | None,
    ) -> None:
        if node.has_error or declaration.has_error:
            return
        key = (symbol, symbol_type, declaration.start_byte, declaration.end_byte)
        if key in seen:
            return
        seen.add(key)
        results.append(
            _metadata(
                filename,
                language,
                symbol,
                symbol_type,
                signature,
                _docstring(node, declaration, language, encoded),
                declaration,
                status,
            )
        )

    def visit(node: Node, scopes: tuple[str, ...] = ()) -> None:
        if node.is_missing:
            return

        if node.type in extractor.classes:
            name = _symbol_name(node)
            declaration = _declaration(node)
            if not name and declaration.type == "export_statement":
                if encoded[declaration.start_byte:declaration.end_byte].lstrip().startswith(
                    b"export default"
                ):
                    name = "default"
            if not name:
                return
            symbol = ".".join((*scopes, name))
            if not node.has_error and not declaration.has_error:
                add(
                    node,
                    declaration,
                    symbol,
                    _CLASS_TYPES.get(node.type, "class"),
                    _signature(node, declaration, encoded),
                )
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.named_children:
                    visit(child, (*scopes, name))
            return

        if node.type == "export_statement":
            value = node.child_by_field_name("value")
            if value is not None and value.type in _FUNCTION_VALUES:
                add(
                    value,
                    node,
                    "default",
                    "function",
                    _signature(value, node, encoded),
                )
                return

        if node.type in extractor.functions:
            declaration = _declaration(node)
            name = _symbol_name(node)
            if not name and declaration.type == "export_statement":
                if encoded[declaration.start_byte:declaration.end_byte].lstrip().startswith(
                    b"export default"
                ):
                    name = "default"
            if name:
                symbol = ".".join((*scopes, name))
                symbol_type: SymbolType
                if node.type == "constructor_declaration":
                    symbol_type = "constructor"
                else:
                    symbol_type = "method" if scopes else "function"
                add(
                    node,
                    declaration,
                    symbol,
                    symbol_type,
                    _signature(node, declaration, encoded),
                )
            return

        if node.type in variable_types:
            name = _symbol_name(node)
            if name:
                declaration = node
                parent = node.parent
                if parent is not None and parent.type in {
                    "lexical_declaration",
                    "variable_declaration",
                }:
                    declaration = _declaration(parent)
                value = node.child_by_field_name("value")
                is_callable = value is not None and value.type in _FUNCTION_VALUES
                symbol = ".".join((*scopes, name))
                signature = _signature(
                    node,
                    declaration,
                    encoded,
                    variable_name=name,
                )
                add(
                    node,
                    declaration,
                    symbol,
                    ("function" if is_callable else "variable"),
                    signature,
                )
            return

        if language == "python" and not scopes and node.type in _PYTHON_ASSIGNMENTS:
            left = node.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                name = left.text.decode("utf-8")
                right = node.child_by_field_name("right")
                signature = (
                    encoded[node.start_byte:right.start_byte].decode("utf-8").rstrip().rstrip("=")
                    if right is not None
                    else name
                )
                add(
                    node,
                    node,
                    name,
                    "variable",
                    signature.strip() or name,
                )
                return

        for child in node.named_children:
            visit(child, scopes)

    for child in root.named_children:
        visit(child)

    if results:
        return results
    return [_file_metadata(source, filename, language, status)]
