# National Research Analytics Framework

A reusable, configurable framework for national-level research analytics.

The framework collects, integrates, cleans, analyses, and exports scholarly
publication data for an entire country. Sri Lanka is the first implementation
and evaluation case; another country can reuse the same pipeline by changing
configuration, institution registries, mappings, and source settings.

## Main Outputs

- Consolidated national research publication dataset.
- Cleaned and standardized national research database.
- AI/ML-based publication classification.
- Research analytics for productivity, citations, topics, trends, and collaboration.
- Standard national exports for publications, authors, institutions, links, data quality, and analytics.

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
- [Reusable Framework Guide](documentation/REUSABLE_FRAMEWORK.md) - national framework package, configuration workflow, templates, and example runs
- [National Framework Guide](documentation/NATIONAL_RESEARCH_ANALYTICS_FRAMEWORK.md) - lecturer-aligned objective, architecture, proof plan, and deliverables
- [Migration to Framework Pipeline](documentation/MIGRATION_TO_RESEARCH_ANALYTICS_PIPELINE.md) - current main run path and legacy-script role
- [Contributing Guide](CONTRIBUTING.md)
- [System and Data-Pipeline Architecture](docs/SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md)
- [Branching and Commit Guide](docs/BRANCHING_AND_COMMITS.md)
- [GitHub Management Workflow](docs/GITHUB_MANAGEMENT.md)

## National Framework Mode

The reusable national framework code lives in `research_analytics/`.
Country-specific settings, source choices, institution registries, year ranges,
categories, field mappings, dashboard labels, and aliases live in
`configurations/`.

Run the example project:

```bash
python -m research_analytics.cli run-all --config configurations/example_country/config.json
```

Run the Sri Lankan implementation with the same framework code:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

The practical deployment wrapper supports the stage workflow used when bringing
a new country online:

```bash
python run_pipeline.py --config configurations/example_country/config.json --stage all
python run_pipeline.py --config configurations/example_country/config.json --stage deduplicate
```

The Makefile uses the framework pipeline as the national workflow:

```bash
make framework-sri-lanka
make framework-example
```

After installing the package, the CLI command is:

```bash
research-framework run-all --config configurations/example_country/config.json
```

To onboard a new source before full import:

```bash
research-framework source-validate --config configurations/example_country/config.json
research-framework preview --config configurations/example_country/config.json --sample-size 5
```

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

Legacy Sri Lanka-specific collection scripts remain available while the project
is being migrated into the reusable framework. For example, the older OpenAlex
collector can still run with:

```bash
python scripts/kaggle_collect_openalex_sri_lanka.py --enrich-crossref --crossref-email you@example.com
```

## Team

- ANUSAN K. - 230048J
- ASMA AR - 230060M
- BANDARA K.G.C. - 230075M
