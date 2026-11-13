"""Read-only GitHub pull request API helpers."""

from __future__ import annotations

import re
import base64
import requests
from urllib.parse import quote
from collections.abc import Mapping
from typing import Literal, TypedDict
from app.models.pr_model import PullRequestContext
from app.schemas import ReviewFinding


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


def fetch_repository_file_paths(
    owner: str,
    repo: str,
    ref: str,
    token: str | None = None,
    timeout: float = 10.0,
) -> list[str]:
    """Fetch repository file paths at a ref using GitHub's recursive tree API."""
    if not owner or not repo or not ref.strip():
        raise ValueError("owner, repo, and ref are required")

    url = (
        f"https://api.github.com/repos/{quote(owner, safe='')}/"
        f"{quote(repo, safe='')}/git/trees/{quote(ref, safe='')}"
    )
    try:
        response = requests.get(
            url,
            params={"recursive": "1"},
            headers=_headers(token),
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("Failed to fetch repository tree") from exc

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ValueError("GitHub returned invalid JSON for repository tree") from exc

    if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
        raise ValueError("Unexpected GitHub repository tree response")
    if not isinstance(data.get("truncated"), bool):
        raise ValueError("GitHub repository tree response is missing truncation status")
    if data["truncated"]:
        raise RuntimeError("GitHub returned a truncated repository tree")

    paths: list[str] = []
    for item in data["tree"]:
        if not isinstance(item, dict):
            raise ValueError("Unexpected GitHub repository tree entry")
        if item.get("type") == "blob":
            path = item.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError("GitHub repository tree entry is missing a file path")
            paths.append(path)

    return paths


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




LineType = Literal["added", "context"]

HUNK_PATTERN = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@"
)


class FindingLocationVerification(TypedDict):
    filename: str
    line: int | None
    file_exists: bool
    patch_available: bool
    line_in_patch: bool | None
    line_type: LineType | None
    verified: bool


def get_patch_line_types(patch: str) -> dict[int, LineType]:
    """
    Parse a unified diff and map new-file line numbers
    to their type: 'added' or 'context'.

    Deleted lines do not exist in the new file and
    therefore do not increment the new-line counter.
    """
    line_types: dict[int, LineType] = {}
    new_line_number: int | None = None

    for line in patch.splitlines():
        match = HUNK_PATTERN.match(line)

        if match:
            new_line_number = int(match.group(1))
            continue

        if new_line_number is None:
            continue

        # Ignore diff metadata
        if line.startswith("\\"):
            continue

        if line.startswith("+"):
            line_types[new_line_number] = "added"
            new_line_number += 1

        elif line.startswith(" "):
            line_types[new_line_number] = "context"
            new_line_number += 1

        elif line.startswith("-"):
            # Deleted lines do not increment new-file positions
            continue

    return line_types


def get_added_lines(patch: str) -> set[int]:
    """Return all added new-file line numbers."""
    return {
        line_number
        for line_number, line_type
        in get_patch_line_types(patch).items()
        if line_type == "added"
    }


def verify_finding_location(
    finding: ReviewFinding | Mapping[str, object],
    pr_context: PullRequestContext,
) -> FindingLocationVerification:
    """
    Verify whether a finding references a location
    present in the pull request's unified diff.

    A finding is location-verified when:
    - Its filename belongs to a changed PR file.
    - That file has an available patch.
    - Its line exists on the new-file side of the patch.

    This does not prove the reported bug is genuine.
    """

    # Extract finding fields
    if isinstance(finding, Mapping):
        filename = finding.get("filename")
        line = finding.get("line")
    else:
        filename = finding.file
        line = finding.line

    # Validate inputs
    if not isinstance(filename, str) or not filename:
        raise ValueError(
            "Finding must include a non-empty filename"
        )

    if line is not None and (
        not isinstance(line, int)
        or isinstance(line, bool)
        or line < 1
    ):
        raise ValueError(
            "Finding line must be a positive integer or None"
        )

    # Find the changed file in the PR
    changed_file = next(
        (
            file
            for file in pr_context["files"]
            if file["filename"] == filename
        ),
        None,
    )

    file_exists = changed_file is not None

    patch = (
        changed_file.get("patch")
        if changed_file is not None
        else None
    )

    patch_available = isinstance(patch, str) and bool(patch)

    # Parse the patch once
    line_types = (
        get_patch_line_types(patch)
        if patch_available
        else {}
    )

    line_type = (
        line_types.get(line)
        if line is not None
        else None
    )

    # None means verification could not be performed
    line_in_patch = (
        line in line_types
        if patch_available and line is not None
        else None
    )

    # Location verification, not semantic bug verification
    verified = (
        file_exists
        and patch_available
        and line_in_patch is True
    )

    return {
        "filename": filename,
        "line": line,
        "file_exists": file_exists,
        "patch_available": patch_available,
        "line_in_patch": line_in_patch,
        "line_type": line_type,
        "verified": verified,
    }

def get_file(
    owner: str,
    repo: str,
    source: str,
    fileName: str,
    token: str | None,
    timeout: float = 10.0,
    *,
    ref: str | None = None,
) -> str:
    """Fetch a repository file's raw UTF-8 text, optionally at a specific ref."""
    if not owner or not repo or not fileName:
        raise ValueError("owner, repo, and fileName are required")
    if any(part in (".", "..") for part in (owner, repo)):
        raise ValueError("Invalid repository name or owner")
    if ref is not None and not ref.strip():
        raise ValueError("ref must be nonempty when supplied")

    directory = source.strip("/")
    path = f"{directory}/{fileName}" if directory else fileName
    if (
        "\\" in path
        or "\0" in path
        or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        raise ValueError("Invalid file path")

    url = (
        f"https://api.github.com/repos/{quote(owner, safe='')}/"
        f"{quote(repo, safe='')}/contents/{quote(path, safe='/')}"
    )

    raw_media_type = "application/vnd.github.raw"
    headers = _headers(token)
    headers["Accept"] = raw_media_type
    try:
        response = requests.get(
            url,
            headers=headers,
            params={"ref": ref} if ref is not None else None,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("Failed to fetch file from GitHub") from exc

    media_type = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
    if media_type != raw_media_type:
        raise ValueError("GitHub did not return raw file content")
    return response.content.decode("utf-8")
