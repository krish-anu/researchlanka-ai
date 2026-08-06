# Pipeline Runbook

Every command, in order, from a clean checkout to a loaded database.

All commands run from the repository root.

**Two paths through this document:**

- **Rebuilding the dataset** from the CSVs already in `data/raw/Datasets/Final Datasets/` — run §0, then §3 → §6. This is what most people need.
- **Refreshing source data** from the live APIs and repositories — run §0 → §7 in full. Takes hours and hits external services.

`scripts/**/*.py` files are thin shims. `python scripts/collection/harvest_oai.py ARGS` and
`python -m src.pipeline.harvest_oai ARGS` are exactly equivalent. Three newer stages have **no shim** and are `python -m` only: `build_institution_registry`, `build_institution_normalized_dataset`, `build_type_journal_normalized_dataset`.

---

## 0. Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python >= 3.11.

```bash
cp .env.example .env               # then edit DATABASE_URL
docker compose up -d db            # postgres:16 on host port 5433
python scripts/database/check_database_connection.py
```

Optional environment variables read by the collectors:

```bash
export CROSSREF_EMAIL=you@example.com     # Crossref polite pool
export OPENALEX_API_KEY=...               # optional
export OPENALEX_OUTPUT_DIR=...            # overrides the OpenAlex output directory
```

```bash
python -m pytest                   # 251 tests, all offline
```

---

## 1. Collect

> Only when refreshing source data. Skip to §3 to rebuild from existing CSVs.

### 1.1 OpenAlex

```bash
make openalex-sample PYTHON=python        # 1,000 records, validates setup first
make openalex PYTHON=python               # full collection
make openalex-resume PYTHON=python        # continue after an interruption
```

Writes to `data/raw/openalex/`: `openalex_sri_lanka_works.{jsonl,csv,parquet}`,
`openalex_sri_lanka_doi_conflicts.csv`, `openalex_sri_lanka_pagination_audit.json`,
`openalex_sri_lanka_works.jsonl.progress.json`, `openalex_collection.log`.

Without `make`:

```bash
python scripts/collection/kaggle_collect_openalex_sri_lanka.py \
  --from-year 2016 --to-year 2026 --per-page 200 \
  --log-level INFO --log-file data/raw/openalex/openalex_collection.log
```

Rebuild derived outputs from raw JSONL without re-calling the API:

```bash
make openalex-rebuild PYTHON=python
make openalex-report PYTHON=python
make openalex-doi-conflicts PYTHON=python
```

### 1.2 Crossref

```bash
python scripts/collection/collect_crossref.py inspect --limit 3
python scripts/collection/collect_crossref.py collect-lk \
  --from-year 2016 --until-year 2026 --rows 100 --email you@example.com
```

Output: `data/processed/crossref/crossref_sri_lanka_works.jsonl`

DOI-based enrichment (`--doi-file` is required):

```bash
python scripts/collection/collect_crossref.py enrich-dois \
  --doi-file data/processed/doi_comparison/doi_comparison_openalex_only_dois.txt \
  --email you@example.com
```

Output: `data/processed/crossref/crossref_sri_lanka_works_doi_enriched.jsonl` (append mode, skips DOIs already present)

Convert to CSV — **must be run from the repo root**, this script uses a relative default path:

```bash
python scripts/processing/jsonl_to_csv.py --chunksize 10000
```

### 1.3 SLJOL

SLJOL is collected through Crossref DOI prefix `10.4038`, not by crawling sljol.info.

```bash
python scripts/collection/collect_sljol.py --email you@example.com --rows 500
```

Output: `data/raw/sljol/crossref_works.jsonl` (~26,200 records)

### 1.4 University repositories

Check which targets are harvestable and which phase they belong to:

```bash
python scripts/collection/harvest_oai.py --list
```

17 harvestable ids: `uom cmb pdn jfn_research jfn_medicine seu ou vpa rjt busl sltc` (phase_2) and `ruh esn uwu vau nsf sliit` (phase_1).

**OAI-PMH — all targets:**

```bash
python scripts/collection/harvest_all.py --max-records-per-target 0
```

`0` means no cap. The default is 2,000 per institution. Writes `data/raw/<id>/oai_dc.jsonl` and `data/reports/harvest_summary_<timestamp>.json`.

**DSpace REST** — for the five institutions whose `harvest_route` is `rest`:

```bash
for id in cmb pdn busl uwu nsf; do
  python scripts/collection/harvest_dspace_rest.py --id "$id" --page-size 100
done
```

Writes `data/raw/<id>/rest_items.jsonl`.

**HTML meta crawl** — for the two Jaffna repositories (slow, 0.5s between requests):

```bash
python scripts/collection/harvest_html_meta.py --id jfn_research
python scripts/collection/harvest_html_meta.py --id jfn_medicine
```

Writes `data/raw/<id>/html_meta.jsonl`.

**Date-bisection rescue** — only for `ruh` and `cmb`, which hit a DSpace pagination bug (HTTP 500) that plain OAI cannot get past:

```bash
python scripts/collection/harvest_large_repository.py --id ruh --start-year 1990
```

Writes the same `data/raw/<id>/oai_dc.jsonl`. Do not run it alongside `harvest_oai.py` for the same id.

**Single OAI target**, if you only need one:

```bash
python scripts/collection/harvest_oai.py --id sltc
python scripts/collection/harvest_oai.py --id seu --from 2020-01-01 --until 2026-12-31
```

**Sitemap discovery** (diagnostic only — finds URLs, extracts no metadata):

```bash
python scripts/collection/discover_sitemap.py --id uom
```

---

## 2. Map to the common schema

> Only when refreshing source data.

```bash
python scripts/processing/map_to_common_schema.py --all
python scripts/processing/convert_repositories_jsonl_to_csv.py
```

The first command reads, per institution, whichever raw route file has the **most lines** — `oai_dc.jsonl`, `rest_items.jsonl`, `html_meta.jsonl` or `crossref_works.jsonl` — and writes `data/processed/repositories/<id>.jsonl`. Routes are never merged.

The second combines those into `data/processed/repositories_combined.csv`.

---

## 3. Merge into one dataset

Requires these four files, found recursively under `--input-dir`:

```
crossref_clean_2016_2026_enriched.csv or crossref_sri_lanka_works.csv
openalex_sri_lanka_works.csv
repositories_combined.csv
sljol.csv
```

```bash
python scripts/processing/kaggle_merge_common_dataset.py \
  --input-dir data \
  --output-dir data/processed/common
```

Quick test on a subset first:

```bash
python scripts/processing/kaggle_merge_common_dataset.py --sample-rows 5000
```

Optional field-level source priority override (defaults documented in [normalization_and_merge.md](normalization_and_merge.md)):

```bash
python scripts/processing/kaggle_merge_common_dataset.py --field-source-policy policy.json
```

Writes 7 files to `data/processed/common/`: `common_publications_all_records.csv`,
`common_publications_deduplicated.csv`, `common_publications_merge_log.csv`,
`common_publications_manual_review_candidates.csv`, `common_publications_schema.csv`,
`common_publications_summary.csv`, `common_publications_run_log.txt`.

**Optional** — adjudicate the 2,344 manual-review candidate groups in a browser at `http://127.0.0.1:8765`:

```bash
python scripts/quality/manual_review_ui.py
```

Optional duplicate-quality analysis:

```bash
python scripts/quality/analyze_false_duplicate_matches.py
python scripts/quality/analyze_missed_duplicate_records.py
```

Outputs are written to `data/processed/common/duplicate_match_analysis/` and
`data/processed/common/missed_duplicate_analysis/`.

---

## 4. Build chain

Run in this order. Each step reads the previous step's output.

```bash
python scripts/processing/build_final_common_dataset.py
python scripts/processing/build_year_filtered_dataset.py --start-year 2016 --end-year 2026
python scripts/processing/build_language_normalized_dataset.py
python scripts/processing/build_multivalue_normalized_dataset.py
python scripts/processing/build_analysis_ready_dataset.py
```

Optional, and **not** part of the chain — its output feeds nothing:

```bash
python scripts/processing/build_columns_filtered_dataset.py
```

Optional model-ready text and TF-IDF exports from `common_publications_final.csv`:

```bash
make model-text PYTHON=python
```

This writes title, abstract, keyword, and compact TF-IDF feature CSVs to
`data/processed/common/`:

- `publication_titles_for_model_all_years.csv`
- `publication_abstracts_for_model_all_years.csv`
- `publication_keywords_for_model_all_years.csv`
- `publication_tfidf_features_all_years.csv`
- `publication_tfidf_vocabulary_all_years.csv`
- `publication_tfidf_summary_all_years.csv`

To rebuild only TF-IDF features:

```bash
make model-tfidf PYTHON=python
```

Tune vocabulary and row width with `MODEL_TFIDF_MAX_FEATURES`,
`MODEL_TFIDF_MIN_DF`, `MODEL_TFIDF_MAX_DF`, `MODEL_TFIDF_NGRAM_MAX`, and
`MODEL_TFIDF_TOP_FEATURES_PER_RECORD`.

Train a TF-IDF + Logistic Regression classifier from publication text:

```bash
make train-logreg PYTHON=python
```

By default this predicts `primary_domain` from `title`, `abstract`, and
`keywords`, then writes reusable training artifacts to `data/models/`:

- `logistic_regression_<label>.joblib` - fitted scikit-learn pipeline
- `logistic_regression_<label>_metrics.txt` - accuracy, F1, class distribution, and classification report
- `logistic_regression_<label>_labels.csv` - label counts after filtering small classes
- `logistic_regression_<label>_predictions.csv` - held-out predictions for review
- `logistic_regression_<label>_manifest.json` - run configuration, metrics, and artifact paths

Use `LOGREG_LABEL_COLUMN=primary_field` or `LOGREG_LABEL_COLUMN=type` to train a
different target. Tune the reusable pipeline with `LOGREG_TEXT_COLUMNS`,
`LOGREG_MIN_CLASS_COUNT`, `LOGREG_TEST_SIZE`, `LOGREG_MAX_FEATURES`,
`LOGREG_MIN_DF`, `LOGREG_MAX_DF`, `LOGREG_NGRAM_MAX`, `LOGREG_MAX_ITER`, and
`LOGREG_EXTRA_ARGS`.

| Step | Input | Main output |
|---|---|---|
| `build_final_common_dataset` | `common_publications_deduplicated.csv` | `common_publications_final.csv` + `publication_references.csv` + `publication_count_audit.csv` |
| `build_year_filtered_dataset` | `common_publications_final.csv` | `common_publications_final_2016_2026.csv` |
| `build_language_normalized_dataset` | `..._2016_2026.csv` | `..._2016_2026_language_normalized.csv` |
| `build_multivalue_normalized_dataset` | `..._language_normalized.csv` | `..._multivalue_normalized.csv` + `publication_multivalue_items_2016_2026.csv` |
| `build_analysis_ready_dataset` | `..._multivalue_normalized.csv` | `..._analysis_ready.csv` + `preprocessing_issues_2016_2026/` |

---

## 5. Normalize institutions, countries, types and venues

```bash
make institution-registry PYTHON=python
# review the diff to configurations/sri_lanka/institutions.csv, then:
make institution-normalize PYTHON=python
make type-journal-normalize PYTHON=python
```

Without `make`:

```bash
python -m src.pipeline.build_institution_registry
python -m src.pipeline.build_institution_normalized_dataset
python -m src.pipeline.build_type_journal_normalized_dataset
```

`build_institution_registry` **rewrites** `configurations/sri_lanka/institutions.csv`. It preserves existing `LK###` identifiers, but read the diff before committing — it also prints institution pairs whose names nest inside one another for manual review.

Details: [10_institution_and_affiliation_standardization.md](10_institution_and_affiliation_standardization.md) and [11_publication_type_and_venue_standardization.md](11_publication_type_and_venue_standardization.md).

---

## 6. Database

```bash
docker compose up -d db
python scripts/database/check_database_connection.py
python scripts/database/apply_database_migrations.py
python scripts/database/verify_database_schema.py
```

Load records:

```bash
python scripts/database/load_records.py \
  data/processed/common/common_publications_final_type_journal_normalized.csv
```

Smoke test with 25 records first:

```bash
python scripts/database/load_records.py \
  data/processed/common/common_publications_final.csv --limit 25
```

Accepts CSV, JSON and JSONL; format is inferred from the extension. `--batch-size` defaults to 1000. Upserts on `publication_key`, so re-running is safe.

Shut down:

```bash
docker compose down
```

---

## 7. Validation and quality checks

```bash
python scripts/quality/validate_repositories.py                 # endpoint health, all harvestable targets
python scripts/quality/validate_repositories.py --ids kln,pgim  # force-check blocked targets
python scripts/quality/validate_harvested_data.py               # coverage per institution (takes no arguments)
python scripts/quality/compare_dois.py                          # OpenAlex vs Crossref DOI overlap (takes no arguments)
make publication-counts PYTHON=python                           # per-source record counts
```

Reports land in `data/reports/` with a UTC timestamp in the filename.

Column profiling:

```bash
python scripts/analysis/columns/analyze_first_25_columns.py --report-dir data/reports/column_analysis
python scripts/analysis/columns/analyze_second_25_columns.py --report-dir data/reports/column_analysis
python scripts/analysis/columns/analyze_final_26_columns.py --report-dir data/reports/column_analysis
```

Without `--report-dir` these print to stdout and write nothing.

---

## Framework CLI (alternative path)

The config-driven framework runs its own pipeline over a single configured source. It does **not** replace §3–§5.

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

Subcommands: `source-validate`, `preview`, `validate`, `import`, `clean`, `deduplicate`, `analyze`, `load_database`, `run-all`. Note `load_database` uses an underscore while `source-validate` and `run-all` use hyphens. All take `--config` (required), `--sample-size`, `--log-level`.

Single stage:

```bash
python run_pipeline.py --config configurations/sri_lanka/config.json --stage deduplicate
```

Stages: `collect transform validate clean resolve_entities deduplicate analyze load_database export all`.

---

## Expected counts

Check your run against these. From `data/processed/common/common_publications_run_log.txt` (2026-07-27).

| Stage | Result |
|---|---|
| Crossref input | 65,946 rows |
| OpenAlex input | 73,289 rows |
| Repositories input | 111,633 rows |
| SLJOL input | 26,200 rows |
| All normalized records | **277,068** |
| After deduplication | **170,365** (106,703 removed) |
| Manual-review groups | 2,344 (4,940 records) |
| Reference rows | 1,808,219 |
| Institution coverage after §5 | 43.0% → 90.1% |
| Publication types after §5 | 97 → 27 |

Repository collection totals 126,440 records from 12 institutions plus SLJOL. Per-institution figures are in [DATA_COLLECTION.md](DATA_COLLECTION.md).

---

## Gotchas

Things that break a literal run.

1. **`make` uses `.venv/bin/python`**, a POSIX path. On Windows add `PYTHON=python` to every make command: `make institution-normalize PYTHON=python`.

2. **`make framework-sri-lanka` does not exist**, despite `README.md:163`. Use
   `python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json`.

3. **The merge finds its inputs by exact filename.** A renamed file is silently not found rather than reported as an error. All four names are listed in §3.

4. **`kaggle_merge_common_dataset.py` has no `--summary` flag.** Only `--input-dir`, `--output-dir`, `--include-raw-json`, `--sample-rows`, `--field-source-policy`. The summary CSV is always written.

5. **The OpenAlex `--filter` flag appends, it does not replace.** The default is
   `authorships.institutions.country_code:LK`, so `--filter X` sends *both* filters. To use a different filter, edit `LK_AUTHORSHIP_FILTER` in `src/collectors/openalex_collector.py`.

6. **The OpenAlex collector uses `parse_known_args()`** — a mistyped flag is silently ignored instead of raising an error. Check spelling.

7. **`jsonl_to_csv.py` uses a relative default path** (`data/processed/crossref`), unlike every other script. Run it from the repo root.

8. **The Crossref enrichment subcommand is `enrich-dois`**, not `enrich`. `--doi-file` is required and has no default.

9. **Never run two harvesters against the same institution at once.** `harvest_oai.py` and `harvest_large_repository.py` both write `data/raw/<id>/oai_dc.jsonl`.

10. **`harvest_all.py` writes `oai_dc.jsonl` for every harvestable target**, including the REST and HTML ones. Harmless — `map_to_common_schema.py` picks whichever route file has the most lines — but it is why those directories hold two raw files.

11. **`build_columns_filtered_dataset.py` is a dead end.** Nothing reads its output. The chain in §4 skips it deliberately.

12. **`sliit` fails TLS verification** and the registry disables verification for it. A certificate warning for that host is expected, not a failure.

13. **`README.md` points `load_records.py` at `final_common_dataset.csv`, which does not exist.** Use `common_publications_final.csv` or the type/journal-normalized output, as in §6.

14. **OpenAlex output paths change with the environment**: `$OPENALEX_OUTPUT_DIR`, else `/kaggle/working` if it exists and is writable, else `data/raw/openalex`. On Kaggle the defaults shift silently. The `make` targets pin all paths explicitly.

15. **`harvest_large_repository.py` helps only `ruh` and `cmb`.** It made `seu` worse — use plain `harvest_oai.py` there — and cannot help `uwu`.

16. **Several scripts have no argparse at all**: `validate_harvested_data.py`, `compare_dois.py`,
    `check_database_connection.py`, `apply_database_migrations.py`, `verify_database_schema.py`.
    All their paths are hard-coded module constants. Passing `--help` does not print help — the
    flag is ignored and the script runs, so the database ones will attempt a real connection.

17. **`compare_dois.py` needs an OpenAlex collection on disk first** — it reads `data/raw/openalex/openalex_sri_lanka_works.csv`, which does not exist until §1.1 has run.
