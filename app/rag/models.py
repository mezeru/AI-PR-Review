from typing import TypedDict

class CodeChunk(TypedDict):
    filename: str
    symbol: str
    start_line: int
    end_line: int
    content: str