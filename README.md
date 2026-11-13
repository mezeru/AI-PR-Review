# AI PR Reviewer

AI PR Reviewer is a Python command-line application that reviews a GitHub pull
request for actionable defects introduced by its changes. It retrieves PR data
through the GitHub REST API, asks a Qwen code-review model through Hugging Face
Inference Providers to investigate the changes, and coordinates model and tool
calls with LangGraph.

## What it does

- Accepts a `github.com` pull-request URL, then fetches the PR metadata and
  changed-file patches.
- Builds an in-memory BM25 symbol index from repository source metadata.
- Sends the PR title, description, and changed-file patches to the reviewer.
- Gives the model two read-only tools: search indexed symbols and retrieve a
  bounded range of source lines from the repository.
- Validates the final response against a Pydantic schema.
- Checks whether each reported location belongs to a changed file and a line
  represented in its patch. This confirms location, not that the finding is a
  genuine defect.
- Prints the validated findings as JSON.
- Uses Langfuse callbacks for graph tracing when configured.

The review graph permits up to 10 tool results in total. Source-context requests
are limited to 150 lines each. If the tool budget is exhausted, the reviewer is
asked to finalize using the evidence gathered so far.

## Review flow

1. Parse the PR URL and fetch its metadata and changed files.
2. Normalize the API response into the application's PR context.
3. Extract repository symbol metadata and build the BM25 search index.
4. Ask the model to review the PR. It may call the symbol-search or file-context
   tool for more information.
5. Validate the final structured response and verify finding locations against
   the PR patches.
6. Print the findings JSON to standard output.

![LangGraph review workflow](review+graph.png)

The command-line output contains the findings. Location-verification details
are kept in the graph result and are not currently printed by the CLI.

## Requirements and setup

- Python 3.11 or newer
- A Hugging Face access token with access to the configured inference provider
- Optional: a GitHub token for authenticated API requests, private repositories,
  or higher API rate limits

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Set credentials in your shell or a local, untracked `.env` file:

```text
HF_TOKEN=your_hugging_face_token
GITHUB_TOKEN=your_github_token
```

`HF_TOKEN` is required. `GITHUB_TOKEN` is optional for public repositories.
Never commit credentials.

## Run a review

Pass the PR URL as an argument:

```powershell
python -m app.main --pr-url https://github.com/owner/repository/pull/123
```

Or omit `--pr-url` to be prompted:

```powershell
python -m app.main
```

The CLI prints a JSON object with a `findings` array. Each finding contains a
file, an optional line number, severity, category, explanation, evidence, and a
suggested fix. If no actionable findings are returned, the array is empty.

## Code retrieval and indexing

The runtime symbol index is created by `build_pr_symbol_index`. It extracts
symbol metadata from repository files and ranks matches with BM25. The
`search_codebase` tool returns matching symbol names, types, filenames, line
ranges, and signatures. The `get_file_context` tool fetches numbered source
lines from the PR repository.

The repository also provides a separate chunking utility for callers that need
bounded code chunks from selected files:

```python
from app.rag.ingestion import chunk_pr_files
from app.services.github_client import consolidate_pr_data
from app.services.pr_normalizer import normalize_pr_data

pr_url = "https://github.com/owner/repository/pull/123"
pr_context = normalize_pr_data(consolidate_pr_data(pr_url))
batch = chunk_pr_files(
    pr_url,
    pr_context,
    ["src/service.py", "web/view.tsx", "config.yaml"],
)

for chunk in batch.chunks:
    print(
        chunk["filename"],
        chunk["language"],
        chunk["symbol"],
        chunk["start_line"],
        chunk["end_line"],
        chunk["parse_status"],
    )
```

Chunking recognizes Python, JavaScript, TypeScript, TSX, and Java. Other
extensions use bounded text chunks. Defaults are 100 lines and 8,000 characters
per chunk, with up to 10 lines of overlap. A line longer than the character
limit can span multiple chunks. Parse status describes the whole file.

The language pack may download grammars on first use. To prime its cache before
running chunking tests offline:

```powershell
python -c "from tree_sitter_language_pack import prefetch; prefetch(['python', 'javascript', 'typescript', 'tsx', 'java'])"
python -m pytest -q tests/test_chunker.py tests/test_rag_ingestion.py
```

`extract_symbol_metadata(source, filename)` returns metadata for declarations
and a file record for nonempty input. Callable signatures omit function bodies;
variable signatures omit initializers. Some parameter defaults are replaced
with `...`. Extracted identifiers, paths, comments, docstrings, and type
annotations may still contain sensitive information. Treat repository-derived
metadata as potentially confidential.

## Tests

Run the test suite with:

```powershell
python -m pytest -q
```

Tests cover chunking, repository-file ingestion, symbol extraction, symbol
indexing, and import/callability smoke checks. In the current checkout,
`tests/test_scaffold.py` imports node modules that are not present under
`app/nodes/`, so full-suite collection fails until those imports and the
available implementation are brought back into sync.

## Project layout

- `app/main.py` — command-line arguments and review entry point.
- `app/graph.py` — LangGraph construction, tool routing, budget handling, and
  review execution.
- `app/agent.py` — model prompts, Hugging Face inference, tool schemas, and
  response conversion.
- `app/nodes/` — model invocation, response validation, budget handling, and
  finding-location verification.
- `app/services/github_client.py` — GitHub API access, source retrieval,
  pagination, and unified-diff location checks.
- `app/services/pr_normalizer.py` — PR context normalization and prompt
  formatting.
- `app/models/pr_model.py` — typed PR and changed-file context.
- `app/schemas.py` — Pydantic finding and review-result schemas.
- `app/state.py` and `app/context.py` — graph state and runtime context types.
- `app/rag/` — symbol extraction, BM25 search, and code chunking utilities.
- `app/tools/` — model-callable source-context and symbol-search tools.
- `tests/` — automated tests.
- `requirements.txt` — Python dependencies.
