from app.rag.symbol_index import load_repository_symbols
from app.rag.bm25_index import SymbolBM25Index
from app.services.github_client import parse_pr_url
from app.models.pr_model import PullRequestContext


def build_pr_symbol_index(
    pr_url: str,
    pr_context: PullRequestContext
) -> SymbolBM25Index:

    owner, repo, pr = parse_pr_url(pr_url)

    head_sha = pr_context.get('head_sha')

    symbols_for_commit = load_repository_symbols(owner, repo, head_sha)

    index = SymbolBM25Index(symbols_for_commit)

    return index