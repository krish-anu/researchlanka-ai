# Branching and Commits

Use this guide to keep project work easy to review and connect each change to a GitHub issue.

## Branch Naming

Create a branch for each task or issue.

```text
type/short-description
```

Examples:

```text
feature/openalex-full-data-collection
docs/system-pipeline-architecture
test/openalex-sample-records
fix/doi-normalization
```

## Commit Message Format

Use:

```text
type(scope): short description
```

Examples:

```text
feat(collector): add OpenAlex Sri Lanka collection
test(openalex): add sample record validation
docs(architecture): draft system and data pipeline
fix(preprocessing): handle missing publication year
```

## Common Types

| Type | Use for |
|---|---|
| `feat` | new functionality |
| `fix` | bug fixes |
| `docs` | documentation-only changes |
| `test` | test additions or updates |
| `refactor` | code restructuring without behavior changes |
| `chore` | maintenance tasks |

## Before Committing

Run:

```bash
git status
pytest -q
```

Do not commit `.env`, secrets, API keys, passwords, or large raw datasets.
