"""Command-line entry point for the AI Pull Request Investigator scaffold."""

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and report that review execution is not implemented."""
    parser = argparse.ArgumentParser(
        description="Investigate a GitHub pull request (scaffold only)."
    )
    parser.add_argument(
        "--pr-url",
        required=True,
        help="URL of the public GitHub pull request to review",
    )
    parser.parse_args(argv)
    print("Pull request review is not implemented yet.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
