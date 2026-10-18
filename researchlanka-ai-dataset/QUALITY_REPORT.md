# Quality Report

Generated for `researchlanka_ai_publications_v1.0.csv` after final curation.

## Dataset Size

- Rows: 3,706
- Columns: 86
- Publication years: 2016-2026
- AI labels: `AI` only

## Validation Results

| Check | Status | Result |
| --- | --- | ---: |
| AI-only labels | Pass | 3,706 / 3,706 |
| Unique OpenAlex IDs | Pass | 3,706 / 3,706 |
| Duplicate DOI values | Pass | 0 |
| Blank titles | Pass | 0 |
| Blank publication dates | Pass | 0 |
| Blank source provenance | Pass | 0 |
| Blank classification confidence | Pass | 0 |
| Numeric confidence or human-review `not_applicable` | Pass | 3,706 / 3,706 |
| Blank model identifier | Pass | 0 |
| Absolute local model paths | Pass | 0 |
| Abstract/search-field consistency | Pass | 3,706 / 3,706 |
| Keyword/search-field consistency | Pass | 3,706 / 3,706 |
| Residual title/year candidate groups | Review | 78 groups / 168 rows |

Title/year matches are retained because they may represent preprint,
conference, or published versions rather than duplicate identifiers. There are
no duplicate OpenAlex IDs or DOI values.

## Completeness

| Field | Available |
| --- | ---: |
| `title` | 3,706 / 3,706 |
| `publication_date` | 3,706 / 3,706 |
| `source_dataset` | 3,706 / 3,706 |
| `source_record_id` | 3,706 / 3,706 |
| `abstract` | 3,013 / 3,706 |
| `keywords` | 3,521 / 3,706 |
| `doi` | 3,674 / 3,706 |
| `openalex_id` | 3,706 / 3,706 |
| `ai_classification_label` | 3,706 / 3,706 |
| `ai_classification_confidence` | 3,706 / 3,706 |
| `ai_classification_model` | 3,706 / 3,706 |

## Year Distribution

| Year | Rows |
| --- | ---: |
| 2016 | 70 |
| 2017 | 101 |
| 2018 | 134 |
| 2019 | 207 |
| 2020 | 277 |
| 2021 | 373 |
| 2022 | 413 |
| 2023 | 392 |
| 2024 | 410 |
| 2025 | 685 |
| 2026 | 644 |

## Source Distribution

| Source dataset | Rows |
| --- | ---: |
| `openalex` | 1,565 |
| `openalex; crossref` | 1,332 |
| `openalex; repositories_combined` | 339 |
| `openalex; crossref; repositories_combined` | 295 |
| `openalex; sljol` | 147 |
| `crossref; openalex` | 26 |
| `openalex; sljol; repositories_combined` | 2 |

## Publication Decision

The dataset is the final AI-only handover corpus. Public redistribution remains
blocked only until the source-specific licensing decision documented in
`LICENSE` is approved.
