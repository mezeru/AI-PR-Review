"""Single-model pull request correctness review."""

import json
import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

from app.models.pr_model import PullRequestContext
from app.schemas import ReviewResult


MODEL_ID = "Qwen/Qwen3-Coder-480B-A35B-Instruct"

SYSTEM_PROMPT = """
You are an expert software engineer reviewing GitHub Pull Requests.

Your objective is to identify functional bugs introduced by the PR.

Rules:
1. Identify correctness, security, reliability, and performance bugs.
2. Do not report style issues, variable naming, formatting,
   missing newlines, or minor maintainability suggestions.
3. Only report issues supported by the provided code.
4. Explain how each bug could cause incorrect runtime behavior.
5. Do not assume code outside the provided diff is incorrect.
6. If additional context is required, state that the finding
   needs verification.
7. Do not invent line numbers.
8. Return an empty findings list if no bugs are identified.

For each finding include:
- File path
- Line number, when known
- Severity
- Explanation
- Evidence
- Suggested fix

Prioritize precision over the number of findings.
"""

REVIEW_RULES = """
RULES TO FOLLOW

Only report actionable bugs introduced by the changes.

Before reporting a finding:
1. Identify the exact code responsible.
2. Explain the specific conditions required to trigger the bug.
3. Explain the observable incorrect behavior.
4. Verify that the finding is supported by the supplied code.
5. Do not report a variable typo unless it causes an actual
   unresolved reference.
6. Do not assume type annotations enforce runtime validation.
7. Do not report code style, formatting, or naming preferences.
8. Do not invent dependencies or behavior from unseen files.
9. If the evidence is insufficient, omit the finding or
   mark it as requiring verification.
10. Assign severity based on demonstrated impact.

Return an empty findings list if no verified bugs exist.
"""

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "ReviewResult",
        "schema": ReviewResult.model_json_schema(),
        "strict": True
    }
}


def review_pull_request(pr_context: PullRequestContext) -> str:
    """Review normalized pull request data and return the model's response."""
    load_dotenv()
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is required to run the model review.")

    client = InferenceClient(
        provider="featherless-ai",
        token=token
    )
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {
                "role": "system",
                "content": (SYSTEM_PROMPT + "\n" + REVIEW_RULES
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review this pull request context for correctness bugs:\n"
                    f"{json.dumps(pr_context, ensure_ascii=False)}"
                ),
            },
        ],
        max_tokens=800,
        temperature=0.1,
        response_format=response_format
    )

    if not response.choices:
        raise RuntimeError("The model returned no response choices.")

    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The model returned an empty or non-text response.")

    return content
