"""Single-model pull request correctness review."""

import json
import os
from huggingface_hub import InferenceClient
from app.models.pr_model import PullRequestContext
from app.schemas import ReviewResult
from langchain_core.utils.function_calling import (
    convert_to_openai_tool
)
from app.tools.fetch_file_tool import get_file_context
from langchain_core.messages import AIMessage
from app.tools.rag_check import search_codebase


tool_schemas = [
    convert_to_openai_tool(get_file_context),
    convert_to_openai_tool(search_codebase)
]


MODEL_ID = "Qwen/Qwen3-Coder-480B-A35B-Instruct"

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "ReviewResult",
        "schema": ReviewResult.model_json_schema(),
        "strict": True
    }
}

SYSTEM_PROMPT = f"""
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

FINAL_PROMPT = """
Finalize the PR review using only the available evidence.

Return ONLY a JSON object with this exact structure:

{
  "findings": [
    {
      "file": "app/example.py",
      "line": 42,
      "severity": "high",
      "category": "correctness",
      "explanation": "Explain the actual incorrect behavior.",
      "evidence": "Describe a concrete triggering scenario.",
      "suggested_fix": "Describe how to correct the issue."
    }
  ]
}

Rules:
- The example above illustrates format only, not a real finding.
- All seven fields are required for every finding.
- file, line, severity, category, explanation,
  evidence, and suggested_fix must be at the same level.
- line can be null if unknown.
- severity: critical, high, medium, low.
- category: correctness, security, performance, reliability.
- Do not use 'type', 'description', 'details', or 'fix'.
- Do not report speculative bugs.
- If no genuine findings exist, return {"findings": []}.
- Do not wrap the JSON in Markdown.
"""


def review_pull_request(messages = [], is_final: bool = False) -> AIMessage:
    """Review normalized pull request data and return the model's response."""
    token = os.getenv("HF_TOKEN")

    if not token:
        raise RuntimeError("HF_TOKEN is required to run the model review.")

    client = InferenceClient(
        provider="featherless-ai",
        token=token
    )

    if is_final:
        response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + '\n' + FINAL_PROMPT},
                    *messages
                ],
                max_tokens=2000,
                temperature=0.1,
                response_format=response_format
                
            )
    else:

        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages
            ],
            max_tokens=800,
            temperature=0.1,
            tools=tool_schemas,
            tool_choice='auto'
            
        )

    return convert_hf_response(response)

def convert_hf_response(response) -> AIMessage:

    hf_message = response.choices[0].message

    tool_calls = []

    for call in hf_message.tool_calls or []:

        arguments = call.function.arguments

        # Some provider responses use JSON strings,
        # others expose decoded dictionaries.
        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        if not isinstance(arguments, dict):
            raise ValueError("Invalid tool arguments")

        tool_calls.append({
            "name": call.function.name,
            "args": arguments,
            "id": call.id,
            "type": "tool_call"
        })

    return AIMessage(
        content=hf_message.content or "",
        tool_calls=tool_calls
    )