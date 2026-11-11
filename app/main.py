"""Command-line entry point for the AI Pull Request Investigator."""

import argparse
from collections.abc import Sequence
import sys
from dotenv import load_dotenv
from app.graph import run_review
from app.services.github_client import consolidate_pr_data
from app.services.pr_normalizer import normalize_pr_data


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    """Ask for a pull request URL, fetch it, normalize it, and run a review."""
    parser = argparse.ArgumentParser(
        description="Review a GitHub pull request."
    )
    parser.add_argument(
        "--pr-url",
        help="URL of the public GitHub pull request to review (prompted if omitted)",
    )
    args = parser.parse_args(argv)
    pr_url = args.pr_url or input("Enter GitHub pull request URL: ").strip()
    if not pr_url:
        print("A pull request URL is required.", file=sys.stderr)
        return 2

    try:
        raw = consolidate_pr_data(pr_url)
        normalized = normalize_pr_data(raw)
        result = run_review(pr_url, normalized)
    except (ValueError, RuntimeError) as exc:
        print(f"Review failed: {exc}", file=sys.stderr)
        return 1

    findings = result["final_findings"]
    print(findings.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
