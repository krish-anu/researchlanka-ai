# Columns 1-25: Final Dataset Decisions

**Dataset reviewed:** `data/processed/common/common_publications_deduplicated.csv`  
**Shape reviewed:** 184,827 rows x 76 columns  
**Columns reviewed:** columns 1-25, from `source_dataset` through `author_affiliations`  
**Purpose:** decide which first-block columns should be kept, merged, harmonized, moved out of the main dataset, or dropped.

> **Status:** implemented in `scripts/processing/build_final_common_dataset.py`.

This completes the same style of column review already documented for columns 26-50 and 51-76.

## Executive Decision

Keep **17** columns and drop or move **8**. Three drops are exact duplicates, two are date/provenance fields that add no extra populated rows beyond `publication_date`, and three are too sparse for publication-level analysis.

| Decision | Columns |
|---|---|
| Keep as core identifiers/provenance | `source_dataset`, `source_institution_id`, `source_record_id`, `source_datestamp`, `openalex_id`, `doi` |
| Keep as access/title/metadata fields | `url`, `pdf_url`, `title`, `abstract`, `keywords` |
| Keep but harmonize or validate before analysis | `publication_year`, `publication_date`, `type`, `authors`, `author_count`, `author_affiliations` |
| Drop - exact duplicate | `landing_page_url`, `publication_type`, `author_names` |
| Drop from main dataset unless date-audit analysis is needed | `created_date`, `published_date` |
| Drop - too sparse for main publication-level analysis | `subtitle`, `original_title`, `subtype` |

Recommended final block for the main dataset:

```text
source_dataset
source_institution_id
source_record_id
source_datestamp
openalex_id
doi
url
pdf_url
title
abstract
keywords
publication_year
publication_date
type
authors
author_count
author_affiliations
```

## Evidence Summary

All figures are against 184,827 total rows.

| Pos | Column | Present | Coverage | Missing | Distinct | Multi-value | Decision |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `source_dataset` | 184,827 | 100.00% | 0 | 14 | 44.9% | Keep |
| 2 | `source_institution_id` | 125,427 | 67.86% | 59,400 | 40 | 0.5% | Keep |
| 3 | `source_record_id` | 184,827 | 100.00% | 0 | 184,827 | 35.8% | Keep |
| 4 | `source_datestamp` | 125,426 | 67.86% | 59,401 | 106,991 | 0.8% | Keep as provenance |
| 5 | `openalex_id` | 73,257 | 39.64% | 111,570 | 73,257 | 0.0% | Keep |
| 6 | `doi` | 91,436 | 49.47% | 93,391 | 91,436 | 0.0% | Keep |
| 7 | `url` | 184,454 | 99.80% | 373 | 183,664 | 0.0% | Keep |
| 8 | `landing_page_url` | 184,454 | 99.80% | 373 | 183,664 | 0.0% | Drop - duplicate of `url` |
| 9 | `pdf_url` | 30,609 | 16.56% | 154,218 | 30,608 | 0.0% | Keep |
| 10 | `title` | 184,708 | 99.94% | 119 | 167,811 | 1.0% | Keep |
| 11 | `subtitle` | 761 | 0.41% | 184,066 | 717 | 5.5% | Drop or optional sidecar |
| 12 | `original_title` | 317 | 0.17% | 184,510 | 285 | 0.9% | Drop |
| 13 | `abstract` | 95,040 | 51.42% | 89,787 | 89,945 | 16.4% | Keep |
| 14 | `keywords` | 86,283 | 46.68% | 98,544 | 71,035 | 87.0% | Keep |
| 15 | `publication_year` | 183,358 | 99.21% | 1,469 | 100 | 0.0% | Keep + validate |
| 16 | `publication_date` | 183,261 | 99.15% | 1,566 | 6,264 | 0.0% | Keep |
| 17 | `created_date` | 65,946 | 35.68% | 118,881 | 3,782 | 0.0% | Drop from main |
| 18 | `published_date` | 65,779 | 35.59% | 119,048 | 3,857 | 0.0% | Drop from main |
| 19 | `type` | 182,076 | 98.51% | 2,751 | 126 | 0.0% | Keep + harmonize |
| 20 | `subtype` | 3,322 | 1.80% | 181,505 | 3 | 0.0% | Drop |
| 21 | `publication_type` | 182,076 | 98.51% | 2,751 | 126 | 0.0% | Drop - duplicate of `type` |
| 22 | `authors` | 181,046 | 97.95% | 3,781 | 142,093 | 67.6% | Keep |
| 23 | `author_count` | 73,257 | 39.64% | 111,570 | 96 | 0.0% | Keep |
| 24 | `author_names` | 181,046 | 97.95% | 3,781 | 142,093 | 67.6% | Drop - duplicate of `authors` |
| 25 | `author_affiliations` | 73,264 | 39.64% | 111,563 | 34,295 | 65.3% | Keep |

## Duplicate And Redundancy Checks

| Left column | Right column | Both present | Equal when both present | Left-only rows | Right-only rows | Decision |
|---|---|---:|---:|---:|---:|---|
| `url` | `landing_page_url` | 184,454 | 100.00% | 0 | 0 | Keep `url`, drop `landing_page_url` |
| `type` | `publication_type` | 182,076 | 100.00% | 0 | 0 | Keep `type`, drop `publication_type` |
| `authors` | `author_names` | 181,046 | 100.00% | 0 | 0 | Keep `authors`, drop `author_names` |
| `publication_date` | `created_date` | 65,946 | 44.09% | 117,315 | 0 | Drop `created_date` from main, not an exact duplicate |
| `publication_date` | `published_date` | 65,779 | 62.85% | 117,482 | 0 | Drop `published_date` from main, not an exact duplicate |
| `created_date` | `published_date` | 65,779 | 28.26% | 167 | 0 | Not a duplicate pair |

`created_date` and `published_date` are not value-identical to `publication_date`, but they add no populated records where `publication_date` is missing. Keep them only if the analysis specifically needs Crossref lifecycle dates. For the clean publication-level table, `publication_date` is enough.

## Per-Column Notes

### Provenance and identifiers, columns 1-6

`source_dataset`, `source_institution_id`, `source_record_id`, and `source_datestamp` should stay because they explain where each record came from and allow source-level auditing. `source_record_id` is unique for every deduplicated row and is multi-valued in merged rows, which is expected.

`openalex_id` is sparse at the whole-table level because repository-only and SLJOL-only records have no OpenAlex work ID. Keep it as a high-quality external identifier for OpenAlex-linked rows.

`doi` covers 49.47% of deduplicated rows. That lower whole-table coverage is driven by local repository records without DOI values. Keep it as the primary external identifier, but do not make DOI mandatory.

### URL and title fields, columns 7-12

`url` and `landing_page_url` are byte-identical in all 184,454 rows where either is present. Keeping both stores one fact twice. Keep `url` and drop `landing_page_url`.

`pdf_url` is OpenAlex-only and sparse, but it is useful for access workflows and full-text collection. Keep it.

`title` is almost complete and should be retained as a core field. `subtitle` is present in only 761 rows and never fills a missing title. `original_title` is present in only 317 rows, never fills a missing title, and is equal to `title` in 217 of those rows. Drop both from the main dataset, or move them to an optional title-detail sidecar if preserving every title variant is required.

### Text enrichment, columns 13-14

`abstract` covers 51.42% of rows and is important for search, topic modelling, and quality review. Keep it.

`keywords` covers 46.68% of rows and is highly multi-valued. Keep it, but normalize separators, casing, and duplicate terms before keyword-frequency analysis.

### Date and type fields, columns 15-21

`publication_year` and `publication_date` should stay. However, the current deduplicated dataset contains 53,844 rows with `publication_year` before 2016 and two invalid future years, `2029` and `2099`. If the target corpus is strictly 2016-2026, add a year validation/filtering step before analysis.

`created_date` and `published_date` do not add coverage beyond `publication_date`. Drop them from the main publication table unless a source-date audit is needed.

`type` and `publication_type` are exact duplicates. Keep `type` and drop `publication_type`. The `type` field still needs harmonization because it contains mixed spellings such as `article`, `Article`, `journal-article`, `conference-paper`, and local repository labels.

`subtype` covers only 1.80% of rows and has only three values: `preprint`, `other`, and `dissertation`. Drop it from the main dataset; use `type` and later `source_type` for publication grouping.

### Author fields, columns 22-25

`authors` is highly covered and should stay. `author_names` is an exact duplicate of `authors`, so drop `author_names`.

`author_count` is available mainly for OpenAlex-linked rows. Keep it because it supports collaboration-size analysis, but treat missing values as unknown rather than as single-author works.

`author_affiliations` is available mainly for OpenAlex and some Crossref records. Keep it as a useful affiliation text field, but use the cleaner institution fields in columns 30-32 when doing formal institution/country analysis.

## Final Accounting

With columns 26-50 and 51-76 using the existing final decisions, applying this first-25 review removes 8 more original-schema columns from the main table:

```text
landing_page_url
subtitle
original_title
created_date
published_date
subtype
publication_type
author_names
```

That leaves **52 original-schema columns**. The final builder also creates 4 main-table
OpenAlex-vs-Crossref count comparison columns:

```text
citation_count_difference_oa_minus_crossref
citation_count_divergence_flag
reference_count_difference_oa_minus_crossref
reference_count_divergence_flag
```

So the implemented clean main dataset width is **56 columns**, with no row loss.
