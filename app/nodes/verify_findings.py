"""Placeholder node for generating a local review report."""

from app.state import ReviewState
from app.services.github_client import verify_finding_location


def verify_findings(state: ReviewState) -> dict:
    results = []

    for finding in state["final_findings"].findings:
        verification = verify_finding_location(
            finding,
            state["pr_context"]
        )
        results.append(verification)

    return {"location_verifications": results}