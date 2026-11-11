"""Placeholder node for the future single-model correctness review."""

from app.state import ReviewState
from app.agent import review_pull_request
from langchain_core.messages import AIMessage
import json

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
)

def review_agent(state: ReviewState) -> dict:
    """
    Analyze the PR and optionally request additional context.

    Reads:
        - pr_context
        - messages

    Updates:
        - messages
    """

    

    hf_converted_messages = to_hf_messages(state['messages'])   
    response = review_pull_request(hf_converted_messages)

    return {"messages": [response]}

def normalise_final(state: ReviewState) -> dict:
    """
    Analyze the PR and optionally request additional context.

    Reads:
        - pr_context
        - messages

    Updates:
        - messages
    """

    

    hf_converted_messages = to_hf_messages(state['messages'])   
    response = review_pull_request(hf_converted_messages, True)

    return {"messages": [response]}




def to_hf_messages(messages):
    converted = []

    for message in messages:

        if isinstance(message, SystemMessage):
            converted.append({
                "role": "system",
                "content": message.content
            })

        elif isinstance(message, HumanMessage):
            converted.append({
                "role": "user",
                "content": message.content
            })

        elif isinstance(message, AIMessage):
            hf_message = {
                "role": "assistant",
                "content": message.content or None
            }

            if message.tool_calls:
                hf_message["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["args"])
                        }
                    }
                    for call in message.tool_calls
                ]

            converted.append(hf_message)

        elif isinstance(message, ToolMessage):
            converted.append({
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "name": message.name,
                "content": message.content
            })

        else:
            raise TypeError(
                f"Unsupported message type: {type(message)}"
            )

    return converted