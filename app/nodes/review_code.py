"""Placeholder node for the future single-model correctness review."""

from app.state import ReviewState


def review_code(state: ReviewState) -> dict[str, object]:
    """Request a structured correctness review from one model.

    INPUT: State containing prepared diff context.
    OUTPUT: Partial state update with the model's structured review result.
    Write the prompt, model invocation, and output handling yourself.
    """
    raise NotImplementedError("TODO: implement the review_code node")
