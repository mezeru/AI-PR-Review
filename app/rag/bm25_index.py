
from rank_bm25 import BM25Okapi
from app.rag.models import SymbolMetadata
from app.rag.symbol_index import (
    symbol_search_text,
    tokenize_symbol
)


class SymbolBM25Index:

    def __init__(
        self,
        symbols: list[SymbolMetadata],
        top_k: int = 5
    ):
        self.symbols = list(symbols)
        self.top_k = top_k

        self.tokenized_corpus = [
            tokenize_symbol(symbol_search_text(symbol))
            for symbol in self.symbols
        ]

        # Build index only when searchable tokens exist
        self.bm25 = (
            BM25Okapi(self.tokenized_corpus)
            if any(self.tokenized_corpus)
            else None
        )

    def search(
        self,
        query: str,
        symbol_type: str | None = None
    ) -> list[SymbolMetadata]:

        if self.bm25 is None or self.top_k <= 0:
            return []

        query_tokens = tokenize_symbol(query)

        if not query_tokens:
            return []

        # Step 1: Identify candidates with keyword overlap
        query_terms = set(query_tokens)

        matching_indices = [
            i
            for i, tokens in enumerate(self.tokenized_corpus)
            if query_terms.intersection(tokens)
        ]

        if not matching_indices:
            return []

        # Step 2: Score all symbols
        scores = self.bm25.get_scores(query_tokens)

        # Step 3: Rank only matching candidates
        ranked_indices = sorted(
            matching_indices,
            key=lambda i: scores[i],
            reverse=False
        )

        # Step 4: Apply optional type filter
        results = []

        for i in ranked_indices:
            symbol = self.symbols[i]

            if (
                symbol_type is not None
                and symbol["symbol_type"] != symbol_type
            ):
                continue

            results.append(symbol)

            if len(results) >= self.top_k:
                break

        return results
  