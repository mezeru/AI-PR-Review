"""Placeholder node for generating a local review report."""

from app.state import ReviewState


def generate_report(state: ReviewState) -> dict[str, object]:
    """Prepare a local report from the review state.

    INPUT: State containing pull request metadata, findings, and skip details.
    OUTPUT: Partial state update containing the final report.
    Implement report formatting and output yourself; do not publish comments.
    """
    raise NotImplementedError("TODO: implement the generate_report node")
