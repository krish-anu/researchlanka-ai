# ResearchLanka AI Project Overview

This file is an onboarding brief for a new developer, researcher, or AI assistant.
Read it before changing the project. It explains what the system is, how the
main parts fit together, where important code lives, and which commands are used
to run and validate it.

## 1. Project Purpose

ResearchLanka AI is a Sri Lanka national research analytics platform focused on
scholarly publication data, with a strong focus on AI-related research. The
project collects publication records from research sources, normalizes and
deduplicates them, applies quality and Sri Lanka-ownership rules, classifies AI
relevance, loads accepted records into PostgreSQL, exposes a read-only HTTP API,
and presents the data in a Next.js web interface.

The main user-facing product is a dashboard/search platform for exploring Sri
Lankan AI publications, institutions, researchers, topics, collaborations, open
access status, and data-quality limitations.

## 2. Repository Shape

The repository has two main workspaces:

- `backend/` - Python data pipeline, reusable research analytics framework,
  collectors, processing stages, AI relevance pipeline, PostgreSQL loader, API,
  models, tests, and backend documentation.
- `frontend/` - Next.js App Router application for the public dashboard,
  account/admin pages, visualizations, exports, and local frontend state.

Important top-level files and folders:

- `README.md` - root quick start and setup notes.
- `Makefile` - root commands for installing, running, testing, and loading data.
- `KAGGLE_README.md` - guide for full Kaggle pipeline runs.
- `docs/` - AWS deployment, CI/CD, monthly automation, and workflow runbooks.
- `researchlanka-ai-dataset/` - packaged public dataset and dataset metadata.
- `notebooks/` - Kaggle and analysis notebooks.
- `.github/workflows/` - CI, branch protection, and deployment workflows.

## 3. The Most Important Architecture Point

The backend intentionally contains two related implementations:

- `backend/research_analytics/` is the reusable, config-driven national research
  analytics framework. It is intended to be reusable beyond this Sri Lanka app.
- `backend/src/` is the concrete Sri Lanka pipeline, API, model, and script
  implementation. Most working application code currently lives here.

Both are active. Do not assume one is obsolete. If you are changing reusable
framework behavior, look in `research_analytics/`. If you are changing the
current ResearchLanka application, API, AI relevance workflow, or dashboard data
pipeline, you will usually work in `backend/src/` and `backend/scripts/`.

## 4. High-Level Data Flow

The publication data flow is:

```text
External sources
  OpenAlex, Crossref, OAI-PMH repositories, DSpace REST, SLJOL, HTML metadata
        |
        v
Collectors
  backend/src/collectors/
  backend/src/pipeline/harvest_*.py and collect_*.py
        |
        v
Raw files
  backend/data/raw/
        |
        v
Preprocessing and schema mapping
  backend/src/preprocessing/
  backend/src/processing/
        |
        v
Processed common publication datasets
  backend/data/processed/common/
        |
        v
Cleaning, deduplication, institution normalization, ownership gating,
year filtering, language/multivalue normalization, analysis-ready outputs
  backend/src/pipeline/build_*.py
        |
        v
AI relevance classification and review filtering
  backend/src/ai_relevance/
  backend/scripts/ai_relevance/
        |
        v
PostgreSQL table: final_publications
  backend/src/database/
  backend/database/migrations/
        |
        v
Read-only API
  backend/src/api/
        |
        v
Next.js frontend
  frontend/src/
```

Generated datasets under `backend/data/processed/` should not be hand-edited.
Regenerate them by running the stage that owns the output.

## 5. Backend Components

Key backend folders:

- `backend/src/collectors/` - OpenAlex, Crossref, OAI-PMH, DSpace REST, HTML
  metadata, sitemap, repository registry, and shared HTTP collection utilities.
- `backend/src/preprocessing/` - source-specific normalization such as OpenAlex
  and Crossref flattening.
- `backend/src/processing/` - tabular conversion and common schema mapping.
- `backend/src/pipeline/` - ordered dataset stages, final dataset builders,
  repository append logic, incremental update flow, and AI publication dataset
  construction.
- `backend/src/ai_relevance/` - AI relevance model, Gemini/LLM review support,
  calibration, hard negatives, sampling, human verification metrics, and
  prediction workflows.
- `backend/src/database/` - PostgreSQL connection, migrations, schema checks,
  final table definition, and batch loading.
- `backend/src/api/` - API core, repositories, services, routing, and transports.
- `backend/src/modeling/` - publication classification, embeddings, SVM/logistic
  regression training, inference, evaluation, and artifact manifests.
- `backend/src/quality/` - validation, audits, DOI comparison, Google Maps
  institution confirmation, and duplicate analysis.
- `backend/research_analytics/` - reusable national framework abstractions:
  adapters, schema, transformations, analytics, exporters, networks, venues,
  authors, institutions, validation, pagination, and CLI.

Backend API notes:

- The main read-only API is under `/api/v1`.
- The standard development server is started by `backend/scripts/api/serve_api.py`
  or `make backend` from the root.
- Important API areas include publications, search, researchers, institutions,
  topics, analytics, collaboration network, data quality, exports, admin
  incremental update, AI review, monitoring, and feedback.
- `backend/src/api/README.md` explains the API package layout.
- Top-level modules like `src.api.service` and `src.api.repository` are
  compatibility exports. New API code should usually go into focused
  subpackages such as `core/`, `repositories/`, `services/`, `routing/`, or
  `transport/`.

## 6. Frontend Components

The frontend is a Next.js App Router application.

Key frontend folders:

- `frontend/src/app/` - routes and pages.
- `frontend/src/components/` - reusable UI, charts, admin panels, auth widgets,
  publication cards, network views, and layout components.
- `frontend/src/services/` - API client, auth/session logic, local JSON-file
  stores, filters, links, formatting, admin services, and workspace actions.
- `frontend/src/types/` - shared TypeScript types.

Major pages include:

- `/` - AI research overview dashboard.
- `/publications` - publication search, filtering, table/card views, exports.
- `/institutions` - institution rankings, profiles, and comparison.
- `/researchers` - researcher profiles and co-author information.
- `/topics` - field/subfield/topic exploration.
- `/collaboration` - collaboration network interface.
- `/data-quality` - completeness, coverage, conflicts, and limitations.
- `/login`, `/register`, `/account` - account and saved-record features.
- `/admin` - pipeline, AI review, flags, users, monitoring, and related admin
  workflows.

The backend API is read-only. Frontend accounts, saved records, flags, and
resolution decisions are stored locally under `frontend/.data/` through JSON
files. This is suitable for one local Node process, not a multi-instance
production deployment.

## 7. Setup and Run Commands

From the repository root:

```bash
make install
make dev
```

This installs backend and frontend dependencies, then runs:

- Backend API: `http://127.0.0.1:8080/api/v1`
- Frontend: `http://127.0.0.1:3000`

Run each side separately:

```bash
make backend
make frontend
```

Use different ports if needed:

```bash
BACKEND_PORT=8082 FRONTEND_PORT=3001 make dev
```

Backend-only setup:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Frontend-only setup:

```bash
cd frontend
npm install
npm run dev
```

## 8. Database Setup

The backend uses PostgreSQL for the API dataset.

Typical local setup:

```bash
cd backend
printf "DATABASE_URL=postgresql://researchlanka_user:change_me@localhost:5433/researchlanka\n" > .env
docker compose up -d db
.venv/bin/python scripts/database/check_database_connection.py
.venv/bin/python scripts/database/apply_database_migrations.py
.venv/bin/python scripts/database/verify_database_schema.py
cd ..
```

Load the AI-reviewed public dataset:

```bash
make reset-db-ai
```

Useful database-related commands:

```bash
make load-db-ai
make incremental-update
make retire-stale-db-2016-now
```

Migrations live in `backend/database/migrations/`. Do not edit an already
applied migration; add a new numbered migration.

## 9. Important Environment Variables

Common backend variables:

- `DATABASE_URL` - PostgreSQL connection string.
- `RESEARCHLANKA_ADMIN_API_TOKEN` - required for protected admin API actions.
- `RESEARCHLANKA_SEMANTIC_EMBEDDINGS_PATH` - semantic-search embeddings path.
- `RESEARCHLANKA_SEMANTIC_MODEL_PATH` - semantic-search vectorizer/model path.
- `RESEARCHLANKA_MODEL_PATH` and `RESEARCHLANKA_MODEL_MANIFEST_PATH` - model API
  artifact overrides.

Common frontend variables:

- `API_BASE_URL` - backend API URL used by the frontend.
- `AUTH_SECRET` - required in production to sign session cookies.
- `ADMIN_EMAIL` and `ADMIN_PASSWORD` - seed a production admin account.
- `SEED_TEST_ACCOUNTS=false` - disables public local test accounts.

See `frontend/.env.example`, `backend/README.md`, and root `README.md` for
details.

Never commit `.env`, passwords, API keys, or private datasets.

## 10. Testing and Validation

Run all checks from the root:

```bash
make test
```

This delegates to backend and frontend checks.

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run check:palette
npm test
npm run build
```

The frontend README lists the intended validation set as:

```bash
npm run lint
npm test
npm run check:palette
npm run build
```

For data-quality validation, inspect `backend/src/quality/`,
`backend/scripts/quality/`, and backend docs such as
`backend/docs/00_metadata_quality_report_index.md`.

## 11. AI Relevance Workflow

The AI relevance system identifies whether publication records are related to
AI research. It includes:

- Candidate sampling and LLM review support.
- Gemini/OpenRouter/Ollama-oriented review experiments and prediction files.
- Human verification and review splits.
- Linear SVM and metadata-ablation models.
- Hard-negative construction and feedback loops.
- Final review-gated dataset generation.

Important locations:

- `backend/src/ai_relevance/`
- `backend/scripts/ai_relevance/`
- `backend/docs/AI_RELEVANCE_PIPELINE.md`
- `backend/docs/AI_RELEVANCE_MODEL_DEVELOPMENT_REPORT.md`
- `backend/docs/AI_RELEVANCE_MODEL_SELECTION.md`
- `backend/data/models/ai_relevance/`
- `backend/data/processed/ai/`

The accepted AI-reviewed public dataset is the boundary used for the app and
database load. The ownership and AI-review gates are important; do not bypass
them casually.

## 12. Dataset Ownership Policy

The broad candidate/source-evidence dataset is not the same as the final public
application dataset.

The final application/database dataset should contain only records that pass the
Sri Lanka-led ownership policy and AI review gate. The root README summarizes
the current ownership rule:

- `ownership_decision=INCLUDE`
- `ownership_confidence` is `HIGH` or `MEDIUM`
- `needs_manual_review=False`

"Sri Lanka-led" means publication-specific evidence points to Sri Lanka, such
as a Sri Lankan corresponding author or project-lead affiliation. Weak evidence
such as first-author-only, SLJOL venue-only, repository-only, missing, or
conflicting evidence should stay in review and not enter the verified final
dataset.

## 13. Deployment and Automation

Deployment material lives mainly in:

- `compose.aws.yml`
- `deploy/aws.ec2.env.example`
- `docs/aws-ec2-app-deployment.md`
- `docs/aws-monthly-automation.md`
- `docs/ci-cd-ec2.md`
- `.github/workflows/deploy-main-to-ec2.yml`

Automation scripts:

- `scripts/aws_monthly_pipeline.sh`
- `scripts/aws_incremental_pipeline.sh`
- `scripts/aws_trigger_kaggle_monthly.sh`

The EC2 path uses Docker Compose. Monthly automation refreshes data/model
artifacts and supports incremental updates.

## 14. Where to Look Before Editing

Use this map to avoid touching the wrong layer:

- API endpoint behavior: `backend/src/api/services/`, `backend/src/api/routing/`,
  `backend/src/api/repositories/`.
- Database schema/load issue: `backend/database/migrations/`,
  `backend/src/database/`.
- Frontend page or route: `frontend/src/app/`.
- Frontend chart/UI component: `frontend/src/components/`.
- Frontend API request shape/types: `frontend/src/services/api.ts` and
  `frontend/src/types/api.ts`.
- Auth, roles, sessions, saved records, flags: `frontend/src/services/auth/`,
  `frontend/src/services/store/`, `frontend/src/services/workspace/`.
- Publication data pipeline: `backend/src/pipeline/`.
- External source collection: `backend/src/collectors/` and
  `backend/scripts/collection/`.
- AI relevance model/review logic: `backend/src/ai_relevance/` and
  `backend/scripts/ai_relevance/`.
- Reusable national framework behavior: `backend/research_analytics/`.
- Dataset quality or audit logic: `backend/src/quality/` and
  `backend/scripts/quality/`.
- Operational pipeline commands: root `Makefile`, `backend/Makefile`,
  `backend/docs/PIPELINE_RUNBOOK.md`.

## 15. Development Rules and Cautions

- Do not work directly on `main` for normal feature work.
- Create a branch per task and use clear commit messages.
- Do not commit secrets, `.env`, passwords, API keys, or large private datasets.
- Treat `backend/data/processed/` as generated output.
- Prefer adding new database migrations instead of changing old ones.
- Preserve the read-only nature of the backend public API unless intentionally
  working on admin endpoints.
- Remember that frontend local JSON storage is not production-safe for
  multi-instance deployments.
- Keep API route changes synchronized with frontend types and API client calls.
- Respect the AI-review and ownership gates when loading or publishing datasets.

## 16. Best Starting Docs

Read these when onboarding:

- `README.md` - root quick start.
- `backend/README.md` - backend setup, database, API, and docs index.
- `frontend/README.md` - frontend routes, roles, local state, and validation.
- `backend/docs/BACKEND_ARCHITECTURE_MAP.md` - backend package map and data flow.
- `backend/docs/PIPELINE_RUNBOOK.md` - operational pipeline commands.
- `backend/docs/API_DESIGN.md` - API contract and design.
- `backend/docs/SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md` - data pipeline
  architecture.
- `backend/docs/AI_RELEVANCE_PIPELINE.md` - AI relevance process.
- `docs/aws-ec2-app-deployment.md` - deployment.
- `docs/aws-monthly-automation.md` - scheduled data/model refresh.

## 17. One-Sentence Mental Model

ResearchLanka AI is a full-stack national research analytics system: Python
collects, cleans, validates, classifies, and serves Sri Lankan AI publication
data; PostgreSQL stores the verified corpus; Next.js lets users explore the
accepted records through dashboards, search, profiles, exports, and admin
review workflows.
