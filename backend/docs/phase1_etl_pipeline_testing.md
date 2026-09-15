# Phase 1 ETL / Data Integration Pipeline Testing

**Purpose:** Final testing for Phase 1 (data collection, cleaning, preprocessing, transforming, deduplication, author disambiguation, institution entity resolution, Dagster orchestration, and database ingestion contract).

## How to run

From `backend/`:

```bash
# Phase 1 suite only (writes structured report automatically)
python scripts/testing/run_phase1_pipeline_tests.py

# Include related legacy suites (author, institution, dedup, loader, framework, …)
python scripts/testing/run_phase1_pipeline_tests.py --include-legacy

# Or via pytest directly
pytest tests/phase1 --phase1-report -q
```

## Automatic artifacts

Every Phase 1 run writes to `data/reports/phase1_pipeline_tests/`:

| File | Format | Use |
|---|---|---|
| `latest_results.csv` | CSV table | Spreadsheet / CI artifact |
| `latest_report.md` | Markdown document | Human review / thesis appendix |
| `latest_summary.json` | JSON | Machine summary (pass rate by category) |
| `phase1_etl_pipeline_<timestamp>_*.{csv,md,json}` | Timestamped copies | Historical runs |

## Test categories and methods

| Category | Marker | Method | What it covers |
|---|---|---|---|
| Cleaning | `@pytest.mark.cleaning` | Unit + edge-case parametrize | DOI/title/date/list null/whitespace rules |
| Preprocessing | `@pytest.mark.preprocessing` | Unit + series fixtures | Tamil stripping, boilerplate, stopword n-grams |
| Transforming | `@pytest.mark.transforming` | Unit | Config-driven field transforms + schema mapping |
| Deduplication | `@pytest.mark.deduplication` | Unit + edge cases | DOI auto-merge, title-year, fuzzy, disabled mode |
| Disambiguation | `@pytest.mark.disambiguation` | Unit + ORCID edge cases | Name parse, ORCID conflict, cluster splits |
| Entity resolution | `@pytest.mark.entity_resolution` | Fixture registry | Alias match, foreign miss, collaboration typing |
| E2E ingestion | `@pytest.mark.e2e_ingestion` | Integration (temp CSV) | Collect→transform→validate→clean→resolve→dedupe→export |
| Dagster | `@pytest.mark.dagster` | Smoke / optional import | Job + asset wiring; skips if dagster missing |
| Database | `@pytest.mark.database` | Unit | `publication_key` + final row contract |

## Mapping to existing suites

The new `tests/phase1/` package is the Phase 1 gate. Deeper regression coverage already lives in:

- `tests/test_author_disambiguation.py`
- `tests/test_institution_normalization.py`
- `tests/test_deduplication_thresholds.py`
- `tests/test_database_loader.py`
- `tests/test_research_analytics_framework.py`
- `tests/test_kaggle_merge_common_dataset.py`
- `tests/test_build_final_common_dataset.py`

Use `--include-legacy` when you want the full Phase 1 regression wall.

## Pass criteria for Phase 1 sign-off

1. `tests/phase1` is green (`pass_rate_pct == 100` in `latest_summary.json`).
2. Category table in `latest_report.md` shows no failed cleaning / dedup / entity / e2e rows.
3. Dagster smoke tests pass (or are explicitly skipped with reason if Dagster is not installed in the environment).
4. Timestamped report files are archived with the release notes.
