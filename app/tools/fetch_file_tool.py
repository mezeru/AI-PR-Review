from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.services.github_client import fetch_file_lines, parse_pr_url
from langchain.tools import ToolRuntime
import os

class FetchFileArgs(BaseModel):
    path: str = Field(
        description="Repository-relative path of the source file."
    )

    start_line: int = Field(
        ge=1,
        description="First line to retrieve, starting at 1."
    )

    line_count: int = Field(
        ge=1,
        le=150,
        description="Number of lines to fetch. Maximum 150."
    )

@tool(args_schema=FetchFileArgs)
def get_file_context(path:str, start_line:int, line_count: int, runtime: ToolRuntime)-> str:
    """Fetch up to 150 lines from the current PR repository."""
    end_line = start_line + line_count - 1
    state = runtime.state
    owner, repo, _ = parse_pr_url(state['pr_url'])
    return fetch_file_lines(owner,repo,path, state['pr_context']['head_sha'], start_line, end_line, token=os.getenv("GITHUB_TOKEN"),)