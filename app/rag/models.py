from typing import Literal, TypedDict


ParseStatus = Literal["parsed", "syntax_error", "parser_error", "unsupported"]
SymbolType = Literal[
    "function",
    "method",
    "class",
    "interface",
    "constructor",
    "enum",
    "record",
    "variable",
    "file",
]

class CodeChunk(TypedDict):
    filename: str
    symbol: str
    start_line: int
    end_line: int
    content: str
    language: str | None
    parse_status: ParseStatus


class SymbolMetadata(TypedDict):
    filename: str
    language: str | None
    symbol: str
    symbol_type: SymbolType
    signature: str | None
    docstring: str | None
    start_line: int
    end_line: int
    parse_status: ParseStatus
