# Changelog

## Final AI-only curation - 2026-10-18

- Replaced the release candidate with the supplied 3,706-row final AI-only
  dataset.
- Removed 352 records confirmed as non-AI; the kept and excluded partitions
  exactly reconstruct the previous 4,058-row candidate export.
- Applied 24 supplied abstract and keyword metadata corrections.
- Recomputed title, abstract, and keyword search-helper fields.
- Replaced absolute workstation model paths with portable model identifiers.
- Removed the Parquet and obsolete scraped-merge copies so the package exposes
  one canonical CSV.

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
