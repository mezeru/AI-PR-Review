from ..models.pr_model import PullRequestContext, ChangedFile

def normalize_pr_data(raw_data: dict) -> PullRequestContext:
    """
    Convert GitHub PR data into the internal
    representation used by the reviewer.
    """

    if not raw_data['title']:
        raise ValueError("No Title Avaiable, Try Again Later")

    if len(raw_data['files']) < 1:
        raise ValueError("No Changes Found, Skipping")

    files: list[ChangedFile] = []

    for i in raw_data['files']:
        file: ChangedFile = {
            "filename": i["filename"],
            "status": i["status"],
            "additions": int(i["additions"]),
            "deletions": int(i["deletions"]),
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
