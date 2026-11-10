"""Placeholder node for the future single-model correctness review."""

from app.state import ReviewState
from app.agent import review_pull_request
from langchain_core.messages import AIMessage

def review_agent(state: ReviewState) -> dict:
    """
    Analyze the PR and optionally request additional context.

    Reads:
        - pr_context
        - messages

    Updates:
        - messages
    """

    pr_context = state["pr_context"]
    response = review_pull_request(pr_context)

    return {
        "messages": [AIMessage(content=response)]
    }
