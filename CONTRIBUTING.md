# Contributing Guide

Thank you for contributing to the AI Research Analytics Platform.

## How to Contribute

1. Create or choose a GitHub issue.
2. Create a branch from the latest `main`.
3. Make focused changes.
4. Commit using the project commit style.
5. Push your branch.
6. Open a pull request.
7. Request review from another team member.
8. Merge only after approval.

## Branch Names

Use:

```text
type/short-description
```

Examples:

```text
feature/openalex-collector
fix/missing-doi-cleaning
docs/update-github-workflow
test/preprocessing-tests
```

## Commit Messages

Use:

```text
type(scope): short description
```

Examples:

```text
docs(readme): update setup instructions
feat(collector): add OpenAlex metadata collection
fix(cleaning): handle missing publication year
test(deduplication): add duplicate DOI test cases
```

## Pull Requests

Before opening a pull request:

- Link the related issue.
- Keep the change focused.
- Check `git status` and `git diff`.
- Do not include secrets, credentials, or large raw datasets.
- Run tests if tests are available.
- Update documentation if behavior or workflow changed.

## Data and Secrets

Do not commit:

- `.env` files.
- API keys.
- Passwords.
- Access tokens.
- Large raw datasets.
- Private or sensitive personal data.

Use `.env.example` to document required environment variables.

## More Details

Read the full workflow in [GitHub Management Workflow](docs/GITHUB_MANAGEMENT.md).
