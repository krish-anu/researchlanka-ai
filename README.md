# ResearchLanka AI

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

Google Maps institution-location confirmation is an offline data-quality step.
It does not run during `make dev`, `make backend`, or `make frontend`; run
`make maps-location-confirm` only when you intentionally want to collect new
location evidence.

## Dataset Ownership Policy

`common_publications_all_records.csv` is the broad candidate/source-evidence
dataset. The final application/database dataset is gated separately and contains
only records with `ownership_decision=INCLUDE`,
`ownership_confidence` of `HIGH` or `MEDIUM`, and
`needs_manual_review=False`.

"Sri Lanka-led" means publication-specific leadership evidence points to Sri
Lanka, for example a Sri Lankan corresponding/project-lead affiliation.
International collaborators are allowed. First-author-only, SLJOL venue-only,
repository-only, missing, weak, or conflicting evidence is kept for REVIEW and
does not enter the verified final dataset.

## Fresh Clone Setup With Data

Use these commands when setting up the full project on a new machine.

```bash
git clone https://github.com/krish-anu/researchlanka-ai.git
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

The public repository does not contain every operational dataset and model
artifact. The packaged dataset under `researchlanka-ai-dataset/` is a release
candidate, not an approved final public release. The current production model
is defined by `backend/configurations/ai_relevance_model_manifest.json`; its
artifact is transferred separately after licensing approval.

See [`HANDOVER.md`](HANDOVER.md) before obtaining or publishing external
artifacts. A handover bundle must identify its version, include checksums, and
restore paths relative to the repository root. Do not rely on an unversioned
`researchlanka-share-data.zip`.

Load the AI-only database and start the backend and frontend:

```bash
make load-db-ai
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

The full backend guide is in [`backend/README.md`](backend/README.md).

## Kaggle Run

For a complete Kaggle guide from uploading the dataset to downloading the final
outputs, see [`KAGGLE_README.md`](KAGGLE_README.md).

Recommended Kaggle notebook:

```text
dse-project.ipynb
```

Smaller alternative workflow:

```text
notebooks/kaggle_run_main_full_pipeline.ipynb
```

## Frontend

Frontend setup, architecture, roles, and security notes are in
[`frontend/README.md`](frontend/README.md).

## AWS Deployment

For the EC2 Docker Compose deployment path, see
[`docs/aws-ec2-app-deployment.md`](docs/aws-ec2-app-deployment.md). Terraform
for provisioning the EC2 host lives in
[`infra/terraform/aws-ec2`](infra/terraform/aws-ec2). For monthly
data/model refresh automation on AWS, see
[`docs/aws-monthly-automation.md`](docs/aws-monthly-automation.md).

## Documentation Map

Start with these documents:

- [`HANDOVER.md`](HANDOVER.md) - current readiness, verification results, and
  dataset/model publication blockers.
- [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) - system overview and repository
  architecture.
- [`docs/README.md`](docs/README.md) - active cross-project documentation and
  archived decision history.
- [`backend/docs/README.md`](backend/docs/README.md) - backend documentation
  index.
- [`researchlanka-ai-dataset/README.md`](researchlanka-ai-dataset/README.md) -
  dataset package status and contents.
- [`CHANGELOG.md`](CHANGELOG.md) - user-visible and operational changes.

The source code, checked-in configuration, and model manifest take precedence
if a historical report conflicts with current behavior.
