# AI Research Analytics Platform

AI-Powered Research Portfolio and Analytics Platform for Sri Lanka.

This project collects, cleans, analyzes, and visualizes research publications by Sri Lankan researchers and institutions.

## Main Outputs

- Consolidated Sri Lankan research publication dataset.
- Cleaned and standardized publication database.
- AI/ML-based publication classification.
- Research analytics for productivity, citations, topics, and collaboration.
- Interactive dashboard for searching and visualizing research trends.

## Setup

Clone the repository:

```bash
git clone <repository-url>
cd researchlanka-ai
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Important GitHub Rules

- Do not work directly on `main`.
- Create one branch for each task.
- Create or use a GitHub issue before starting work.
- Use clear commit messages.
- Open a pull request before merging.
- Get at least one review before merging.
- Do not commit `.env`, passwords, API keys, or large datasets.

## Branch Example

```bash
git checkout main
git pull origin main
git checkout -b feature/openalex-collector
```

## Commit Example

```bash
git add .
git commit -m "feat(collector): add OpenAlex data collection"
git push origin feature/openalex-collector
```

## Useful Docs

- [Contributing Guide](CONTRIBUTING.md)
- [Branching and Commit Guide](docs/BRANCHING_AND_COMMITS.md)
- [GitHub Management Workflow](docs/GITHUB_MANAGEMENT.md)

## Team

- ANUSAN K. - 230048J
- ASMA AR - 230060M
- BANDARA K.G.C. - 230075M
