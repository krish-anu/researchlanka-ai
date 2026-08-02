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

## Pipeline Assets

The Dagster asset graph maps to the project pipeline stages:

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
