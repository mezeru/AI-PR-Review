"""Placeholder node for preparing changed-file diffs."""

from app.state import ReviewState


def prepare_diff(state: ReviewState) -> dict[str, object]:
    """Prepare bounded diff context for review.

    INPUT: State containing pull request data and changed files.
    OUTPUT: Partial state update with prepared diff context and skip details.
    Implement diff handling and size limits yourself.
    """
    raise NotImplementedError("TODO: implement the prepare_diff node")
