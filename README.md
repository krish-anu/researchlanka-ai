# researchlanka-ai

This repository is organized into two top-level workspaces:

- `backend/` - Python research analytics pipeline, API, database scripts, docs, tests, and data configuration.
- `frontend/` - Frontend application workspace.

## Quick Start

From the repository root:

```bash
make install
make dev
```

This starts the backend API at `http://127.0.0.1:8080/api/v1` and the
frontend at `http://127.0.0.1:3000`.

## Fresh Clone Setup With Data

Use these commands when setting up the full project on a new machine.

```bash
git clone <repository-url>
cd researchlanka-ai
make install
```

Start PostgreSQL and create the backend environment file:

```bash
cd backend
printf "DATABASE_URL=postgresql://researchlanka_user:change_me@localhost:5433/researchlanka\n" > .env
docker compose up -d db
.venv/bin/python scripts/database/check_database_connection.py
.venv/bin/python scripts/database/apply_database_migrations.py
.venv/bin/python scripts/database/verify_database_schema.py
cd ..
```

The large data and model files are not committed to git. To restore the
prepared dataset, place `researchlanka-share-data.zip` in the repository root
and unzip it:

```bash
unzip researchlanka-share-data.zip
```

The zip should restore these files:

```text
backend/data/processed/common/common_publications_final_2016_2026.csv
backend/data/models/publication_text_embeddings_cli_sample.parquet
backend/data/models/publication_text_embedding_model_cli_sample.joblib
```

Load the database and start the backend and frontend:

```bash
make reset-db-2016-now
make dev
```

You can also run each side separately:

```bash
make backend
make frontend
```

Use port overrides when needed:

```bash
BACKEND_PORT=8082 FRONTEND_PORT=3001 make dev
```

## Backend

Run backend commands from the backend folder:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

The full backend README is in `backend/README.md`.

## Kaggle Run

For a complete Kaggle guide from uploading the dataset to downloading the final
outputs, see `KAGGLE_README.md`.

Recommended Kaggle notebook:

```text
dse-project.ipynb
```

Alternative copy:

```text
notebooks/kaggle_run_main_full_pipeline.ipynb
```

## Frontend

Frontend code should be added inside `frontend/`.
