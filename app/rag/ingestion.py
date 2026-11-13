import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.models.pr_model import PullRequestContext
from app.rag.chunker import chunk_code_file
from app.rag.models import CodeChunk
from app.services.github_client import get_file, parse_pr_url


@dataclass(frozen=True)
class RepositoryChunks:
    owner: str
    repo: str
    head_sha: str
    chunks: list[CodeChunk]


def chunk_pr_files(
    pr_url: str,
    pr_context: PullRequestContext,
    paths: Iterable[str],
    token: str | None = None,
) -> RepositoryChunks:
    """Fetch the supplied repository-relative text files at the PR's head commit."""
    owner, repo, _ = parse_pr_url(pr_url)
    head_sha = pr_context["head_sha"]
    if re.fullmatch(r"[0-9a-fA-F]{40}", head_sha or "") is None:
        raise ValueError("PR head_sha must be a full commit SHA")

    chunks: list[CodeChunk] = []
    for path in dict.fromkeys(paths):
        source = get_file(owner, repo, "", path, token, ref=head_sha)
        chunks.extend(chunk_code_file(source, path))
    return RepositoryChunks(owner.lower(), repo.lower(), head_sha.lower(), chunks)
