"""Placeholder node for preparing changed-file diffs."""

from app.state import ReviewState
from langchain_core.messages import ToolMessage


def tool_budget_exhausted(state: ReviewState) -> dict:
    last_message = state["messages"][-1]

    skipped_messages = [
        ToolMessage(
            content=(
                "Tool execution skipped: the investigation "
                "budget has been exhausted. Continue using "
                "the information already available."
            ),
            tool_call_id=call["id"],
            name=call["name"]
        )
        for call in last_message.tool_calls
    ]

    return {"messages": skipped_messages}