# Preprocessing Status Report

**Date:** 2026-07-29  
**Current best dataset:** `data/processed/common/common_publications_final_2016_2026_analysis_ready.csv`  
**Shape:** 129,512 rows x 71 columns

## Current Pipeline State

The project now has a reproducible preprocessing chain:

```bash
python scripts/processing/kaggle_merge_common_dataset.py
python scripts/processing/build_final_common_dataset.py
python scripts/processing/build_columns_filtered_dataset.py
python scripts/processing/build_year_filtered_dataset.py
python scripts/processing/build_language_normalized_dataset.py
python scripts/processing/build_multivalue_normalized_dataset.py
python scripts/processing/build_analysis_ready_dataset.py
```

The latest Kaggle/all-column analysis report is available in:

```text
data/reports/final_dataset_column_analysis/
```

## Completed Preprocessing

### 1. Merge and deduplication

Completed by `kaggle_merge_common_dataset.py`.

Outputs:

```text
data/processed/common/common_publications_all_records.csv
data/processed/common/common_publications_deduplicated.csv
data/processed/common/common_publications_schema.csv
data/processed/common/common_publications_merge_log.csv
```

Summary:

```text
All-record rows: 291,890
Deduplicated rows: 184,827
Common schema columns: 76
Manual review candidate groups: 4,619
Manual review candidate records: 9,770
```

### 2. Final column filtering

Completed by `build_final_common_dataset.py`.

Output:

```text
data/processed/common/common_publications_final.csv
```

Summary:

```text
Input rows: 184,827
Input columns: 76
Output rows: 184,827
Output columns: 56
```

Completed decisions:

```text
Dropped duplicate/sparse/raw columns
Moved references_json to publication_references.csv
Moved count-audit fields to publication_count_audit.csv
Renamed cited_by_count -> citation_count
Renamed funder_id -> funder_identifier
Normalized funder identifiers
Deduplicated selected semicolon fields
```

Sidecars:

```text
data/processed/common/publication_references.csv
data/processed/common/publication_count_audit.csv
```

### 3. Finalized columns dataset

Completed by `build_columns_filtered_dataset.py`.

Output:

```text
data/processed/common/common_publications_columns_filtered.csv
```

Summary:

```text
Rows: 184,827
Columns: 56
```

This is a reproducible final-column-only output.

### 4. Year filtering

Completed by `build_year_filtered_dataset.py`.

Output:

```text
data/processed/common/common_publications_final_2016_2026.csv
```

Summary:

```text
Input rows: 184,827
Kept rows: 129,512
Dropped before 2016: 53,844
Dropped after 2026: 2
Dropped missing/invalid year: 1,469
Year range after filtering: 2016 to 2026
```

### 5. Language normalization

Completed by `build_language_normalized_dataset.py`.

Output:

```text
data/processed/common/common_publications_final_2016_2026_language_normalized.csv
```

Mapping/report:

```text
data/processed/common/common_publications_final_2016_2026_language_normalized_mapping.csv
data/processed/common/common_publications_final_2016_2026_language_normalized_summary.csv
```

Rules applied:

```text
en_US -> en
si_lk -> si
English -> en
blank/missing -> unknown
lowercase language codes
```

Summary:

```text
Rows: 129,512
Distinct languages before: 52
Distinct languages after: 50
```

Current top language values:

```text
en: 105,848
unknown: 17,835
other: 4,088
si: 951
fr: 128
id: 116
es: 88
ar: 73
```

### 6. Multi-value parsing and normalization

Completed by `build_multivalue_normalized_dataset.py`.

Output:

```text
data/processed/common/common_publications_final_2016_2026_multivalue_normalized.csv
```

Exploded sidecar for Kaggle:

```text
data/processed/common/publication_multivalue_items_2016_2026.csv
```

Columns normalized:

```text
authors
keywords
institutions
countries
concepts
topics
funder_name
source_dataset
```

Rules applied:

```text
Split on semicolon
Strip and collapse extra spaces
Deduplicate items inside each cell
keywords and source_dataset lowercased
countries uppercased
```

Summary:

```text
Main rows: 129,512
Main columns: 56
Exploded item rows: 2,850,764
```

### 7. Text cleaning for NLP/search

Completed by `build_analysis_ready_dataset.py`.

Current output:

```text
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```

Added helper columns:

```text
title_search_text
abstract_search_text
keywords_search_text
abstract_missing_flag
```

Rules applied:

```text
Lowercase search text
Strip and collapse spaces
Deduplicate keyword tokens
Do not overwrite original title/abstract/keywords
Flag missing abstracts
```

Current quality:

```text
Missing title rows: 88
Missing abstract rows: 59,075
```

### 8. Identifier normalization

Completed by `build_analysis_ready_dataset.py`.

Normalized fields:

```text
doi
openalex_id
url
pdf_url
author_orcids
issn
issn_l
funder_doi
funder_identifier
```

Current issue count:

```text
identifier_issues: 20
```

This is low. Remaining identifier issues are mostly URL cleanup cases, not major DOI/ORCID problems.

### 9. Numeric conversion

Completed by `build_analysis_ready_dataset.py`.

Converted fields:

```text
publication_year
author_count
citation_count
reference_count
citation_count_difference_oa_minus_crossref
reference_count_difference_oa_minus_crossref
```

Fields intentionally left as text:

```text
volume
issue
first_page
last_page
article_number
```

Current issue count:

```text
numeric_issues: 0
```

### 10. Missing-value flags

Completed by `build_analysis_ready_dataset.py`.

Added flags:

```text
abstract_missing_flag
funder_name_missing_flag
funder_doi_missing_flag
funder_identifier_missing_flag
funder_award_missing_flag
license_missing_flag
license_url_missing_flag
pdf_url_missing_flag
author_orcids_missing_flag
article_number_missing_flag
```

Important missingness:

```text
funder_award missing: 122,184
funder_doi missing: 121,038
funder_identifier missing: 121,002
funder_name missing: 118,800
article_number missing: 119,362
author_orcids missing: 107,853
pdf_url missing: 98,903
license missing: 94,641
license_url missing: 89,237
```

These are mostly naturally sparse fields. They should not be blindly filled.

### 11. Author name cleaning helper

Partly completed by `build_analysis_ready_dataset.py`.

Added:

```text
authors_clean
author_disambiguation_available_flag
```

Current status:

```text
authors_clean present: 128,427
authors_clean missing: 1,085
author_orcids present: 21,659
author_orcids missing: 107,853
```

Basic cleanup is done. True author disambiguation is still pending.

### 12. Open access and license cleanup

Partly completed by `build_analysis_ready_dataset.py`.

Cleaned fields:

```text
oa_status
is_oa
license
license_url
```

Current values:

```text
oa_status unknown: 56,255
license unknown/missing: 94,641
license_url missing: 89,237
is_oa missing/unknown: 56,255
```

Important rule:

```text
Missing is_oa should be treated as unknown, not False.
```

### 13. Separate preprocessing issue files

Completed by `build_analysis_ready_dataset.py`.

Folder:

```text
data/processed/common/preprocessing_issues_2016_2026/
```

Files:

```text
text_issues.csv
identifier_issues.csv
numeric_issues.csv
missingness_issues.csv
author_issues.csv
oa_license_issues.csv
all_preprocessing_issues.csv
issue_file_summary.csv
```

Issue counts:

```text
text_issues: 335,087
identifier_issues: 20
numeric_issues: 0
missingness_issues: 10
author_issues: 157,090
oa_license_issues: 304,288
```

## Current Best Dataset For Kaggle

Use this for most analysis:

```text
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```

Use this for analyzing individual authors, keywords, institutions, countries, concepts, topics, funders, or source datasets:

```text
data/processed/common/publication_multivalue_items_2016_2026.csv
```

Use this for all-column profiling reports:

```text
data/reports/final_dataset_column_analysis/
```

## Remaining Preprocessing To Do

### Priority 1: Publication type harmonization

Status: not done.

Current problem:

```text
type has 95 distinct values
```

Examples:

```text
article
Article
journal-article
conference-paper
Conference-Full-text
Conference-Abstract
Thesis-Full-text
Other
Exam Paper
```

Needed output column:

```text
type_clean
```

Recommended cleaned groups:

```text
journal_article
conference_paper
conference_abstract
thesis
book_chapter
book
preprint
report
review
abstract
dataset
software
exam_material
presentation
speech_lecture
front_matter
other
unknown
```

Why it matters:

```text
Publication type analysis is currently unreliable until Article/article/journal-article and similar variants are merged.
```

### Priority 2: Publisher alias cleaning

Status: not done.

Current problem:

```text
publisher has 6,035 distinct values
publisher missing: 10,294 rows
```

Example duplicate:

```text
Sri Lanka Journals Online
Sri Lanka Journals Online (JOL)
```

Needed output column:

```text
publisher_clean
```

Why it matters:

```text
Publisher rankings and source summaries will be split across aliases unless this is cleaned.
```

### Priority 3: Journal / venue alias cleaning

Status: not done.

Current problem:

```text
journal has 14,505 distinct values
journal missing: 49,267 rows
```

Some high-frequency values are not true journals:

```text
Zenodo
SSRN Electronic Journal
Research Square
Figshare
Elsevier eBooks
```

Needed output columns:

```text
journal_clean
venue_clean
venue_category
```

Why it matters:

```text
Journal analysis needs to separate journals, repositories, preprint servers, ebook platforms, proceedings, and datasets.
```

### Priority 4: Institution alias cleaning

Status: not done.

Current problem:

```text
institutions has 26,211 distinct values
sri_lankan_institutions has 3,445 distinct values
institutions missing: 56,255 rows
```

Needed output columns:

```text
institutions_clean
sri_lankan_institutions_clean
institution_country_clean
```

Why it matters:

```text
University rankings, domestic collaboration, and international collaboration analysis depend on clean institution names.
```

### Priority 5: Author disambiguation

Status: partly done, not complete.

Completed:

```text
authors_clean
author_disambiguation_available_flag
```

Still needed:

```text
author_cluster_id
author_name_key
orcid-based author matching
name + institution matching for non-ORCID authors
```

Why it matters:

```text
ORCID coverage is only 21,659 rows, so author-level productivity analysis can over-count or split the same person.
```

### Priority 6: Abstract/NLP strategy

Status: partly done.

Completed:

```text
abstract_search_text
abstract_missing_flag
```

Still needed:

```text
For NLP, decide whether to use title + keywords when abstract is missing.
Create nlp_text = title_search_text + keywords_search_text + abstract_search_text.
Do not run abstract-only NLP on rows with abstract_missing_flag = True.
```

Why it matters:

```text
59,075 rows have missing abstracts.
```

### Priority 7: Open access analysis strategy

Status: cleaned, but missingness remains.

Still needed:

```text
Create oa_status_clean if grouping should merge unknown/missing explicitly.
Use is_oa = unknown separately from False.
Use license only when license_missing_flag = False.
```

Why it matters:

```text
oa_status unknown: 56,255
license missing: 94,641
```

### Priority 8: Duplicate review after analysis-ready output

Status: needs review.

Current flags:

```text
duplicate_doi_rows: 0 among non-empty DOI values
duplicate_title_year_rows: 6,933
duplicate_title_year_values in overview: 7,014
```

Still needed:

```text
Review title + year duplicates.
Use title + year + first author where possible.
Decide if these are true duplicate publications, proceedings items, or legitimate repeated titles.
```

## Recommended Next Work Order

Do these next, in this order:

```text
1. Add type_clean
2. Add publisher_clean
3. Add journal_clean, venue_clean, venue_category
4. Add institutions_clean and sri_lankan_institutions_clean
5. Add nlp_text for search/topic modeling
6. Review duplicate title-year groups
7. Add author disambiguation only after institution aliases are cleaner
```

## Current Verification

Current test suite status:

```text
140 passed
```

The latest all-column report was refreshed against:

```text
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```

