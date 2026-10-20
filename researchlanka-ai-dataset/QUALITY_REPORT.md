# Quality Report

Generated for `researchlanka_ai_publications_v1.0.csv` after final curation.

## Dataset Size

- Rows: 3,555
- Public columns: 35
- Private master columns: 86
- Publication years: 2016-2026
- AI labels: `AI` only

## Validation Results

| Check | Status | Result |
| --- | --- | ---: |
| AI-only labels | Pass | 3,555 / 3,555 |
| Unique OpenAlex IDs | Pass | 3,555 / 3,555 |
| Duplicate DOI values | Pass | 0 |
| Duplicate normalized titles | Pass | 0 |
| Secondary `REVIEW` decisions | Pass | 0 |
| Unsupported ambiguous-institution ownership | Pass | 0 |
| Blank titles | Pass | 0 |
| Blank publication dates | Pass | 0 |
| Blank source provenance | Pass | 0 |
| Blank classification confidence | Pass | 0 |
| Numeric confidence or human-review `not_applicable` | Pass | 3,555 / 3,555 |
| Blank model identifier | Pass | 0 |
| Absolute local model paths | Pass | 0 |
| Abstract availability measured | Pass | 2,896 present / 659 missing |
| Exact documented public schema | Pass | 35 / 35 columns |
| Keyword/search-field consistency | Pass | 3,555 / 3,555 |
| Release validator quality gates | Pass | 16 / 16 |

The audit consolidated 95 connected title/version groups covering 202 records.
It retained 95 canonical works and excluded 107 alternate versions. There are
no remaining duplicate OpenAlex IDs, DOI values, normalized titles, or
normalized title/year keys.

## Completeness

| Field | Available |
| --- | ---: |
| `title` | 3,555 / 3,555 |
| `publication_date` | 3,555 / 3,555 |
| `source_dataset` | 3,555 / 3,555 |
| `source_record_id` | 3,555 / 3,555 |
| `abstract` | 2,896 / 3,555 (81.46%) |
| `keywords` | 3,378 / 3,555 |
| `doi` | 3,523 / 3,555 |
| `openalex_id` | 3,555 / 3,555 |
| `ai_classification_label` | 3,555 / 3,555 |
| `ai_classification_confidence` | 3,555 / 3,555 |
| `ai_classification_model` | 3,555 / 3,555 |

## Year Distribution

| Year | Rows |
| --- | ---: |
| 2016 | 68 |
| 2017 | 100 |
| 2018 | 129 |
| 2019 | 200 |
| 2020 | 268 |
| 2021 | 363 |
| 2022 | 404 |
| 2023 | 382 |
| 2024 | 399 |
| 2025 | 660 |
| 2026 | 582 |

## Source Distribution

| Source dataset | Rows |
| --- | ---: |
| `openalex` | 1,421 |
| `openalex; crossref` | 1,327 |
| `openalex; repositories_combined` | 337 |
| `openalex; crossref; repositories_combined` | 295 |
| `openalex; sljol` | 147 |
| `crossref; openalex` | 26 |
| `openalex; sljol; repositories_combined` | 2 |

## Publication Decision

The dataset is the technically finalized handover corpus and retains available
abstract text. Public deposition remains blocked until the dataset owner
confirms abstract/source redistribution rights and selects the dataset-level
license documented in `LICENSE`.
