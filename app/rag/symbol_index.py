import logging
import os
import re

from app.rag.models import SymbolMetadata
from app.rag.symbol_extractor import extract_symbol_metadata
from app.services.github_client import fetch_repository_file_paths, get_file
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

def symbol_search_text(symbol: SymbolMetadata) -> str:
    """
    Produce searchable text from metadata:
    filename, symbol, type, signature, docstring.
    """
    return "\n".join([
        symbol["filename"],
        symbol["symbol"],
        symbol["symbol_type"],
        symbol["signature"] or "",
        symbol["docstring"] or ""
    ])





def tokenize_symbol(text: str) -> list[str]:
    """
    Normalize search terms.
    Consider:
    - snake_case
    - camelCase
    - PascalCase
    - file paths
    - lowercase normalization
    """

    text = re.sub(
        r"([A-Z])([A-Z][a-z])",
        r"\1 \2",
        text
    )

    # Split camelCase and PascalCase:
    # getFileContext -> get File Context
    text = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1 \2",
        text
    )

    # Extract alphabetic and numeric tokens
    tokens = re.findall(
        r"[a-z]+|\d+",
        text.lower()
    )

    return tokens



def load_repository_symbols(
    owner: str,
    repo: str,
    sha: str,
) -> list[SymbolMetadata]:
    """
    Fetch repository files at ``sha`` and return their extracted symbol metadata.

    Binary files are skipped because they cannot be analyzed as UTF-8 source.
    """
    token = os.getenv("GITHUB_TOKEN")
    paths = fetch_repository_file_paths(owner, repo, sha, token=token)
    symbols: list[SymbolMetadata] = []

    for path in paths:
        try:
            source = get_file(owner, repo, "", path, token, ref=sha)
        except Exception:
            logger.info("Skipping non-UTF-8 repository file %s", path)
            continue
        symbols.extend(extract_symbol_metadata(source, path))

    return symbols
