"""Placeholder node for validating future review findings."""

from app.state import ReviewState


def validate_findings(state: ReviewState) -> dict[str, object]:
    """Check that returned findings are well-formed and actionable.

    INPUT: State containing changed files and candidate findings.
    OUTPUT: Partial state update with accepted findings and validation details.
    Implement validation and useful error reporting yourself.
    """
    raise NotImplementedError("TODO: implement the validate_findings node")
