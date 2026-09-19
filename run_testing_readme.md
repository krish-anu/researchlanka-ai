# How to run tests (ResearchLanka)

Clear run guide for every structured test suite built so far: **Phase 1** (ETL), **Phase 2** (DB / ML / API), **Phase 3** (overall app: frontend, integration, performance, security, load, recovery), plus **frontend Vitest**.

---

## Prerequisites

```bash
# From repo root
source .venv/bin/activate          # or: source backend/.venv/bin/activate
cd backend
# Ensure pytest is available in that venv

# Frontend (for Vitest / Phase 3 frontend bridge)
cd ../frontend
npm install
```

Use `python` or `python3` depending on your environment. Examples below assume the project venv is active and you are in the directory named in each section.

---

## Quick index

| Suite | What it covers | Runner (from `backend/`) | Reports |
|---|---|---|---|
| **Phase 1** | Cleaning, preprocessing, transforms, dedup, disambiguation, entity resolution, e2e ingestion, Dagster, DB contract | `python scripts/testing/run_phase1_pipeline_tests.py` | `data/reports/phase1_pipeline_tests/` |
| **Phase 2** | DB integrity, classification, NMF, semantic search, API matrix | `python scripts/testing/run_phase2_ml_api_tests.py` | `data/reports/phase2_ml_api_tests/` |
| **Phase 3** | Frontend contracts, integration, performance, security, load, recovery, deploy config | `python scripts/testing/run_phase3_overall_tests.py` | `data/reports/phase3_overall_tests/` |
| **Frontend Vitest** | Auth, format, charts, Phase 3 frontend unit tests | `cd frontend && npm test` | Terminal only |

More detail: `backend/docs/phase1_etl_pipeline_testing.md`, `backend/docs/phase2_ml_api_testing.md`, `backend/docs/phase3_overall_testing.md`.

---

## Phase 1 — ETL / data integration

### Run

```bash
cd backend

# Gate suite only (recommended)
python scripts/testing/run_phase1_pipeline_tests.py
python scripts/testing/run_phase1_pipeline_tests.py -q

# Gate + related legacy regression files
python scripts/testing/run_phase1_pipeline_tests.py --include-legacy

# Custom report directory
python scripts/testing/run_phase1_pipeline_tests.py --report-dir data/reports/phase1_pipeline_tests
```

Or with pytest directly:

```bash
cd backend
pytest tests/phase1 --phase1-report -q
```

### Test files

| File | Focus |
|---|---|
| `tests/phase1/test_phase1_cleaning.py` | DOI / title / date / list cleaning |
| `tests/phase1/test_phase1_preprocessing.py` | Text preprocessing |
| `tests/phase1/test_phase1_transformations.py` | Field transforms / schema mapping |
| `tests/phase1/test_phase1_deduplication.py` | Duplicate detection |
| `tests/phase1/test_phase1_disambiguation.py` | Author disambiguation |
| `tests/phase1/test_phase1_entity_resolution.py` | Institution entity resolution |
| `tests/phase1/test_phase1_e2e_ingestion.py` | Collect → transform → validate → clean → resolve → dedupe → export |
| `tests/phase1/test_phase1_dagster.py` | Dagster job/asset smoke (may skip if Dagster missing) |
| `tests/phase1/test_phase1_database.py` | DB load / `publication_key` contract |

### Useful markers

```bash
pytest tests/phase1 -m cleaning -q
pytest tests/phase1 -m deduplication -q
pytest tests/phase1 -m e2e_ingestion -q
```

Markers: `phase1`, `cleaning`, `preprocessing`, `transforming`, `deduplication`, `disambiguation`, `entity_resolution`, `e2e_ingestion`, `dagster`, `database`, `edge_case`.

### Artifacts

Under `backend/data/reports/phase1_pipeline_tests/`:

- `latest_results.csv`
- `latest_report.md`
- `latest_summary.json`
- timestamped `phase1_etl_pipeline_*` copies

### Legacy included with `--include-legacy`

- `tests/test_author_disambiguation.py`
- `tests/test_institution_normalization.py`
- `tests/test_deduplication_thresholds.py`
- `tests/test_database_loader.py`
- `tests/test_normalize_doi.py`
- `tests/test_crossref_normalizer.py`
- `tests/test_build_final_common_dataset.py`
- `tests/test_kaggle_merge_common_dataset.py`
- `tests/test_research_analytics_framework.py`

---

## Phase 2 — Database integrity / ML / API

### Run

```bash
cd backend

python scripts/testing/run_phase2_ml_api_tests.py
python scripts/testing/run_phase2_ml_api_tests.py -q
python scripts/testing/run_phase2_ml_api_tests.py --include-legacy
python scripts/testing/run_phase2_ml_api_tests.py --report-dir data/reports/phase2_ml_api_tests
```

Or:

```bash
cd backend
pytest tests/phase2 --phase2-report -q
```

### Test files

| File | Focus |
|---|---|
| `tests/phase2/test_phase2_database_integrity.py` | Schema / columns / `publication_key` / row builder |
| `tests/phase2/test_phase2_classification.py` | Hierarchical classification contracts |
| `tests/phase2/test_phase2_nmf.py` | NMF k=25 topic modeling / trends |
| `tests/phase2/test_phase2_semantic_search.py` | Embeddings / semantic / related search |
| `tests/phase2/test_phase2_api_matrix.py` | Fixed API cases **API-001…API-026** |

Helpers: `tests/phase2/helpers.py` (`attach_api_case`, payload asserts).

### API matrix

Columns: **Test ID | Endpoint | Scenario | Expected | Result**

Written to:

- `latest_api_matrix.md`
- `latest_api_matrix.csv`

### Useful markers

```bash
pytest tests/phase2 -m database_integrity -q
pytest tests/phase2 -m classification -q
pytest tests/phase2 -m nmf_topic_modeling -q
pytest tests/phase2 -m semantic_search -q
pytest tests/phase2 -m api_matrix -q
```

Markers: `phase2`, `database_integrity`, `classification`, `nmf_topic_modeling`, `semantic_search`, `api`, `api_matrix`.

### Artifacts

Under `backend/data/reports/phase2_ml_api_tests/`:

- `latest_results.csv` / `latest_report.md` / `latest_summary.json`
- `latest_api_matrix.md` / `latest_api_matrix.csv`
- timestamped `phase2_ml_api_*` copies

### Legacy included with `--include-legacy`

- `tests/test_database_loader.py`
- `tests/test_hierarchical_linear_svm.py`
- `tests/test_classification_model_comparison.py`
- `tests/test_nmf_topic_endpoints.py`
- `tests/test_publication_text_embeddings.py`
- `tests/test_api_service.py`
- `tests/test_model_fastapi_endpoints.py`

---

## Phase 3 — Overall application

Covers frontend contracts, integration smoke, performance budgets, security (SQL injection, invalid params, data/secret exposure, HTTPS boundary, API access), load, recovery, accessibility, and deploy config.

### Run

```bash
cd backend

# Phase 3 pytest suite (includes Vitest bridge inside frontend tests unless skipped)
python scripts/testing/run_phase3_overall_tests.py
python scripts/testing/run_phase3_overall_tests.py -q

# Also run a second full `npm test` pass from the runner
python scripts/testing/run_phase3_overall_tests.py --with-frontend

# Skip the Vitest subprocess inside pytest (static frontend checks still run)
PHASE3_SKIP_VITEST=1 python scripts/testing/run_phase3_overall_tests.py -q

python scripts/testing/run_phase3_overall_tests.py --report-dir data/reports/phase3_overall_tests
```

Or:

```bash
cd backend
pytest tests/phase3 --phase3-report -q
```

### Test files

| File | Focus |
|---|---|
| `tests/phase3/test_phase3_security.py` | Security matrix **SEC-001…**, SQLi binding, exposure, secrets, HTTPS/API access |
| `tests/phase3/test_phase3_integration.py` | Health → meta → search → detail → export smoke |
| `tests/phase3/test_phase3_performance.py` | Latency budgets on hot reads |
| `tests/phase3/test_phase3_load.py` | Concurrent read / export pressure |
| `tests/phase3/test_phase3_recovery.py` | DB failure, corrupt incremental status, unknown routes |
| `tests/phase3/test_phase3_frontend.py` | Frontend contracts + Vitest bridge |
| `tests/phase3/test_phase3_deploy_accessibility.py` | Compose isolation / healthchecks / error contract / login+forbidden routes |

Helpers: `tests/phase3/helpers.py` (`FakeRepository`, `attach_security_case`, secret-leak asserts).

### Security matrix

Columns: **Test ID | Endpoint | Scenario | Expected | Result**

Written to:

- `latest_security_matrix.md`
- `latest_security_matrix.csv`

### Useful markers

```bash
pytest tests/phase3 -m security -q
pytest tests/phase3 -m integration -q
pytest tests/phase3 -m performance -q
pytest tests/phase3 -m load -q
pytest tests/phase3 -m recovery -q
pytest tests/phase3 -m frontend -q
pytest tests/phase3 -m deploy_config -q
pytest tests/phase3 -m accessibility -q
```

Markers: `phase3`, `frontend`, `integration`, `performance`, `security`, `load`, `recovery`, `accessibility`, `deploy_config`.

### Artifacts

Under `backend/data/reports/phase3_overall_tests/`:

- `latest_results.csv` / `latest_report.md` / `latest_summary.json`
- `latest_security_matrix.md` / `latest_security_matrix.csv`
- timestamped `phase3_overall_*` copies

---

## Frontend Vitest (unit / component)

### Run

```bash
cd frontend
npm test                 # vitest run (CI-style once)
npm run test:watch       # watch mode
npm run test:coverage    # coverage
```

Related frontend checks (not Vitest):

```bash
cd frontend
npm run typecheck
npm run check:palette
npm run lint
```

### Test files

| File | Focus |
|---|---|
| `src/services/auth/password.test.ts` | Password hashing |
| `src/services/auth/session.test.ts` | Session cookie / HMAC |
| `src/services/auth/permissions.test.ts` | Role capabilities |
| `src/services/auth/store.test.ts` | Account store |
| `src/services/format.test.ts` | Formatting helpers |
| `src/services/links.test.ts` | URL builders |
| `src/services/overall.phase3.test.ts` | Query encoding, ApiResult helpers, cookie Secure flags, admin capability |
| `src/app/overall.middleware.phase3.test.ts` | Middleware matcher for `/account` and `/admin` |
| `src/components/charts/PlotlyChart.dom.test.tsx` | Chart shell (jsdom) |
| `src/components/network/NetworkMetrics.dom.test.tsx` | Network metrics (jsdom) |

---

## Run everything (recommended order)

```bash
# 1) Backend Phase gates
cd backend
python scripts/testing/run_phase1_pipeline_tests.py -q
python scripts/testing/run_phase2_ml_api_tests.py -q
python scripts/testing/run_phase3_overall_tests.py -q

# 2) Frontend unit tests (if not already covered via Phase 3 bridge)
cd ../frontend
npm test
```

Optional full regression walls:

```bash
cd backend
python scripts/testing/run_phase1_pipeline_tests.py --include-legacy -q
python scripts/testing/run_phase2_ml_api_tests.py --include-legacy -q
python scripts/testing/run_phase3_overall_tests.py --with-frontend -q
```

Root convenience (broader repo check, not the Phase runners):

```bash
# From repo root — backend pytest + frontend typecheck/palette (see Makefile)
make check
# or
make test
```

Note: `make check` / `make test` are the general project checks. They are **not** the same as the Phase 1/2/3 report runners above. Prefer the `scripts/testing/run_phase*_*.py` commands when you need the structured CSV/MD/JSON reports and matrices.

---

## Pytest reporting options (shared)

Configured in `backend/tests/conftest.py` and `backend/pytest.ini`:

| Flag | Effect |
|---|---|
| `--phase1-report` | Write Phase 1 report for the session |
| `--phase1-report-dir=PATH` | Phase 1 output directory |
| `--phase2-report` | Write Phase 2 report + API matrix |
| `--phase2-report-dir=PATH` | Phase 2 output directory |
| `--phase3-report` | Write Phase 3 report + security matrix |
| `--phase3-report-dir=PATH` | Phase 3 output directory |

Reports also auto-write when you only collect tests under `tests/phase1`, `tests/phase2`, or `tests/phase3`.

---

## Where reports land

```
backend/data/reports/
  phase1_pipeline_tests/
    latest_report.md
    latest_results.csv
    latest_summary.json
  phase2_ml_api_tests/
    latest_report.md
    latest_results.csv
    latest_summary.json
    latest_api_matrix.md
    latest_api_matrix.csv
  phase3_overall_tests/
    latest_report.md
    latest_results.csv
    latest_summary.json
    latest_security_matrix.md
    latest_security_matrix.csv
```

Pass criteria for each phase: `pass_rate_pct == 100` in that phase’s `latest_summary.json` (intentional skips such as missing Dagster or `PHASE3_SKIP_VITEST=1` may appear as skipped, not failed).

---

## Troubleshooting

| Issue | What to do |
|---|---|
| `python: command not found` | Use `python3` or activate `.venv` |
| `No module named pytest` | Activate project venv; install backend deps |
| Phase 3 Vitest fails in sandbox / no npm | Run `cd frontend && npm test` separately, or `PHASE3_SKIP_VITEST=1` for backend-only Phase 3 |
| Dagster tests skipped | Install Dagster in the env, or accept skip for smoke |
| Wrong working directory | Phase runners expect **`backend/`** as cwd; frontend tests expect **`frontend/`** |
