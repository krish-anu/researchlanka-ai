# Quality Report

Generated for `researchlanka_ai_publications_v1.0`.

## Dataset Size

- Rows: 4,177
- Columns: 66
- Publication years: 2016-2026
- AI labels included: `AI`

## Automated Release Gates

| Gate | Status | Count | Meaning |
| --- | --- | ---: | --- |
| Required columns present | Pass | 0 | All required release columns exist. |
| Title not blank | Fail | 2 | Two records need title repair or exclusion. |
| Publication date not blank | Pass | 0 | All rows have publication dates. |
| Source dataset not blank | Pass | 0 | All rows have source provenance. |
| Source record ID not blank | Pass | 0 | All rows have source record IDs. |
| AI label not blank | Pass | 0 | All rows have an AI classification label. |
| AI confidence not blank | Pass | 0 | All rows have an AI confidence-like score. |
| AI model not blank | Pass | 0 | All rows have model provenance. |
| Final release labels are AI | Pass | 0 | No non-AI labels are present in the AI-only release. |
| AI confidence range | Pass | 0 | Confidence values are within `[0, 1]`. |
| Publication year range | Pass | 0 | No missing, impossible, or future years after 2026. |
| Negative reference count | Pass | 0 | No negative reference counts. |
| Sri Lanka manual review resolved | Pass | 0 | No rows remain marked for manual Sri Lanka review. |
| Sri Lanka evidence available | Pass | 0 | Every row has obvious Sri Lanka evidence text. |
| Duplicate candidates | Review required | 203 | Candidate duplicate rows require manual confirmation. |
| License metadata available | Pass | 0 | Every row has license or open-access metadata. |

## Required Field Completeness

| Field | Available |
| --- | ---: |
| `title` | 4,175 / 4,177, 99.95% |
| `publication_date` | 4,177 / 4,177, 100.00% |
| `source_dataset` | 4,177 / 4,177, 100.00% |
| `source_record_id` | 4,177 / 4,177, 100.00% |
| `ai_classification_label` | 4,177 / 4,177, 100.00% |
| `ai_classification_confidence` | 4,177 / 4,177, 100.00% |
| `ai_classification_model` | 4,177 / 4,177, 100.00% |

## Year Distribution

| Year | Rows |
| --- | ---: |
| 2016 | 84 |
| 2017 | 136 |
| 2018 | 178 |
| 2019 | 253 |
| 2020 | 301 |
| 2021 | 425 |
| 2022 | 470 |
| 2023 | 453 |
| 2024 | 449 |
| 2025 | 726 |
| 2026 | 702 |

## Source Distribution

| Source dataset | Rows |
| --- | ---: |
| `openalex` | 1,739 |
| `openalex; crossref` | 1,419 |
| `openalex; repositories_combined` | 474 |
| `openalex; crossref; repositories_combined` | 366 |
| `openalex; sljol` | 152 |
| `crossref; openalex` | 24 |
| `openalex; sljol; repositories_combined` | 3 |

## Release Decision

Do not publish this as the final public v1.0 until:

1. The 2 blank-title records are repaired or removed.
2. The 203 duplicate candidates are manually reviewed.
3. The 500-row human AI and Sri Lanka relevance audit is completed.
4. The license and redistribution policy is confirmed.

