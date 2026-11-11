from dataclasses import dataclass
from pathlib import PurePath

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.rag.models import CodeChunk

FALLBACK_LINES = 100


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


def _named_child(node: Node, field: str) -> Node | None:
    return node.child_by_field_name(field)


def _symbol_name(node: Node) -> str | None:
    name = _named_child(node, "name")
    if name is None:
        return None
    return name.text.decode("utf-8", errors="replace")


def _chunks_from_tree(source: str, filename: str, language: str) -> list[CodeChunk]:
    extractor = _EXTRACTORS[language]
    tree = get_parser(language).parse(source.encode("utf-8"))
    lines = source.splitlines(keepends=True)
    chunks: list[CodeChunk] = []

    def add(node: Node, symbol: str) -> None:
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + (1 if node.end_point.column else 0)
        end_line = max(start_line, end_line)
        chunks.append(
            {
                "filename": filename,
                "symbol": symbol,
                "start_line": start_line,
                "end_line": end_line,
                "content": "".join(lines[start_line - 1 : end_line]),
            }
        )

    def include_decorators(node: Node) -> Node:
        if node.parent is not None and node.parent.type == "decorated_definition":
            return node.parent
        return node

    def visit(node: Node, class_name: str | None = None) -> None:
        if node.type == "export_statement":
            value = _named_child(node, "value")
            if value is not None and value.type in {
                "arrow_function",
                "function_expression",
            }:
                add(node, "default")
                return

        if node.type in extractor.classes:
            name = _symbol_name(node)
            if name:
                add(include_decorators(node), name)
                for child in node.named_children:
                    visit(child, name)
                return

        if node.type in extractor.functions:
            name = _symbol_name(node)
            if name:
                add(
                    include_decorators(node),
                    f"{class_name}.{name}" if class_name else name,
                )
                return

        if node.type in extractor.variables:
            value = _named_child(node, "value")
            name = _symbol_name(node)
            if (
                value is not None
                and value.type in {"arrow_function", "function_expression"}
                and name
            ):
                declaration = node
                parent = node.parent
                if parent is not None and parent.type in {
                    "lexical_declaration",
                    "variable_declaration",
                }:
                    declaration = parent
                    if (
                        parent.parent is not None
                        and parent.parent.type == "export_statement"
                    ):
                        declaration = parent.parent
                add(declaration, f"{class_name}.{name}" if class_name else name)
                return

        for child in node.named_children:
            visit(child, class_name)

    for child in tree.root_node.named_children:
        visit(child)

    return chunks


def _text_chunks(source: str, filename: str) -> list[CodeChunk]:
    lines = source.splitlines(keepends=True)
    return [
        {
            "filename": filename,
            "symbol": (
                f"{PurePath(filename).name}:lines "
                f"{start}-{min(start + FALLBACK_LINES - 1, len(lines))}"
            ),
            "start_line": start,
            "end_line": min(start + FALLBACK_LINES - 1, len(lines)),
            "content": "".join(lines[start - 1 : start - 1 + FALLBACK_LINES]),
        }
        for start in range(1, len(lines) + 1, FALLBACK_LINES)
    ]


def chunk_code_file(source: str, filename: str) -> list[CodeChunk]:
    """Extract code structures or fall back to bounded, line-numbered text chunks."""
    language = _EXTENSIONS.get(PurePath(filename).suffix.lower())
    if language is not None:
        chunks = _chunks_from_tree(source, filename, language)
        if chunks:
            return chunks
    return _text_chunks(source, filename)


def chunk_python_file(source: str, filename: str) -> list[CodeChunk]:
    """Extract Python functions, classes, and class methods."""
    chunks = _chunks_from_tree(source, filename, "python")
    return chunks if chunks else _text_chunks(source, filename)
