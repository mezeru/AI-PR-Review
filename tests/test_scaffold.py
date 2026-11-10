"""Smoke tests for scaffold importability and callable placeholders only."""

from app.graph import build_graph
from app.nodes.fetch_pr import fetch_pr
from app.nodes.generate_report import generate_report
from app.nodes.prepare_diff import prepare_diff
from app.nodes.review_code import review_code
from app.nodes.validate_findings import validate_findings
from app.schemas import Finding, ReviewResult
from app.services.github_client import (
    fetch_pr_files,
    fetch_pr_metadata,
    parse_pr_url,
)


def test_scaffold_symbols_are_importable_and_callable() -> None:
    """Ensure the intended scaffold entry points exist without implementing them."""
    placeholders = (
        build_graph,
        fetch_pr,
        prepare_diff,
        review_code,
        validate_findings,
        generate_report,
        parse_pr_url,
        fetch_pr_metadata,
        fetch_pr_files,
    )

    assert all(callable(placeholder) for placeholder in placeholders)
    assert Finding is not None
    assert ReviewResult is not None
