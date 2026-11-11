"""Read-only GitHub pull request API helpers."""

import re

import requests


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Parse a public GitHub pull request URL.

    Args:
        pr_url: URL in the form https://github.com/{owner}/{repo}/pull/{number}.

    Returns:
        The repository owner, repository name, and pull request number.

    Raises:
        ValueError: If the URL does not match the supported format.
    """
    pattern = (
        r"https://github\.com/"
        r"(?P<owner>[^/]+)/"
        r"(?P<repo>[^/]+)/pull/"
        r"(?P<pull_number>[1-9]\d*)/?"
    )
    match = re.fullmatch(pattern, pr_url.strip())
    if match is None:
        raise ValueError("Invalid GitHub pull request URL")

    return (
        match.group("owner"),
        match.group("repo"),
        int(match.group("pull_number")),
    )


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_pr_metadata(
    owner: str,
    repo: str,
    pull_number: int,
    token: str | None = None,
    timeout: float = 10.0,
) -> dict[str, object]:
    """Fetch metadata for a pull request.

    Raises:
        ValueError: If an API response is not valid JSON or has an unexpected
            structure.
        RuntimeError: If the GitHub request fails.
    """
    if not owner or not repo or pull_number <= 0:
        raise ValueError("owner, repo, and a positive pull_number are required")

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
    try:
        response = requests.get(url, headers=_headers(token), timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("Failed to fetch pull request metadata") from exc

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ValueError("GitHub returned invalid JSON for pull request metadata") from exc

    if not isinstance(data, dict):
        raise ValueError("Unexpected GitHub pull request metadata response")

    try:
        base = data["base"]["sha"]
        head = data["head"]["sha"]
    except (KeyError, TypeError) as exc:
        raise ValueError("GitHub metadata is missing base/head commit SHAs") from exc

    return {
        "title": data.get("title"),
        "mergeable_state": data.get("mergeable_state"),
        "changed_files": data.get("changed_files"),
        "body": data.get("body"),
        "commits": data.get("commits"),
        "additions": data.get("additions"),
        "deletions": data.get("deletions"),
        "comments": data.get("comments"),
        "review_comments": data.get("review_comments"),
        "base_sha": base,
        "head_sha": head,
    }


def fetch_pr_files(
    owner: str,
    repo: str,
    pull_number: int,
    token: str | None = None,
    timeout: float = 10.0,
) -> list[dict[str, object]]:
    """Fetch all changed-file records, following GitHub's pagination links.

    Raises:
        ValueError: If an API response is invalid or has an unexpected structure.
        RuntimeError: If a GitHub request fails.
    """
    if not owner or not repo or pull_number <= 0:
        raise ValueError("owner, repo, and a positive pull_number are required")

    url: str | None = (
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files"
    )
    params: dict[str, int] | None = {"per_page": 100}
    files: list[dict[str, object]] = []

    while url:
        try:
            response = requests.get(
                url,
                params=params,
                headers=_headers(token),
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError("Failed to fetch pull request files") from exc

        try:
            page = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise ValueError("GitHub returned invalid JSON for pull request files") from exc

        if not isinstance(page, list) or not all(
            isinstance(item, dict) for item in page
        ):
            raise ValueError("Unexpected GitHub pull request files response")

        files.extend(page)
        url = response.links.get("next", {}).get("url")
        params = None

    return files


def consolidate_pr_data(
    pr_url: str,
    token: str | None = None,
) -> dict[str, object]:
    """Fetch pull request metadata and changed files from a GitHub URL."""
    owner, repo, pull_number = parse_pr_url(pr_url)
    metadata = fetch_pr_metadata(owner, repo, pull_number, token=token)
    metadata["files"] = fetch_pr_files(owner, repo, pull_number, token=token)
    return metadata
