"""Read-only GitHub pull request API helpers."""

import re
import base64
import requests
from urllib.parse import quote
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

MAX_LINES = 150
MAX_FILE_BYTES = 500_000

def fetch_file_lines(
    owner: str,
    repo: str,
    path: str,
    ref: str,
    start_line: int,
    end_line: int,
    token: str | None = None,
    timeout: float = 10.0,
) -> str:

    if(start_line < 1 or end_line < start_line or end_line - start_line + 1 > MAX_LINES):
        raise ValueError("Invalid or oversized line range, Max lines that should be fetched are 150")

    if (
    not path
    or "\\" in path
    or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        raise ValueError("Invalid file path")

    url = (
        f"https://api.github.com/repos/"
        f"{quote(owner, safe='')}/{quote(repo, safe='')}"
        f"/contents/{quote(path, safe='/')}"
    )

    headers = {"Accept": "application/vnd.github+json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(
        url,
        headers=headers,
        params={"ref": ref},
        timeout=timeout
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict) or data.get("type") != "file":
        raise ValueError("Expected a file")

    if data.get("size", 0) > MAX_FILE_BYTES:
        raise ValueError("File too large")

    if data.get("encoding") != "base64":
        raise ValueError("Unsupported file encoding")

    encoded = data.get("content")
    if not isinstance(encoded, str):
        raise ValueError("File content is unavailable")

    content = base64.b64decode(encoded)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("File too large")

    text = content.decode("utf-8")
    lines = text.splitlines()

    # 6. Extract requested lines
    if start_line > len(lines):
        raise ValueError("Start line exceeds file length")

    selected = lines[start_line - 1:end_line]

    return "\n".join(
        f"{number}: {line}"
        for number, line in enumerate(selected, start=start_line)
    )



