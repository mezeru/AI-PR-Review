import json

from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from app.context import ReviewContext


@tool
def search_codebase(
    query: str,
    runtime: ToolRuntime[ReviewContext]
) -> str:
    """
    Search functions, classes, and symbols in the
    current PR repository.

    Returns matching symbols with their source locations.
    Use get_file_context to inspect implementations.
    """

    index = runtime.context.symbol_index

    results = index.search(query)

    # Return only the metadata useful for source discovery.
    response = [
        {
            "symbol": symbol["symbol"],
            "symbol_type": symbol["symbol_type"],
            "filename": symbol["filename"],
            "start_line": symbol["start_line"],
            "end_line": symbol["end_line"],
            "signature": symbol.get("signature")
        }
        for symbol in results
    ]

    return json.dumps(response, ensure_ascii=False)