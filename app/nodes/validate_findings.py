"""Placeholder node for validating future review findings."""

from app.state import ReviewState
from app.schemas import ReviewResult

def validate_findings(state: ReviewState) -> dict[str, object]:
    """Check that returned findings are well-formed and actionable.

    INPUT: State containing changed files and candidate findings.
    OUTPUT: Partial state update with accepted findings and validation details.
    Implement validation and useful error reporting yourself.
    """

    last_message = state['messages'][-1]

    result = ReviewResult.model_validate_json(last_message.content)

    return {
        "final_findings": result
    }
