from langchain_core.messages import HumanMessage
from .services.pr_normalizer import format_pr_context
from langgraph.graph import StateGraph, START, END


from app.state import ReviewState
from app.nodes.review_code import review_agent
from app.nodes.validate_findings import validate_findings

"""Placeholder for the future LangGraph review workflow."""


def build_graph():
    """Build the review graph.

    TODO: Wire START -> fetch_pr -> prepare_diff -> review_code ->
    validate_findings -> [retry review_code or generate_report] -> END.
    Implement graph construction and routing as a learning exercise.
    """

    # def review_or_finalize(state: ReviewState) -> dict[str, object]:
    #     # TODO
    #     return

    graph = StateGraph(ReviewState)

    graph.add_node("review_code", review_agent)
    graph.add_node("validate_findings", validate_findings)

    graph.add_edge(START,'review_code')
    # graph.add_conditional_edges('review_code',
    #     review_or_finalize,
    #     {
    #         "review": "review_code"
    #         "finalize": 'validate_findings'
    #     }
    # )

    graph.add_edge('review_code','validate_findings')
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

    return graph.invoke(initial_state)