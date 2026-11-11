"""Single-model pull request correctness review."""

import json
import os
from huggingface_hub import InferenceClient
from app.models.pr_model import PullRequestContext
from app.schemas import ReviewResult





MODEL_ID = "Qwen/Qwen3-Coder-480B-A35B-Instruct"

SYSTEM_PROMPT = """
You are a senior software engineer performing
a correctness-focused GitHub Pull Request review.

Your task is to find defects introduced by the changed code
that could cause observable incorrect behavior.

REVIEW PROCESS:

1. Understand the intended behavior of the changed code.
2. Examine the added and modified lines in the patch.
3. Trace how the changes affect execution, data flow,
   state, and interactions with other functions.
4. Identify specific scenarios where the implementation
   produces incorrect results, raises unexpected exceptions,
   introduces vulnerabilities, or breaks existing behavior.
5. Verify each candidate issue against the available code.
6. Report only actionable findings supported by evidence.

A valid finding must include:
- The changed code responsible for the defect.
- The input or conditions that trigger the defect.
- The expected behavior.
- The actual incorrect behavior.
- A practical correction.

Severity must reflect the impact of the failure.

If the code appears correct or there is insufficient
evidence to establish a defect, return an empty findings list.

Only report bugs introduced by the PR.
Exclude cosmetic issues and speculative concerns.

Return findings matching the required JSON schema.
"""

EXAMPLE = """
EXAMPLE — NOT A BUG:

Changed code:
    reponse = requests.get(url)
    reponse.raise_for_status()

Analysis:
The variable spelling does not affect execution.
Both references use the same identifier, so no NameError
occurs.

Correct output:
{"findings": []}
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
                "content": (SYSTEM_PROMPT + "\n" + EXAMPLE
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
