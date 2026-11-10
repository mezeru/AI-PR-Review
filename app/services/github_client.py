import re
import requests
import math


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
    

    pattern = r'https://api\.github\.com/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)'

    match = re.match(pattern, pr_url)

    if match:
        owner = match.group('owner')
        repo = match.group('repo')
        pull_number = match.group('pull_number')
        return (owner, repo, int(pull_number))
    else:
        raise ValueError("Invalid URL")
    


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
        return "Missing Value for owner, repo or pull_number"

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"

    try:
        reponse  = requests.get(url=url, token=token, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return f"Error Calling Github API {e}"

    if reponse.status_code != 200:
        return f"Github responded with {reponse.json()}"        

    metaData = reponse.json()

    relevantData = {}

    relevantData["title"] = metaData.get("title")
    relevantData["mergeable_state"] = metaData.get("mergeable_state")
    relevantData["changed_files"] = metaData.get("changed_files")
    relevantData["body"] = metaData.get("body")
    relevantData["base"] = metaData.get("base")
    relevantData["commits"] = metaData.get("commits")
    relevantData["additions"] = metaData.get("additions")
    relevantData["deletions"] = metaData.get("deletions")
    relevantData["comments"] = metaData.get("comments")
    relevantData["review_comments"] = metaData.get("review_comments")

    return relevantData
    




def fetch_pr_files(
    owner: str,
    repo: str,
    pull_number: int,
    token: str | None = None,
    timeout: float = 10.0,
    metaData: dict = {}
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


    paginations = math.ceil(metaData.get('changed_files')/100) + 1

    for i in range(1,paginations):

        params = {
        "per_page": 100,
        "page": i
        }
    
        try:
            files_edited_reponse = requests.get(url=url, params=params, headers=headers, timeout=timeout)

            files_edited_reponse_json = files_edited_reponse.json()

            for i in files_edited_reponse_json:
                files_patch.append(i)

        except requests.exceptions.RequestException as e:
            return f"Error Calling Github API {e}"

    return files_patch


# print(fetch_pr_files('mezeru','AI-PR-Review',1, metaData={"changed_files": 1}))

print(parse_pr_url("https://api.github.com/repos/pl/ok/pulls/5/files"))



