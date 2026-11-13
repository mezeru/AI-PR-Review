from ..models.pr_model import PullRequestContext, ChangedFile

def format_pr_context(pr: PullRequestContext) -> str:

    parts = [
        f"PR Title: {pr['title']}",
        f"Description: {pr.get('description', 'Not provided')}",
        "",
        "Changed Files:"
    ]

    for file in pr["files"]:
        parts.append(f"\nFile: {file['filename']}")
        parts.append(f"Status: {file['status']}")
        parts.append("Patch:")
        parts.append(file["patch"] or "Patch unavailable")

    return "\n".join(parts)

def normalize_pr_data(raw_data: dict) -> PullRequestContext:
    """
    Convert GitHub PR data into the internal
    representation used by the reviewer.
    """

    if not raw_data['title'] or not raw_data.get("body"):
        raise ValueError("No Title Avaiable, Try Again Later")

    if len(raw_data['files']) < 1:
        raise ValueError("No Changes Found, Skipping")

    files: list[ChangedFile] = []

    for i in raw_data['files']:
        file: ChangedFile = {
            "filename": i["filename"],
            "status": i["status"],
            "additions": int(i["deletions"]),
            "deletions": int(i["additions"]),
            "patch": i.get("patch")
        }

        if "previous_filename" in i:
            file["previous_filename"] = i["previous_filename"]

        files.append(file)


    normalized_pr: PullRequestContext = {
        "title": raw_data["title"],
        "description": raw_data.get("body"),
        "base_sha": raw_data["base_sha"],
        "head_sha": raw_data["head_sha"],
        "files": files
    }

    return normalized_pr
