# Backend Architecture Map

Orientation for anyone reading this backend for the first time: what each
package is for, how data moves through it, and which file to open for a given
task.

This is the *code* map. For the data-quality reasoning behind the cleaning
decisions see [00_metadata_quality_report_index.md](00_metadata_quality_report_index.md);
for step-by-step operational commands see [PIPELINE_RUNBOOK.md](PIPELINE_RUNBOOK.md).

---

## 1. The one thing to understand first

There are **two parallel implementations** of the same idea, and most confusion
about this repository comes from not knowing which one you are looking at.

| | `research_analytics/` | `src/` |
|---|---|---|
| Role | The **reusable, config-driven national framework** | The **concrete Sri Lanka pipeline**, scripts, API, and models |
| Driven by | `configurations/sri_lanka/config.json` | CLI flags and hardcoded default paths |
| Entry point | `research_analytics.cli` / `run_pipeline.py` | `python -m src.pipeline.<stage>` and `scripts/` |
| Reusable for another country? | Yes, that is the point | No, Sri Lanka specific |
| Status | The intended destination | Where most working code still lives |

Both are live. `docs/MIGRATION_TO_RESEARCH_ANALYTICS_PIPELINE.md` records the
intent to converge on `research_analytics/`; until then, expect some logic
(deduplication, institution handling, venue standardization) to exist in both
places with different code.

> The two entry points also expose **different stage names** — see
> [BACKEND_CODE_AUDIT.md §2.6](BACKEND_CODE_AUDIT.md#26-two-different-stage-vocabularies).

---

## 2. Data flow

```
  EXTERNAL SOURCES
  OAI-PMH  ·  DSpace REST  ·  OpenAlex  ·  Crossref  ·  SLJOL  ·  HTML meta  ·  sitemaps
        |
        |  src/collectors/          network access, pagination, retry
        v
  data/raw/<institution>/*.jsonl              raw payloads, never edited
        |
        |  src/preprocessing/        per-source field flattening
        |  src/processing/           JSONL -> CSV, map to common schema
        v
  data/processed/<source>/*.csv
        |
        |  src/pipeline/kaggle_merge_common_dataset.py
        |    merges all sources, dedupes, writes the 76-column COMMON_COLUMNS schema
        v
  common_publications_all_records.csv      (76 cols, every record)
  common_publications_deduplicated.csv     (76 cols, deduplicated)
        |
        |  build_final_common_dataset.py
        v
  common_publications_final.csv            <-- the hub; three branches leave here
        |
        +--> build_columns_filtered_dataset.py --> common_publications_columns_filtered.csv
        |
        +--> build_institution_normalized_dataset.py
        |         --> ..._institution_normalized.csv
        |               |
        |               +--> build_type_journal_normalized_dataset.py --> ..._type_journal_normalized.csv
        |               +--> build_author_disambiguated_dataset.py    --> ..._author_disambiguated.csv
        |
        +--> build_year_filtered_dataset.py --> common_publications_final_2016_2026.csv
                  |
                  v  build_language_normalized_dataset.py
             ..._2016_2026_language_normalized.csv
                  |
                  v  build_multivalue_normalized_dataset.py
             ..._2016_2026_multivalue_normalized.csv
                  |
                  v  build_analysis_ready_dataset.py
             ..._2016_2026_analysis_ready.csv        <-- input for model training
        |
        |  src/database/loader.py  ·  scripts/database/load_records.py
        v
  PostgreSQL  final_publications
        |
        |  src/api/
        v
  HTTP JSON API  (consumed by frontend/)
```

Everything under `data/processed/` is a **generated artifact**. Never hand-edit
it; re-run the stage that produces it.

### Schema stages — three different "common schemas"

A frequent source of bugs. These are all legitimately different:

| Schema | Columns | Defined in | Applies to |
|---|---|---|---|
| `COMMON_COLUMNS` | 76 | `src/pipeline/kaggle_merge_common_dataset.py` | `all_records`, `deduplicated` |
| `FINAL_MAIN_COLUMNS` | 58 | `src/pipeline/build_final_common_dataset.py` | `common_publications_final.csv` |
| `BASE_COLUMNS` | 62 | `src/api/repositories/sql.py` | the `final_publications` table |

Validating a downstream file against `COMMON_COLUMNS` will always fail — later
stages drop columns on purpose. When a script needs to check its input, it
should require only the columns it actually reads (`load_dataset(...,
required_columns=[...])`).

> `FINAL_MAIN_COLUMNS` and the committed `common_publications_final.csv`
> currently disagree, which breaks one stage —
> [BACKEND_CODE_AUDIT.md §2.1](BACKEND_CODE_AUDIT.md#21-the-committed-final-dataset-is-stale-one-pipeline-stage-cannot-run).

---

## 3. Package reference

### `src/collectors/` — talking to the outside world

Every collector keeps network access separate from CLI orchestration and
follows one shape:

- `fetch_*()` — request exactly one API resource or page
- `iter_*()` — handle pagination, yield records
- `total_*()` — only when the source exposes a reliable count

| File | Source |
|---|---|
| `oai_pmh_collector.py` | OAI-PMH repositories (most university repositories) |
| `dspace_rest_collector.py` | DSpace REST, where OAI-PMH is incomplete |
| `openalex_collector.py` | OpenAlex works API |
| `crossref_collector.py` | Crossref by affiliation, by DOI, and by DOI prefix |
| `html_meta_collector.py` | Scraping `<meta>` tags where no API exists |
| `sitemap_collector.py` | Sitemap URL discovery |
| `http.py` | Shared retry/session behaviour — **all** collectors use this |
| `repository_registry.py` | Which institution uses which harvest method |
| `schema_mapping.py` | Source field -> common schema field |

### `src/preprocessing/` and `src/processing/` — raw to tabular

`preprocessing/` flattens one source's nested payload into the stable field set
(`crossref_normalizer.py`, `openalex_normalizer.py`). `processing/` converts
JSONL to CSV and maps onto the common schema.

### `src/pipeline/` — the ordered dataset stages

The `build_*.py` modules are the numbered steps in the diagram above; the
`harvest_*.py` and `collect_*.py` modules drive collectors for a whole run.
Each is runnable standalone:

```bash
python -m src.pipeline.build_institution_normalized_dataset
```

Every stage takes `--input-csv` / `--output-csv` and defaults to the canonical
path, so stages chain without arguments.

### `src/database/` — PostgreSQL

| File | Purpose |
|---|---|
| `connection.py` | `DATABASE_URL` handling, connection factory |
| `apply_database_migrations.py` | Applies `database/migrations/*.sql` in order |
| `verify_database_schema.py` | Asserts the live schema matches expectations |
| `final_schema.py` | The `final_publications` table definition |
| `loader.py` / `load_records.py` | Batch load with `--year-min` / `--year-max` |
| `check_database_connection.py` | First thing to run when something looks wrong |

Migrations live in `database/migrations/` and are numbered; never edit an
applied migration, add a new one.

### `src/api/` — the read-only HTTP API

The most heavily layered package, and the layering is deliberate:

```
transport/   http_server.py (stdlib)  ·  fastapi_app.py (FastAPI)
routing/     routes.py — path dispatch for the stdlib server
services/    publications.py — the actual query/response logic
repositories/ postgres.py, sql.py, aggregates.py — SQL construction
core/        query.py, serializers.py, exports.py, errors.py, protocols.py, constants.py
```

**Two transports serve the same service layer.** The stdlib server
(`scripts/api/serve_api.py`, port 8080) is dependency-free; the FastAPI app
(port 8081) adds the model-prediction endpoints and OpenAPI docs, and currently
exposes strictly more routes.

> **Compatibility shims.** `src/api/constants.py`, `errors.py`, `exports.py`,
> `protocols.py`, `query.py`, `serializers.py`, `aggregates.py`,
> `repository.py`, `routes.py`, `fastapi_app.py`, and `server.py` are each a
> few lines that re-export from the subpackage that now owns the code. They are
> **intentional**, kept so older imports keep working. Add new code to the
> subpackage (`core/`, `routing/`, …), never to the shim.

SQL safety: user input is always parameterized; identifiers come from fixed
dicts and pass through `quote_identifier`; sort keys are dict lookups with a
safe fallback.

### `src/modeling/` — classification and embeddings

| File | Purpose |
|---|---|
| `training.py` | TF-IDF + classifier training entry point |
| `hierarchical_linear_svm.py`, `linear_svm_training.py` | Linear SVM variants |
| `classification_comparison.py` | Trains and ranks several model families |
| `embeddings.py` | TF-IDF + TruncatedSVD dense vectors |
| `dataset_splits.py` | Stratified 70/15/15 train/validation/test |
| `inference.py` | Loads a saved model, verifies it, predicts |
| `artifacts.py` | Atomic, checksummed artifact saving |

`artifacts.py` is worth reading before touching this package: every artifact is
written to a temp file, fsynced, atomically replaced, and recorded in a
manifest with byte size and SHA-256. Inference **verifies the checksum** before
using a model, so a partially-written model can never be silently used.

### `src/quality/` — validation and manual review

Harvest validators, DOI and publication-count comparisons, false-duplicate and
missed-duplicate analyses, and the ambiguous-author review queue
(`review_ambiguous_authors.py`, driven by `make author-review` /
`make author-decisions`).

### `src/utils/` — small shared helpers

`column_resolve.py` holds the shared "pick the first populated column from a
priority list, and record which one it was" logic; the `*_utils.py` modules
apply it per concept. `io_utils.py` provides `load_dataset` / `save_dataset`
for the lightweight extraction scripts. Also `doi.py` (DOI normalization)
and `file_naming.py`.

> These extractors are currently **not wired into the pipeline** and their
> priority lists contradict their docstrings —
> [BACKEND_CODE_AUDIT.md §2.2–2.3](BACKEND_CODE_AUDIT.md#22-column-priority-lists-contradict-their-own-docstrings).

### `src/analytics/` — `network.py`, co-authorship and collaboration graphs.

### `research_analytics/` — the reusable framework

Config-driven and country-agnostic. `adapters/` wrap each source behind a
common `connect`/`collect`/`transform` interface (`registry.py` maps a config
name to an adapter); `pipeline.py` runs the stages; `config.py` loads the
national configuration. The remaining modules mirror pipeline concerns —
`cleaning`, `deduplication`, `institutions`, `authors`, `venues`, `validation`,
`analytics`, `networks`, `exporters`, `schema`.

Every module here already carries a module docstring; start with `pipeline.py`.

---

## 4. Where things live

| Path | Contents |
|---|---|
| `configurations/sri_lanka/` | `config.json`, institution registry, author decisions |
| `data/raw/` | Untouched harvested payloads |
| `data/processed/` | Generated datasets — never hand-edit |
| `data/models/` | Trained models, manifests, metrics |
| `data/reports/` | Timestamped validation and coverage reports |
| `database/migrations/` | Numbered SQL migrations |
| `docs/` | This map, the audit, quality analyses, runbooks |
| `notebooks/` | Exploratory analysis (not part of the pipeline) |
| `plugins/example_repository/` | Template for adding a new source |
| `dagster-quickstart/` | Separate Dagster orchestration experiment |

---

## 5. Common tasks

| Task | Start here |
|---|---|
| Add a new institution/repository | `src/collectors/repository_registry.py`, then `plugins/example_repository/` |
| Add a new data source | `research_analytics/adapters/` + `registry.py` |
| Change a cleaning rule | `src/pipeline/build_*.py`, and record it in `docs/10_data_cleaning_rules.md` |
| Add an API endpoint | `src/api/services/publications.py`, then both transports |
| Change the database schema | New file in `database/migrations/`, update `final_schema.py` and `BASE_COLUMNS` |
| Train a different classifier | `make train-logreg` with `LOGREG_*` overrides |
| Debug a failing pipeline stage | Check the input CSV's columns first — see §2 |

Run `make help` for the full target list, and `pytest` from `backend/` for the
suite (476 tests, ~30s).

---

## 6. Conventions

- **Never edit `data/processed/`** — regenerate it.
- **Never edit an applied migration** — add a new one.
- **Collectors do not orchestrate**; `scripts/` and `src/pipeline/` do.
- **Add to the subpackage, not the `src/api/` shim.**
- Stages take `--input-csv` / `--output-csv` with canonical defaults.
- Model artifacts are atomic and checksummed; keep it that way.
- Imports inside `src/` are absolute from the backend root (`from src.utils...`).
  A bare `from utils...` will not resolve — this has broken six modules before.
