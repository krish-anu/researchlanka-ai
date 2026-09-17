# Phase 2 Database Integrity / ML / API Testing

**Purpose:** Final testing for Phase 2 (database schema integrity, hierarchical classification, NMF topic modeling, semantic search, and REST API coverage via a fixed test matrix).

## How to run

From `backend/`:

```bash
# Phase 2 suite only (writes structured report + API matrix automatically)
python scripts/testing/run_phase2_ml_api_tests.py

# Include related legacy ML/API/DB suites
python scripts/testing/run_phase2_ml_api_tests.py --include-legacy

# Or via pytest directly
pytest tests/phase2 --phase2-report -q
```

## Automatic artifacts

Every Phase 2 run writes to `data/reports/phase2_ml_api_tests/`:

| File | Format | Use |
|---|---|---|
| `latest_results.csv` | CSV table | Spreadsheet / CI artifact |
| `latest_report.md` | Markdown document | Human review / thesis appendix |
| `latest_summary.json` | JSON | Machine summary (pass rate by category) |
| `latest_api_matrix.md` | Markdown matrix | Test ID \| Endpoint \| Scenario \| Expected \| Result |
| `latest_api_matrix.csv` | CSV matrix | Same columns for spreadsheets |
| `phase2_ml_api_<timestamp>_*.{csv,md,json}` | Timestamped copies | Historical runs |

## Test categories

| Category | Marker | What it covers |
|---|---|---|
| Database integrity | `@pytest.mark.database_integrity` | Core tables, final column contract, typed sets, `publication_key`, row builder |
| Classification | `@pytest.mark.classification` | Hierarchical Linear SVM predict / label shape (offline fixtures) |
| NMF topic modeling | `@pytest.mark.nmf_topic_modeling` | k=25 artifact load, trend labels, topic publication join |
| Semantic search | `@pytest.mark.semantic_search` | Embeddings, ranked search, related-publications exclusion |
| API matrix | `@pytest.mark.api_matrix` | Fixed cases API-001…API-026 against service layer |

## API test matrix columns

| Column | Meaning |
|---|---|
| Test ID | Stable ID (`API-001` … `API-026`) |
| Endpoint | Route under `/api/v1/...` |
| Scenario | What the case exercises |
| Expected | Asserted outcome / status |
| Result | `PASS` / `FAIL` / `SKIP` filled by the reporter |

## Mapping to existing suites

Deeper regression coverage already lives in:

- `tests/test_database_loader.py`
- `tests/test_hierarchical_linear_svm.py`
- `tests/test_classification_model_comparison.py`
- `tests/test_nmf_topic_endpoints.py`
- `tests/test_publication_text_embeddings.py`
- `tests/test_api_service.py`
- `tests/test_model_fastapi_endpoints.py`

Use `--include-legacy` when you want the full Phase 2 regression wall.

## Pass criteria for Phase 2 sign-off

1. `tests/phase2` is green (`pass_rate_pct == 100` in `latest_summary.json`).
2. API matrix shows 26/26 PASS in `latest_api_matrix.md`.
3. Category table in `latest_report.md` shows no failed database / classification / NMF / semantic / API rows.
4. Timestamped report files are archived with the release notes.
