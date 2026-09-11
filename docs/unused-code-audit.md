# Unused Code Audit

Date: 2026-09-11

Status: safe cleanup completed

This audit was done with:

- `npm run typecheck -- --noUnusedLocals --noUnusedParameters` in `frontend/`
- Lightweight Python AST/reference scans across `backend/`
- Manual checks for framework entrypoints, Makefile targets, tests, and compatibility wrappers

## Cleaned Frontend Code

These were reported directly by TypeScript's unused-code checks and have been removed.

| File | Line | Removed code |
| --- | ---: | --- |
| `frontend/src/app/institutions/compare/page.tsx` | 5 | `TableDisclosure` import |
| `frontend/src/app/researchers/[...key]/page.tsx` | 33 | `topicHref` import |

No obviously unreferenced frontend source files were found after treating Next.js route files, API routes, layouts, tests, and middleware as entrypoints.

## Cleaned Python Imports

These imports were unused inside their files and have been removed.

| File | Line | Removed import |
| --- | ---: | --- |
| `backend/research_analytics/adapters/registry.py` | 7 | `Any` |
| `backend/src/ai_relevance/evaluation.py` | 9 | `pandas as pd` |
| `backend/src/collectors/sitemap_collector.py` | 13 | `field` |
| `backend/src/pipeline/collect_crossref.py` | 19 | `time` |
| `backend/src/quality/audit_crossref_lk_affiliations.py` | 12 | `csv` |
| `backend/src/quality/manual_review_ui.py` | 21 | `html` |
| `backend/tests/test_database_connection.py` | 8 | `check_connection` |
| `backend/src/api/repositories/postgres.py` | 18 | `quality_flags` |
| `backend/src/database/loader.py` | 18 | `FINAL_PUBLICATION_COLUMNS` |
| `backend/src/preprocessing/crossref_normalizer.py` | 21 | `OWNERSHIP_POLICY_VERSION` |

## Review Before Deleting

These modules currently have no internal import references from app code, scripts, tests, or configured package entrypoints. They may still be kept intentionally as public compatibility paths, older APIs, or documentation-backed utilities.

Do not delete these without checking whether external users, notebooks, or deployment scripts import them.

| File or module | Reason to review |
| --- | --- |
| `backend/src/api/aggregates.py` | Looks like a compatibility wrapper around newer `src.api.repositories` / `src.api.core` modules. |
| `backend/src/api/constants.py` | Looks like a compatibility wrapper. |
| `backend/src/api/errors.py` | Looks like a compatibility wrapper. |
| `backend/src/api/exports.py` | Looks like a compatibility wrapper. |
| `backend/src/api/protocols.py` | Looks like a compatibility wrapper. |
| `backend/src/api/query.py` | Looks like a compatibility wrapper. |
| `backend/src/api/serializers.py` | Looks like a compatibility wrapper. |
| `backend/src/api/sql.py` | Looks like a compatibility wrapper. |
| `backend/research_analytics/pagination.py` | No direct imports found; pagination logic appears implemented inline in adapters. |
| `backend/research_analytics/duplicate_analysis.py` | No direct imports found, but docs and dependencies mention it, so it may be a standalone/manual utility. |

## Not Removed

Some imports look unused to a simple in-file scan but are intentionally exposed as module attributes or script wrapper exports:

- `backend/src/collectors/openalex_collector.py`
- `backend/src/collectors/crossref_collector.py`
- `backend/src/modeling/training.py`
- `backend/src/modeling/linear_svm_training.py`
- `backend/scripts/modeling/create_dataset_splits.py`
- `backend/scripts/modeling/generate_publication_text_embeddings.py`
- `backend/scripts/modeling/train_logistic_regression_classifier.py`
- `backend/scripts/modeling/predict_publication_classifier.py`

The modeling scripts are also used by `backend/Makefile` targets.

## Verification

Frontend strict unused-code check passes:

```bash
npm --prefix frontend run typecheck -- --noUnusedLocals --noUnusedParameters
```

Recommended final backend check:

```bash
make check-backend
```
