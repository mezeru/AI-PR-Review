"""Initial state types for the future review workflow."""

from typing import TypedDict, NotRequired
from .models.pr_model import PullRequestContext
from langgraph.graph import MessagesState
from .schemas import ReviewResult


class ReviewState(MessagesState):
    """Incomplete graph state; decide the final fields and reducers yourself."""
    pr_url: str
    pr_context: PullRequestContext
    final_findings: NotRequired[ReviewResult]
