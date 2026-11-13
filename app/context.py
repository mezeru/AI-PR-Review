from dataclasses import dataclass

from app.rag.bm25_index import SymbolBM25Index


@dataclass(frozen=True)
class ReviewContext:
    symbol_index: SymbolBM25Index