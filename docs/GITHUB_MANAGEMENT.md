# GitHub Management Workflow

This project uses GitHub issues, branches, pull requests, and reviews to keep work organized.

## Issue Workflow

1. Create or choose an issue before starting work.
2. Confirm the task scope in the issue.
3. Create a branch from the latest `main`.
4. Make focused changes for that issue only.
5. Run tests or document why tests were not needed.
6. Open a pull request and link the issue.
7. Request review.
8. Merge after approval.

## Pull Request Checklist

Before opening a PR, check:

- The PR links the related issue.
- The change is focused.
- Documentation is updated if behavior or workflow changed.
- Tests pass with `pytest -q` when code changed.
- No secrets or large datasets are committed.
- `git status` only shows intended files.

## Issue Closing Rules

Close an issue only when the repository contains clear evidence that the task is done.

Examples:

- A documentation issue should have the promised document committed.
- A test issue should have repeatable tests committed.
- A collection issue should include runnable collection code or a notebook with a clear workflow.
- A pipeline issue should include architecture notes, module changes, or executable workflow updates.

## Week 1 Issue Status

For the current Week 1 work:

- `#133`: definition work is documented in the OpenAlex collector and analysis notebook.
- `#134`: OpenAlex fields and LK filters are implemented in the collector.
- `#135`: OpenAlex sample-record tests live in `tests/test_openalex_collection.py`.
- `#136`: system and data-pipeline architecture is documented in `docs/SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md`.
