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
