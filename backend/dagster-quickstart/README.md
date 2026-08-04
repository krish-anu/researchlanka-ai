# ResearchLanka Dagster Quickstart

This Dagster project orchestrates the existing ResearchLanka backend pipeline.

## Getting started

### Installing dependencies

**Option 1: uv**

Ensure [`uv`](https://docs.astral.sh/uv/) is installed following their [official documentation](https://docs.astral.sh/uv/getting-started/installation/).

Create a virtual environment, and install the required dependencies using _sync_:

```bash
uv sync
```

Then, activate the virtual environment:

| OS | Command |
| --- | --- |
| MacOS | ```source .venv/bin/activate``` |
| Windows | ```.venv\Scripts\activate``` |

**Option 2: pip**

Install the python dependencies with [pip](https://pypi.org/project/pip/):

```bash
python3 -m venv .venv
```

Then activate the virtual environment:

| OS | Command |
| --- | --- |
| MacOS | ```source .venv/bin/activate``` |
| Windows | ```.venv\Scripts\activate``` |

Install the required dependencies:

```bash
pip install -e ".[dev]"
```

Install the backend package in editable mode:

```bash
pip install -e ..
```

### Running Dagster

Start the Dagster UI web server:

```bash
dg dev
```

Open http://localhost:3000 in your browser to see the project.

## Available Jobs

- `researchlanka_source_check_job` checks source connection, preview, and source
  validation.
- `researchlanka_export_job` runs the staged ResearchLanka pipeline and writes
  file outputs without loading PostgreSQL.
- `researchlanka_database_job` runs the staged ResearchLanka pipeline through
  the PostgreSQL load stage.
- `researchlanka_all_assets_job` materializes every asset in this code location.

The export and database jobs now collect enabled sources before downstream
processing starts. The first assets gather OpenAlex, Crossref, SLJOL, and
university repository data; `researchlanka_all_sources_common_dataset`
normalizes those collected files into
`data/processed/common/common_publications_all_records.csv` before source
validation, transformation, cleaning, analytics, and export assets run.
Set `RESEARCHLANKA_COMMON_WRITE_MERGE_OUTPUTS=1` when you also want the
common-dataset deduplicated CSV, merge log, summary, and manual-review files.
Enabled sources with missing or empty CSV outputs fail this merge by default;
set `RESEARCHLANKA_ALLOW_PARTIAL_COMMON_DATASET=1` only for an intentional
partial run.

For a quick smoke run, cap the external harvests:

```bash
mkdir -p /tmp/researchlanka-dagster-home
DAGSTER_HOME=/tmp/researchlanka-dagster-home \
RESEARCHLANKA_OPENALEX_MAX_RECORDS=1 \
RESEARCHLANKA_CROSSREF_MAX_RECORDS=1 \
RESEARCHLANKA_SLJOL_MAX_RECORDS=1 \
RESEARCHLANKA_REPOSITORY_MAX_RECORDS_PER_TARGET=1 \
RESEARCHLANKA_REPOSITORY_PHASE=phase_1 \
dagster job execute -m dagster_quickstart.definitions -j researchlanka_export_job
```

Repository collection also supports focused and cached runs:

```bash
RESEARCHLANKA_REPOSITORY_INCLUDE_IDS=uom,cmb,sliit
RESEARCHLANKA_REPOSITORY_EXCLUDE_IDS=seu,sltc,ruh
RESEARCHLANKA_REPOSITORY_SKIP_EXISTING=1
RESEARCHLANKA_REPOSITORY_WORKERS=3
RESEARCHLANKA_REPOSITORY_TIMEOUT=10
```

`RESEARCHLANKA_REPOSITORY_WORKERS` defaults to `3` for Dagster runs and only
parallelizes across different repository targets. Individual OAI, REST, and
HTML harvests remain sequential for each host. For a lecturer-ready full run,
omit `RESEARCHLANKA_REPOSITORY_INCLUDE_IDS`,
`RESEARCHLANKA_REPOSITORY_EXCLUDE_IDS`, and
`RESEARCHLANKA_REPOSITORY_SKIP_EXISTING` unless you intentionally want a partial
or cached run.

Omit the `*_MAX_RECORDS*` variables for a full 2016-2026 harvest. Set
`RESEARCHLANKA_OPENALEX_WRITE_PARQUET=1` only when the Dagster environment has
`pyarrow` or `fastparquet` installed.

OpenAlex collection resumes automatically when
`data/raw/openalex/openalex_sri_lanka_works.jsonl` and its progress JSON already
exist. Set `RESEARCHLANKA_OPENALEX_RESUME=0` only when you intentionally want to
start a fresh OpenAlex collection and overwrite the existing files.

Crossref collection uses affiliation queries `sri lanka`, `lanka`, and `ceylon`
by default. Override them with `RESEARCHLANKA_CROSSREF_QUERIES` only when you
want a narrower or experimental Crossref search.

SLJOL collection uses recursive Crossref publication-date windows by default,
so it can continue past repeated prefix cursors. The default SLJOL range is
2016-2026, matching the project collection range. Override it with
`RESEARCHLANKA_SLJOL_FROM_YEAR` and `RESEARCHLANKA_SLJOL_UNTIL_YEAR` when you
need a different date range.

## Pipeline Assets

The Dagster asset graph maps to the project pipeline stages:

- `researchlanka_openalex_api_collection`
- `researchlanka_crossref_api_collection`
- `researchlanka_sljol_api_collection`
- `researchlanka_repository_collection`
- `researchlanka_all_sources_collected`
- `researchlanka_all_sources_common_dataset`
- `researchlanka_source_connection`
- `researchlanka_source_preview`
- `researchlanka_source_validation`
- `researchlanka_collected_records`
- `researchlanka_transformed_records`
- `researchlanka_validation_report`
- `researchlanka_cleaned_records`
- `researchlanka_national_records`
- `researchlanka_deduplicated_records`
- `researchlanka_analytics_summary`
- `researchlanka_export_files`
- `researchlanka_database_loaded_records`

## Learn more

To learn more about this template and Dagster in general:

- [Dagster Documentation](https://docs.dagster.io/)
- [Dagster University](https://courses.dagster.io/)
- [Dagster Slack Community](https://dagster.io/slack)
