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

- [Data Collection Guide](docs/DATA_COLLECTION.md) - repository registry, harvesting scripts, per-institution status
- [Frontend Requirements](docs/frontend_requirements.md) - user personas and interface requirements
- [Contributing Guide](CONTRIBUTING.md)
- [System and Data-Pipeline Architecture](docs/SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md)
- [Branching and Commit Guide](docs/BRANCHING_AND_COMMITS.md)
- [GitHub Management Workflow](docs/GITHUB_MANAGEMENT.md)

## Collector Structure

Collector implementations live in `src/collectors/` and should keep network
access separate from command-line orchestration. Each collector follows the
same shape:

- `fetch_*()` methods request one API resource or page.
- `iter_*()` methods handle pagination and yield records.
- `total_*()` methods are used only when the source API exposes reliable counts.
- Shared HTTP retry/session behavior lives in `src/collectors/http.py`.
- Source-specific normalization lives in `src/preprocessing/`.
- CLI entrypoints live in `scripts/` and should call collector classes instead
  of duplicating request or pagination logic.

Run the OpenAlex pipeline with Crossref DOI enrichment in one command:

```bash
python scripts/kaggle_collect_openalex_sri_lanka.py --enrich-crossref --crossref-email you@example.com
```

## Team

- ANUSAN K. - 230048J
- ASMA AR - 230060M
- BANDARA K.G.C. - 230075M
