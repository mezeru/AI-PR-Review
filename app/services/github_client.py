"""Function signatures for the future read-only GitHub pull request client."""


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Parse a GitHub pull request URL into owner, repository, and number.

    Args:
        pr_url: A GitHub pull request URL.

    Returns:
        A tuple of owner, repository name, and pull request number.

    Raises:
        ValueError: To be raised by the implementation for unsupported URLs.
    """
    raise NotImplementedError("TODO: implement safe pull request URL parsing")


def fetch_pr_metadata(
    owner: str,
    repo: str,
    pull_number: int,
    token: str | None = None,
    timeout: float = 10.0,
) -> dict[str, object]:
    """Fetch pull request metadata from the GitHub REST API.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional token for authenticated read access.
        timeout: Per-request timeout in seconds.

    Returns:
        The decoded pull request metadata object.

    Raises:
        NotImplementedError: Until API requests and error handling are added.

    Implement response validation, HTTP/API errors, timeouts, and safe handling
    of credentials yourself.
    """
    raise NotImplementedError("TODO: fetch pull request metadata")


def fetch_pr_files(
    owner: str,
    repo: str,
    pull_number: int,
    token: str | None = None,
    timeout: float = 10.0,
) -> list[dict[str, object]]:
    """Fetch changed-file records from the GitHub REST API.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional token for authenticated read access.
        timeout: Per-request timeout in seconds.

    Returns:
        A list of decoded changed-file objects, including patches when available.

    Raises:
        NotImplementedError: Until paginated API requests and error handling are
            added.

    Implement pagination, response validation, API errors, and timeouts yourself.
    """
    raise NotImplementedError("TODO: fetch changed pull request files")
