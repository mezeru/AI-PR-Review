# AI Pull Request Investigator

A learning-focused Python CLI scaffold for a future pull request investigator.
The eventual Milestone 1 application will fetch a public GitHub pull request,
prepare its changed-file context, run one correctness reviewer through
LangGraph, validate structured findings, and print a local report.

## Milestone 1 flow

The planned flow is:

1. Fetch pull request metadata and changed files.
2. Prepare bounded diff context.
3. Ask one LLM to review correctness.
4. Validate the returned findings, with a bounded retry for invalid output.
5. Generate a local report.

Fetching, diff preparation, validation, and report generation are deterministic
nodes: they apply explicit program logic to inputs and outputs. The review node
is different because it will ask a language model to reason about the prepared
code changes. No node or graph behavior is implemented yet.

## Project map

- `app/main.py` — minimal command-line entry point.
- `app/graph.py` and `app/state.py` — future workflow construction and state.
- `app/schemas.py` — placeholders for future Pydantic output models.
- `app/nodes/` — one stub per planned workflow step.
- `app/services/github_client.py` — signatures for future read-only GitHub access.
- `tests/` — importability and scaffold smoke test only.
- [`IMPLEMENTATION_CHECKLIST.txt`](./IMPLEMENTATION_CHECKLIST.txt) — step-by-step
  implementation plan; all work remains unchecked.

## Setup

Create and activate a Python 3.11+ virtual environment, then install the listed
dependencies:

```text
python -m venv .venv
```

On Windows, activate it with:

```text
.\.venv\Scripts\Activate.ps1
```

Then install dependencies and prepare local settings:

```text
python -m pip install -r requirements.txt
copy .env.example .env
```

No dependency installation or API access is performed by this scaffold. The
environment file is optional for public pull requests; do not put real
credentials in tracked files.

## Current behavior

The CLI help is available with:

```text
python -m app.main --help
```

Invoking the CLI with `--pr-url` prints that review is not implemented and
returns a nonzero exit status. GitHub fetching, graph construction, prompts,
model calls, finding validation, retry routing, report generation, and GitHub
publishing are intentionally unfinished. The domain functions raise
`NotImplementedError`; this scaffold must not be used to review a real PR.

Run the scaffold smoke tests after installing the requirements:

```text
python -m pytest
```
