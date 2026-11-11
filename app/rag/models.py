from typing import Literal, TypedDict


ParseStatus = Literal["parsed", "syntax_error", "parser_error", "unsupported"]

class CodeChunk(TypedDict):
    filename: str
    symbol: str
    start_line: int
    end_line: int
    content: str
    language: str | None
    parse_status: ParseStatus
