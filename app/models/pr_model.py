from typing import TypedDict, NotRequired

class ChangedFile(TypedDict):
    fileName: str
    status: str
    additions: str
    deletions: str
    patch: str | None
    previous_filename: NotRequired[str]

class PullRequestContext(TypedDict):
    title: str
    description: str
    base_sha: str
    head_sha: str
    files: list[ChangedFile]
