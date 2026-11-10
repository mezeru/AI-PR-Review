import re
import requests
import math
import json


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
    

    pattern = (
        r"https://github\.com/"
        r"(?P<owner>[^/]+)/"
        r"(?P<repo>[^/]+)/pull/"
        r"(?P<pull_number>\d+)/?"
    )

    match = re.fullmatch(pattern, pr_url.strip())

    if not match:
        raise ValueError("Invalid GitHub pull request URL")

    return (
        match.group("owner"),
        match.group("repo"),
        int(match.group("pull_number")),
    )
    


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

    Implement response validation, HTTP/API errors, timeouts, and safe handling
    of credentials yourself.
    """

    if not owner or not repo or not pull_number:
        raise ValueError

    headers = {
            "Accept": "application/vnd.github+json"
        }

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"

    if token:
            headers["Authorization"] = f"Bearer {token}"

    try:
        reponse  = requests.get(url=url, headers=headers, timeout=timeout)
        reponse.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Error Calling Github API {e}"

    if reponse.status_code != 200:
        return f"Github responded with {reponse.json()}"        
    
    try:
        metaData = reponse.json()
    except requests.exceptions.JSONDecodeError as e:
        raise ValueError("Invalid JSON from GitHub") from e

    if not isinstance(metaData, dict):
        raise ValueError("Unexpected GitHub metadata response")

    relevantData: dict | None = None
    relevantData["title"] = metaData.get("title")
    relevantData["mergeable_state"] = metaData.get("mergeable_state")
    relevantData["changed_files"] = metaData.get("changed_files")
    relevantData["body"] = metaData.get("body")
    relevantData["commits"] = metaData.get("commits")
    relevantData["additions"] = metaData.get("additions")
    relevantData["deletions"] = metaData.get("deletions")
    relevantData["comments"] = metaData.get("comments")
    relevantData["review_comments"] = metaData.get("review_comments")
    relevantData["base_sha"] = metaData.get("base").get("sha")
    relevantData["head_sha"] = metaData.get("head").get("sha")

    return relevantData


def fetch_pr_files(
    owner: str,
    repo: str,
    pull_number: int,
    token: str | None = None,
    timeout: float = 10.0
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

    Implement pagination, response validation, API errors, and timeouts yourself.
    """

    if not owner or not repo or not pull_number:
            return "Missing Value for owner, repo or pull_number"

    headers = {
        "Accept": "application/vnd.github+json"
    }

    files_patch = []

    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files"

    params = {"per_page": 100}

    while url:
    
        try:
            files_edited_reponse = requests.get(url=url, params=params, headers=headers, timeout=timeout)

            files_edited_reponse.raise_for_status()

            page_files = files_edited_reponse.json()

        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                "Failed to fetch PR files"
            ) from e

        if not isinstance(page_files, list):
            raise ValueError(
                "Unexpected GitHub files response"
            )

        files_patch.extend(page_files)

        url = files_edited_reponse.links.get("next", {}).get("url")

        params = None

    return files_patch


print(fetch_pr_files('mezeru','AI-PR-Review',1))
# print(json.dumps(fetch_pr_metadata('mezeru','AI-PR-Review',1)))
# print(parse_pr_url("https://api.github.com/repos/pl/ok/pulls/5/files"))



