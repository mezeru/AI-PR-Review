"""Initial state types for the future review workflow."""

from typing import TypedDict


class ReviewState(TypedDict):
    """Incomplete graph state; decide the final fields and reducers yourself."""

    pr_url: str
    # TODO: pr_data
    # TODO: files
    # TODO: findings
    # TODO: validation_errors
    # TODO: review_attempts
    # TODO: final_report
