# Changelog

## Abstract enrichment - 2026-09-22

- Filled 2,543 missing abstracts from `backend/data/results (1)/common_publications_FINAL_filled.csv` using unique publication identifier matches. Of these, 115 have `MATCHED` recovery status and 2,428 were already present in the supplied filled dataset.
- Abstract coverage is now 3,670 of 4,177 publications; 507 abstracts remain missing.
- Preserved existing abstracts, all other fields, and row order. AI classifications were not rerun.
- Synchronized the CSV and Parquet files and refreshed package checksums.

## v1.0 Release Candidate - 2026-09-11

- Created public dataset package structure.
- Added CSV and Parquet dataset files.
- Added README, data dictionary, methodology, quality report, license notice, citation metadata, and checksums.
- Rebuilt AI-only dataset with populated SVM margin-derived confidence values.
- Documented current release blockers: 2 blank titles, 203 duplicate candidates, pending human audit, and pending final license decision.

