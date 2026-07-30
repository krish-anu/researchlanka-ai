# National Research Analytics Framework

A Sri Lanka national-level research analytics framework.

The framework collects, integrates, cleans, analyses, and exports scholarly
publication data for Sri Lanka.

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

## PostgreSQL Database

Create a `.env` file from `.env.example` and set your PostgreSQL connection URL:

```env
DATABASE_URL=postgresql://researchlanka_user:change_me@localhost:5433/researchlanka
```

Start PostgreSQL with Docker Compose:

```bash
docker compose up -d db
```

Check the connection:

```bash
python scripts/database/check_database_connection.py
```

Apply and verify the PostgreSQL schema:

```bash
python scripts/database/apply_database_migrations.py
python scripts/database/verify_database_schema.py
```

The production load writes deduplicated records into `final_publications`, whose
columns follow the latest finalized dataset schema from `FINAL_MAIN_COLUMNS`.
The Sri Lanka config enables `"load_database": true`, so `run-all` applies the
database load after deduplication:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

To run only the database load stage:

```bash
python -m research_analytics.cli load_database --config configurations/sri_lanka/config.json
```

Stop the database:

```bash
docker compose down
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
- [Metadata Quality Report Index](docs/00_metadata_quality_report_index.md) - missing values, completeness, conflicts, and final column decisions
- [Frontend Requirements](docs/frontend_requirements.md) - user personas and interface requirements
- [National Framework Guide](documentation/NATIONAL_RESEARCH_ANALYTICS_FRAMEWORK.md) - lecturer-aligned objective, architecture, proof plan, and deliverables
- [Migration to Framework Pipeline](documentation/MIGRATION_TO_RESEARCH_ANALYTICS_PIPELINE.md) - current main run path and legacy-script role
- [Contributing Guide](CONTRIBUTING.md)
- [System and Data-Pipeline Architecture](docs/SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md)
- [Branching and Commit Guide](docs/BRANCHING_AND_COMMITS.md)
- [GitHub Management Workflow](docs/GITHUB_MANAGEMENT.md)

## Sri Lanka National Framework Mode

The Sri Lanka national framework code lives in `research_analytics/`.
Sri Lanka source choices, institution registries, year ranges, categories,
field mappings, dashboard labels, and aliases live in `configurations/sri_lanka/`.

Run the Sri Lanka implementation:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

The practical deployment wrapper supports stage workflow:

```bash
python run_pipeline.py --config configurations/sri_lanka/config.json --stage all
python run_pipeline.py --config configurations/sri_lanka/config.json --stage deduplicate
```

The Makefile uses the framework pipeline as the national workflow:

```bash
make framework-sri-lanka
```

After installing the package, the CLI command is:

```bash
research-framework run-all --config configurations/sri_lanka/config.json
```

To validate the Sri Lanka source mapping before full import:

```bash
research-framework source-validate --config configurations/sri_lanka/config.json
research-framework preview --config configurations/sri_lanka/config.json --sample-size 5
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
is being migrated into the Sri Lanka framework. For example, the older OpenAlex
collector can still run with:

```bash
python scripts/collection/kaggle_collect_openalex_sri_lanka.py --enrich-crossref --crossref-email you@example.com
```

## Common Dataset Pipeline

Merge the four source CSVs into one deduplicated dataset, then build the cleaned final
dataset and its reference sidecar:

```bash
python scripts/processing/kaggle_merge_common_dataset.py
python scripts/processing/build_final_common_dataset.py
python scripts/processing/build_columns_filtered_dataset.py
python scripts/processing/build_year_filtered_dataset.py
python scripts/processing/build_language_normalized_dataset.py
python scripts/processing/build_multivalue_normalized_dataset.py
python scripts/processing/build_analysis_ready_dataset.py
```

Outputs land in `data/processed/common/`. Column keep/drop decisions are documented in
[docs/07](docs/07_last_26_columns_final_dataset_decisions.md),
[docs/08](docs/08_columns_26_50_final_dataset_decisions.md), and
[docs/09](docs/09_columns_1_25_final_dataset_decisions.md).

Profile the 76-column deduplicated dataset by column block - coverage, per-source
completeness, decisions, and duplicate/redundancy checks:

```bash
python scripts/analysis/columns/analyze_first_25_columns.py --report-dir data/reports/column_analysis
python scripts/analysis/columns/analyze_second_25_columns.py --report-dir data/reports/column_analysis
python scripts/analysis/columns/analyze_final_26_columns.py --report-dir data/reports/column_analysis
```

The analyzers read in chunks, so they work on the full multi-hundred-megabyte outputs.

For Kaggle analysis of every column in the current final dataset, use:

```bash
notebooks/05_kaggle_final_dataset_all_columns_analysis.py
```

## Team

- ANUSAN K. - 230048J
- ASMA AR - 230060M
- BANDARA K.G.C. - 230075M
