import logging
import re
from bisect import bisect_right
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from io import StringIO
from pathlib import PurePath

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.rag.models import CodeChunk, ParseStatus

MAX_CHUNK_LINES = 100
CHUNK_OVERLAP_LINES = 10
MAX_CHUNK_CHARS = 8_000

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Extractor:
    classes: frozenset[str]
    functions: frozenset[str]
    variables: frozenset[str] = frozenset()


_EXTRACTORS = {
    "python": _Extractor(
        classes=frozenset({"class_definition"}),
        functions=frozenset({"function_definition"}),
    ),
    "javascript": _Extractor(
        classes=frozenset({"class_declaration", "class"}),
        functions=frozenset(
            {
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
            }
        ),
        variables=frozenset({"variable_declarator"}),
    ),
    "typescript": _Extractor(
        classes=frozenset(
            {
                "class_declaration",
                "abstract_class_declaration",
                "interface_declaration",
                "enum_declaration",
            }
        ),
        functions=frozenset(
            {
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "method_signature",
            }
        ),
        variables=frozenset({"variable_declarator"}),
    ),
    "tsx": _Extractor(
        classes=frozenset(
            {
                "class_declaration",
                "abstract_class_declaration",
                "interface_declaration",
                "enum_declaration",
            }
        ),
        functions=frozenset(
            {
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "method_signature",
            }
        ),
        variables=frozenset({"variable_declarator"}),
    ),
    "java": _Extractor(
        classes=frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
                "annotation_type_declaration",
            }
        ),
        functions=frozenset({"method_declaration", "constructor_declaration"}),
    ),
}

_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
}

_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression"})
_VARIABLE_DECLARATIONS = frozenset({"lexical_declaration", "variable_declaration"})
_LINE_WHITESPACE = re.compile(rb"[ \t\r\f\v]*")


@dataclass(frozen=True)
class _Region:
    start: int
    end: int
    symbol: str | None = None


def _symbol_name(node: Node) -> str | None:
    name = node.child_by_field_name("name")
    if name is None or name.has_error:
        return None
    return name.text.decode("utf-8")


def _declaration(node: Node) -> Node:
    parent = node.parent
    if parent is not None and (
        parent.type == "decorated_definition"
        or (
            parent.type == "export_statement"
            and parent.child_by_field_name("declaration") == node
        )
    ):
        return parent
    return node


def _tree_regions(
    root: Node, source: bytes, extractor: _Extractor, line_starts: list[int]
) -> Iterator[_Region]:
    def region(node: Node, symbol: str | None, *, include_class_docs: bool = False) -> _Region:
        start, end = node.start_byte, node.end_byte
        previous = node.prev_named_sibling
        while previous is not None and not previous.has_error:
            is_doc = (
                include_class_docs
                and previous.type in {"block_comment", "comment"}
                and source.startswith(b"/**", previous.start_byte)
            )
            if previous.type != "decorator" and not is_doc:
                break
            gap = source[previous.end_byte : start]
            if gap.strip() or gap.count(b"\n") > 1:
                break
            start = previous.start_byte
            previous = previous.prev_named_sibling

        # Keep indentation and whitespace up to the next token or end of line.
        line_start = line_starts[bisect_right(line_starts, start) - 1]
        if _LINE_WHITESPACE.fullmatch(source, line_start, start):
            start = line_start
        if source[end - 1 : end] != b"\n":
            whitespace = _LINE_WHITESPACE.match(source, end)
            if whitespace is not None:
                end = whitespace.end()
            if source[end : end + 1] == b"\n":
                end += 1
        return _Region(start, end, symbol)

    def visit(node: Node, scope: str = "") -> Iterator[_Region]:
        if node.is_missing:
            return

        if node.type == "export_statement" and not node.has_error:
            value = node.child_by_field_name("value")
            if value is not None and value.type in _FUNCTION_VALUES:
                yield region(node, "default")
                return

        if node.type in extractor.classes:
            name = _symbol_name(node)
            if name:
                symbol = f"{scope}.{name}" if scope else name
                declaration = _declaration(node)
                context = region(
                    declaration,
                    None if declaration.has_error else symbol,
                    include_class_docs=True,
                )
                cursor = context.start
                for child in node.named_children:
                    for member in visit(child, symbol):
                        if cursor < member.start:
                            yield _Region(cursor, member.start, context.symbol)
                        yield member
                        cursor = member.end
                if cursor < context.end:
                    yield _Region(cursor, context.end, context.symbol)
                return

        if node.type in extractor.functions:
            declaration = _declaration(node)
            name = _symbol_name(node)
            if name and not declaration.has_error:
                yield region(declaration, f"{scope}.{name}" if scope else name)
            return

        if node.type in extractor.variables:
            value = node.child_by_field_name("value")
            name = _symbol_name(node)
            if name and value is not None and value.type in _FUNCTION_VALUES:
                declaration = node
                parent = node.parent
                # Use the surrounding declaration only when this is its sole named child.
                if (
                    parent is not None
                    and parent.type in _VARIABLE_DECLARATIONS
                    and parent.named_child_count == 1
                ):
                    declaration = _declaration(parent)
                if not declaration.has_error:
                    yield region(declaration, f"{scope}.{name}" if scope else name)
                return

        for child in node.named_children:
            yield from visit(child, scope)

    cursor = 0
    for symbol_region in visit(root):
        if cursor < symbol_region.start:
            yield _Region(cursor, symbol_region.start)
        yield symbol_region
        cursor = symbol_region.end
    if cursor < len(source):
        yield _Region(cursor, len(source))


def _bounded_chunks(
    content: str,
    first_line: int,
    max_lines: int,
    max_chars: int,
    overlap_lines: int,
) -> Iterator[tuple[int, int, str]]:
    # Tree-sitter counts LF bytes as line breaks. Keep CRLF and all other text intact.
    lines = list(StringIO(content))
    start = 0
    while start < len(lines):
        if len(lines[start]) > max_chars:
            line = lines[start]
            if line.strip():
                line_number = first_line + start
                for offset in range(0, len(line), max_chars):
                    yield line_number, line_number, line[offset : offset + max_chars]
            start += 1
            continue

        end = start
        size = 0
        while end < len(lines) and end - start < max_lines:
            line_size = len(lines[end])
            if size + line_size > max_chars:
                break
            size += line_size
            end += 1

        window = "".join(lines[start:end])
        if window.strip():
            yield first_line + start, first_line + end - 1, window
        if end == len(lines):
            break

        # Leave room for at least one new line within both limits.
        next_start = end
        size = len(lines[end])
        while next_start > max(start + 1, end - overlap_lines):
            size += len(lines[next_start - 1])
            if size > max_chars:
                break
            next_start -= 1
        start = next_start


def _chunk_file(
    source: str,
    filename: str,
    language: str | None,
    max_lines: int,
    max_chars: int,
    overlap_lines: int,
) -> list[CodeChunk]:
    if max_lines < 1 or max_chars < 1 or overlap_lines < 0:
        raise ValueError("Chunk limits must be positive and overlap must be nonnegative")

    encoded = source.encode("utf-8")
    line_starts = [0, *(match.end() for match in re.finditer(b"\n", encoded))]
    regions: Iterable[_Region] = (_Region(0, len(encoded)),)
    status: ParseStatus = "unsupported"
    if language is not None:
        try:
            root = get_parser(language).parse(encoded).root_node
            status = "syntax_error" if root.has_error else "parsed"
            # Finish extraction before emitting chunks so an interrupted walk can fall back cleanly.
            regions = list(_tree_regions(root, encoded, _EXTRACTORS[language], line_starts))
        except Exception as exc:
            logger.warning("Tree-sitter failed to analyze %s as %s: %s", filename, language, exc)
            status = "parser_error"

    basename = PurePath(filename).name
    chunks: list[CodeChunk] = []
    for region in regions:
        first_line = bisect_right(line_starts, region.start)
        content = encoded[region.start : region.end].decode("utf-8")
        for start, end, window in _bounded_chunks(
            content, first_line, max_lines, max_chars, overlap_lines if region.symbol else 0
        ):
            chunks.append(
                {
                    "filename": filename,
                    "language": language,
                    "symbol": region.symbol or f"{basename}:lines {start}-{end}",
                    "start_line": start,
                    "end_line": end,
                    "content": window,
                    "parse_status": status,
                }
            )
    return chunks


def chunk_code_file(
    source: str,
    filename: str,
    *,
    max_lines: int = MAX_CHUNK_LINES,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_lines: int = CHUNK_OVERLAP_LINES,
) -> list[CodeChunk]:
    """Chunk symbols and uncovered text. Parse status describes the entire file."""
    language = _EXTENSIONS.get(PurePath(filename).suffix.lower())
    return _chunk_file(source, filename, language, max_lines, max_chars, overlap_lines)


def chunk_python_file(
    source: str,
    filename: str,
    *,
    max_lines: int = MAX_CHUNK_LINES,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_lines: int = CHUNK_OVERLAP_LINES,
) -> list[CodeChunk]:
    """Chunk source as Python regardless of filename extension."""
    return _chunk_file(source, filename, "python", max_lines, max_chars, overlap_lines)
