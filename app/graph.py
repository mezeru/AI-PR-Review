from langchain_core.messages import HumanMessage
from .services.pr_normalizer import format_pr_context
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from app.state import ReviewState
from app.nodes.review_code import review_agent, normalise_final
from app.nodes.validate_findings import validate_findings
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from dotenv import load_dotenv
from app.tools.fetch_file_tool import get_file_context

load_dotenv()

langfuse = get_client()
langfuse_handler = CallbackHandler()


def build_graph():
    """Build the review graph.

    TODO: Wire START -> fetch_pr -> prepare_diff -> review_code ->
    validate_findings -> [retry review_code or generate_report] -> END.
    Implement graph construction and routing as a learning exercise.
    """

    tools = [get_file_context]

    graph = StateGraph(ReviewState)
    graph.add_node("review_code", review_agent)
    graph.add_node("normalise_final",normalise_final )
    graph.add_node("validate_findings", validate_findings)

    graph.add_node('tools',ToolNode(tools))

    graph.add_edge(START,'review_code')

    graph.add_conditional_edges(
        "review_code",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "normalise_final"
        }
    )
    graph.add_edge("tools", "review_code")
    graph.add_edge("normalise_final", "validate_findings")
    graph.add_edge('validate_findings',END)

    return graph.compile()

def run_review(pr_url, normalized_pr):
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
        result = graph.invoke(initial_state, config={
            "callbacks": [langfuse_handler]
        })

        return result

    finally:
        langfuse.flush()


    
