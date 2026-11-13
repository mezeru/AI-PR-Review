from langchain_core.messages import HumanMessage
from .services.pr_normalizer import format_pr_context
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.errors import GraphRecursionError
from app.state import ReviewState
from app.nodes.review_code import review_agent, normalise_final
from app.nodes.validate_findings import validate_findings
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from dotenv import load_dotenv
from app.tools.fetch_file_tool import get_file_context
from app.nodes.verify_findings import verify_findings
from langchain_core.messages import ToolMessage
from typing import Literal
from app.nodes.tool_budget_exhaust import tool_budget_exhausted
from app.tools.rag_check import search_codebase
from app.context import ReviewContext

load_dotenv()

langfuse = get_client()
langfuse_handler = CallbackHandler()

MAX_TOOL_CALLS = 10

def count_tool_calls(state: ReviewState) -> int:
    return sum(
        isinstance(message, ToolMessage)
        for message in state["messages"]
    )

def review_tool_budget(state: ReviewState) -> Literal["tools", "normalise_final", "budget_exhausted"]:

    last_message = state["messages"][-1]

    if len(last_message.tool_calls) == 0:
        return "normalise_final"

    requested_tool_calls = count_tool_calls(state)

    if(requested_tool_calls + len(last_message.tool_calls) > MAX_TOOL_CALLS):
        return "budget_exhausted"

    return "tools"

def review_post_tool_call(state: ReviewState)-> Literal["review_code","normalise_final"]:

    tool_calls = count_tool_calls(state)

    if tool_calls >= MAX_TOOL_CALLS:
        return "normalise_final"

    return "review_code"


def build_graph():
    """Build the review graph.

    TODO: Wire START -> fetch_pr -> prepare_diff -> review_code ->
    validate_findings -> [retry review_code or generate_report] -> END.
    Implement graph construction and routing as a learning exercise.
    """

    tools = [get_file_context, search_codebase]

    graph = StateGraph(ReviewState,
                       context_schema=ReviewContext)
    graph.add_node("review_code", review_agent)
    graph.add_node("normalise_final",normalise_final )
    graph.add_node("validate_findings", validate_findings)
    graph.add_node('tools',ToolNode(tools))
    graph.add_node('verify_findings',verify_findings)
    graph.add_node('tool_budget_exhausted',tool_budget_exhausted)

    graph.add_edge(START,'review_code')
    graph.add_conditional_edges(
        "review_code",
        review_tool_budget,
        {
            "tools": "tools",
            "normalise_final": "normalise_final",
            "budget_exhausted":"tool_budget_exhausted"
        }
    )

    graph.add_edge('tool_budget_exhausted','normalise_final')
    graph.add_conditional_edges("tools",review_post_tool_call,{
        "review_code":"review_code",
        "normalise_final": "normalise_final"
    })
    graph.add_edge("normalise_final", "validate_findings")
    graph.add_edge('validate_findings','verify_findings')
    graph.add_edge('verify_findings',END)

    return graph.compile()

def run_review(pr_url, normalized_pr, index):
    initial_state = {
        "pr_url": pr_url,
        "pr_context": normalized_pr,
        "messages": [
            HumanMessage(
                content=format_pr_context(normalized_pr)
            )
        ]
    }

    graph = build_graph()

    try:
        result = graph.invoke(initial_state, context=ReviewContext(symbol_index=index) ,config={
            "callbacks": [langfuse_handler],
            "recursion_limit": 35
        })

        return result
    
    except GraphRecursionError:
        print("PR review exceeded maximum execution steps.")
        raise

    finally:
        langfuse.flush()


    
