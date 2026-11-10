"""Placeholder node for retrieving pull request data."""

from app.state import ReviewState


def fetch_pr(state: ReviewState) -> dict[str, object]:
    """Fetch pull request metadata and changed files.

    INPUT: State containing the pull request URL.
    OUTPUT: Partial state update with metadata and changed-file records.
    Implement API orchestration, errors, and state updates yourself.
    """
    raise NotImplementedError("TODO: implement the fetch_pr node")
