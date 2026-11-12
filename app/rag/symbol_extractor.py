import ast
import logging
import re
from pathlib import PurePath
from typing import Literal

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
_JS_LANGUAGES = frozenset({"javascript", "typescript", "tsx"})
_JS_FIELDS = frozenset({"field_definition", "public_field_definition"})
_JS_DECLARATIONS = frozenset({"lexical_declaration", "variable_declaration"})
_PROPERTY_NAMES = frozenset({"identifier", "property_identifier", "private_property_identifier"})
_BODYLESS_METHODS = frozenset({"method_signature", "method_declaration"})
_DEFAULT_VALUE_FIELDS = {
    "default_parameter": "value",
    "typed_default_parameter": "value",
    "assignment_pattern": "right",
    "object_assignment_pattern": "right",
    "required_parameter": "value",
    "optional_parameter": "value",
}
_SIMPLE_DEFAULTS = frozenset({"integer", "float", "number", "true", "false", "none", "null"})
_JAVADOC_MARKER = re.compile(r"^\s*(?:/\*\*?|\*/|\* ?)")
_Scope = Literal["class", "function", "object"]


def _line_range(node: Node) -> tuple[int, int]:
    start = node.start_point.row + 1
    end = node.end_point.row + bool(node.end_point.column)
    return start, max(start, end)


def _bounded(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def _header_end(node: Node) -> int | None:
    if node.type in {"function_definition", "class_definition"}:
        # Python can recover erroneous suite text as an ERROR sibling before its block.
        for child in node.children:
            if child.is_missing or child.has_error:
                return None
            if child.type == ":":
                return child.end_byte
        return None

    body = node.child_by_field_name("body")
    if any(child.is_missing or (child != body and child.has_error) for child in node.children):
        return None
    if body is not None:
        closing = body.child(body.child_count - 1) if body.child_count else None
        if closing is not None and closing.type == "}" and closing.is_missing:
            return None
        return body.start_byte
    return node.end_byte if node.type in _BODYLESS_METHODS else None


def _valid_wrapper(node: Node, declaration: Node) -> bool:
    while node != declaration:
        parent = node.parent
        if parent is None or any(
            child != node and (child.is_missing or child.has_error) for child in parent.children
        ):
            return False
        node = parent
    return True


def _redacted_defaults(node: Node) -> list[tuple[int, int]]:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return []

    ranges: list[tuple[int, int]] = []
    pending = [parameters]
    while pending:
        current = pending.pop()
        field = _DEFAULT_VALUE_FIELDS.get(current.type)
        value = current.child_by_field_name(field) if field is not None else None
        if value is not None and value.type not in _SIMPLE_DEFAULTS:
            ranges.append((value.start_byte, value.end_byte))
        pending.extend(child for child in reversed(current.named_children) if child != value)
    return sorted(ranges)


def _signature(
    node: Node,
    source: bytes,
    start: int,
    prefix: str,
) -> str | None:
    end = _header_end(node)
    if end is None:
        return None
    parts = [prefix]
    for value_start, value_end in _redacted_defaults(node):
        parts.extend((source[start:value_start].decode("utf-8"), "..."))
        start = value_end
    parts.append(source[start:end].decode("utf-8"))
    signature = "".join(parts)
    if node.type == "arrow_function":
        signature = re.sub(r"\s*=>\s*$", "", signature)
    return _bounded(signature, MAX_SIGNATURE_CHARS) or None


def _property_name(node: Node | None) -> str | None:
    if node is None or node.is_missing or node.has_error or node.type not in _PROPERTY_NAMES:
        return None
    return node.text.decode("utf-8")


def _member_name(node: Node | None) -> str | None:
    if node is not None and node.type == "string" and not node.has_error:
        if node.named_child_count == 1:
            fragment = node.named_child(0)
            if fragment is not None and fragment.type == "string_fragment":
                return fragment.text.decode("utf-8") or None
        return None
    return _property_name(node)


def _binding_names(node: Node) -> list[str]:
    names: list[str] = []
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type in {"identifier", "shorthand_property_identifier_pattern"}:
            names.append(current.text.decode("utf-8"))
        elif current.type in {"array_pattern", "object_pattern", "rest_pattern"}:
            pending.extend(reversed(current.named_children))
        elif current.type in {"pair_pattern", "assignment_pattern", "object_assignment_pattern"}:
            field = "value" if current.type == "pair_pattern" else "left"
            target = current.child_by_field_name(field)
            if target is not None:
                pending.append(target)
    return names


def _has_braced_body(node: Node) -> bool:
    body = node.child_by_field_name("body")
    if body is None or body.type != "statement_block" or not body.child_count:
        return False
    closing = body.child(body.child_count - 1)
    return closing is not None and closing.type == "}" and not closing.is_missing


def _definition_name(node: Node, declaration: Node) -> str | None:
    name = _symbol_name(node)
    if name is None and declaration.type == "export_statement":
        if any(child.type == "default" for child in declaration.children):
            return "default"
    return name


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
    except (SyntaxError, ValueError, RecursionError):
        return None
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
        "end_line": source.count("\n") + (not source.endswith("\n")),
        "parse_status": status,
    }


def extract_symbol_metadata(source: str, filename: str) -> list[SymbolMetadata]:
    """Extract body-free symbols and one file record for nonempty source."""
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
    is_javascript_family = language in _JS_LANGUAGES
    variable_types = extractor.variables if language != "java" else {"variable_declarator"}
    results: list[SymbolMetadata] = []
    seen: set[tuple[str, SymbolType, int, int]] = set()
    pending: list[tuple[Node, tuple[str, ...], _Scope | None]] = [(root, (), None)]

    def add(
        node: Node,
        declaration: Node,
        scopes: tuple[str, ...],
        symbol_type: SymbolType,
        signature: str | None,
    ) -> None:
        symbol = ".".join(scopes)
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

    def add_definition(
        node: Node,
        declaration: Node,
        scopes: tuple[str, ...],
        symbol_type: SymbolType,
        *,
        start: int | None = None,
        prefix: str = "",
        allow_missing_signature: bool = False,
    ) -> bool:
        if not _valid_wrapper(node, declaration):
            return False
        if start is None:
            start = (
                declaration.start_byte if declaration.type == "export_statement" else node.start_byte
            )
        signature = _signature(node, encoded, start, prefix)
        if signature is None and not (allow_missing_signature and _has_braced_body(node)):
            return False
        add(node, declaration, scopes, symbol_type, signature)
        return True

    def visit_body(node: Node, scopes: tuple[str, ...], scope: _Scope) -> None:
        body = node.child_by_field_name("body")
        if body is not None:
            pending.append((body, scopes, scope))

    def visit_binding(node: Node, scopes: tuple[str, ...], scope: _Scope | None) -> None:
        name_node = node.child_by_field_name("name")
        parent = node.parent
        if name_node is None or name_node.is_missing or name_node.has_error or parent is None:
            return

        name = _property_name(name_node)
        if language == "java":
            if (
                name is None
                or node.has_error
                or parent.type not in {"field_declaration", "constant_declaration"}
            ):
                return
            first = parent.child_by_field_name("declarator")
            if first is not None:
                prefix = encoded[parent.start_byte:first.start_byte].decode("utf-8").strip()
                signature = _bounded(f"{prefix} {name}", MAX_SIGNATURE_CHARS)
                add(node, node, (*scopes, name), "variable", signature)
            return

        if parent.type not in _JS_DECLARATIONS:
            return
        binding = _declaration(parent)
        declaration = binding if parent.named_child_count == 1 else node
        kind = parent.child(0)
        if kind is None or kind.type not in {"const", "let", "var"}:
            return
        prefix = ("export " if binding.type == "export_statement" else "") + kind.type + " "
        value = node.child_by_field_name("value")
        if name is not None and value is not None and value.type in _FUNCTION_VALUES:
            symbol_path = (*scopes, name)
            if add_definition(
                value, declaration, symbol_path, "function", start=node.start_byte, prefix=prefix
            ):
                visit_body(value, symbol_path, "function")
        elif scope != "function":
            if (
                name is not None
                and value is not None
                and value.type == "object"
                and _valid_wrapper(value, declaration)
            ):
                pending.append((value, (*scopes, name), "object"))
            elif node.has_error or declaration.has_error:
                return
            for binding_name in _binding_names(name_node):
                signature = _bounded(prefix + binding_name, MAX_SIGNATURE_CHARS)
                add(node, declaration, (*scopes, binding_name), "variable", signature)

    def visit_member(node: Node, key: Node | None, scopes: tuple[str, ...]) -> None:
        name = _member_name(key)
        value = node.child_by_field_name("value")
        if name is None or value is None:
            return
        symbol_path = (*scopes, name)
        if value.type in _FUNCTION_VALUES:
            if add_definition(
                value, node, symbol_path, "method", start=node.start_byte,
                allow_missing_signature=node.type == "pair",
            ):
                visit_body(value, symbol_path, "function")
        elif node.type == "pair" and value.type == "object":
            pending.append((value, symbol_path, "object"))

    def visit(node: Node, scopes: tuple[str, ...], scope: _Scope | None) -> None:
        if node.is_missing:
            return

        if node.type in extractor.classes:
            declaration = _declaration(node)
            name = _definition_name(node, declaration)
            if name:
                symbol_path = (*scopes, name)
                add_definition(node, declaration, symbol_path, _CLASS_TYPES.get(node.type, "class"))
                visit_body(node, symbol_path, "class")
            return

        if node.type == "export_statement":
            value = node.child_by_field_name("value")
            if value is not None and value.type in _FUNCTION_VALUES:
                if add_definition(value, node, ("default",), "function"):
                    visit_body(value, ("default",), "function")
                return

        if node.type in extractor.functions:
            declaration = _declaration(node)
            name = (
                _member_name(node.child_by_field_name("name"))
                if scope == "object" else _definition_name(node, declaration)
            )
            if name:
                symbol_path = (*scopes, name)
                symbol_type: SymbolType
                if node.type == "constructor_declaration":
                    symbol_type = "constructor"
                else:
                    symbol_type = "method" if scope in {"class", "object"} else "function"
                if add_definition(
                    node, declaration, symbol_path, symbol_type, allow_missing_signature=scope == "object"
                ):
                    visit_body(node, symbol_path, "function")
            return

        if node.type in variable_types:
            visit_binding(node, scopes, scope)
            return

        if is_javascript_family:
            if scope == "class" and node.type in _JS_FIELDS:
                key = node.child_by_field_name("name") or node.child_by_field_name("property")
                visit_member(node, key, scopes)
                return
            if node.type == "object":
                if scope == "object":
                    pending.extend(
                        (child, scopes, scope)
                        for child in reversed(node.named_children)
                        if child.type in {"method_definition", "pair"}
                    )
                return
            if scope == "object" and node.type == "pair":
                visit_member(node, node.child_by_field_name("key"), scopes)
                return
            if node.type in _FUNCTION_VALUES:
                return

        if language == "python" and scope != "function" and node.type in _PYTHON_ASSIGNMENTS:
            left = node.child_by_field_name("left")
            name = _property_name(left)
            if left is not None and name and not node.has_error:
                annotation = node.child_by_field_name("type")
                signature = (
                    encoded[left.start_byte:annotation.end_byte].decode("utf-8")
                    if annotation is not None
                    else name
                )
                add(node, node, (*scopes, name), "variable", _bounded(signature, MAX_SIGNATURE_CHARS))
            return

        pending.extend((child, scopes, scope) for child in reversed(node.named_children))

    while pending:
        visit(*pending.pop())

    results.append(_file_metadata(source, filename, language, status))
    return results
