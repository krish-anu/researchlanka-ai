# Last 26 Columns: Final Dataset Decisions

**Dataset reviewed:** `data/processed/common/common_publications_all_records.csv`  
**Shape reviewed:** 291,890 rows x 76 columns  
**Columns reviewed:** columns 51-76, from `oa_status` through `raw_source_json`  
**Purpose:** decide which of the final 26 merged-dataset columns should be kept, merged, modified, deduplicated, moved to an audit/sidecar table, or dropped for a cleaner final dataset.

> **Status:** implemented in `scripts/build_final_common_dataset.py`.
>
> The coverage figures in this document were measured on an earlier build of
> `common_publications_all_records.csv` (291,890 rows). The current build has 277,068
> all-records rows and 170,365 deduplicated rows, so absolute counts here no longer match;
> the relative decisions still hold. Re-measure with
> `python scripts/profile_common_dataset.py` before quoting any number from this document.
>
> Columns 26-50 are covered by
> [08_columns_26_50_final_dataset_decisions.md](08_columns_26_50_final_dataset_decisions.md),
> while columns 1-25 are covered by
> [09_columns_1_25_final_dataset_decisions.md](09_columns_1_25_final_dataset_decisions.md).
> Together, the current implemented decisions reduce the original 76-column schema to
> 52 surviving source columns, plus 4 generated count comparison columns in the main
> dataset, for 56 final columns.

## Executive Decision

For the final public dataset, keep or standardize the analytical fields, move source-specific count comparison columns to `publication_count_audit.csv`, and remove or move the remaining bulky or sparse fields:

| Decision | Columns |
|---|---|
| Keep as main analytical fields | `oa_status`, `is_oa`, `citation_count`, `reference_count`, `citation_count_difference_oa_minus_crossref`, `citation_count_divergence_flag`, `reference_count_difference_oa_minus_crossref`, `reference_count_divergence_flag`, `concepts`, `topics`, `primary_topic`, `primary_field`, `primary_subfield`, `primary_domain`, `funder_name`, `funder_doi`, `funder_award`, `source_set_specs`, `raw_identifiers` |
| Keep but rename/standardize | `cited_by_count` -> `citation_count`; `funder_id` -> normalized `funder_identifier` |
| Move to sidecar/audit table | `references_json`; source-specific count columns `is_referenced_by_count`, `referenced_works_count` |
| Move to optional sidecar or drop from main dataset | `event_name`, `event_acronym`, `event_location`, `event_start_date`, `event_end_date`, `event_sponsor` |
| Drop from final dataset | `raw_source_json` because it is completely empty in the current output |

Recommended final block for the main dataset:

```text
oa_status
is_oa
citation_count
reference_count
citation_count_difference_oa_minus_crossref
citation_count_divergence_flag
reference_count_difference_oa_minus_crossref
reference_count_divergence_flag
concepts
topics
primary_topic
primary_field
primary_subfield
primary_domain
funder_name
funder_doi
funder_identifier
funder_award
source_set_specs
raw_identifiers
```

## Evidence Summary

| Column | Non-empty rows | Coverage | Source coverage | Final decision |
|---|---:|---:|---|---|
| `oa_status` | 73,289 | 25.11% | OpenAlex 100.0% | Keep |
| `is_oa` | 73,289 | 25.11% | OpenAlex 100.0% | Keep |
| `cited_by_count` | 139,235 | 47.70% | Crossref 100.0%; OpenAlex 100.0% in the previous merged output | Rename to `citation_count`; select through the configured field policy |
| `is_referenced_by_count` | 139,235 | 47.70% | Crossref citation count | Move to `publication_count_audit.csv` |
| `reference_count` | 139,235 | 47.70% | Crossref/OpenAlex-derived reference count | Keep as best available reference count from the normal merge |
| `referenced_works_count` | 73,289 | 25.11% | OpenAlex 100.0% | Move to `publication_count_audit.csv` |
| `references_json` | 39,377 | 13.49% | Crossref 59.7% | Move to reference sidecar table |
| `concepts` | 73,188 | 25.07% | OpenAlex 99.9% | Keep as optional topic enrichment |
| `topics` | 71,813 | 24.60% | OpenAlex 98.0% | Keep |
| `primary_topic` | 71,813 | 24.60% | OpenAlex 98.0% | Keep |
| `primary_field` | 71,813 | 24.60% | OpenAlex 98.0% | Keep |
| `primary_subfield` | 71,813 | 24.60% | OpenAlex 98.0% | Keep |
| `primary_domain` | 71,813 | 24.60% | OpenAlex 98.0% | Keep |
| `funder_name` | 10,717 | 3.67% | Crossref 16.3% | Keep; sparse but high-value |
| `funder_doi` | 8,474 | 2.90% | Crossref 12.8% | Keep; normalize DOI values |
| `funder_id` | 8,510 | 2.92% | Crossref 12.9% | Modify to `funder_identifier`; remove JSON wrapper text |
| `funder_award` | 7,340 | 2.51% | Crossref 11.1% | Keep; sparse but useful grant metadata |
| `event_name` | 9,496 | 3.25% | Crossref 14.4% | Drop from main dataset; optional sidecar only |
| `event_acronym` | 1,488 | 0.51% | Crossref 2.3% | Drop from main dataset |
| `event_location` | 7,754 | 2.66% | Crossref 11.8% | Drop from main dataset; optional sidecar only |
| `event_start_date` | 7,470 | 2.56% | Crossref 11.3% | Drop from main dataset; optional sidecar only |
| `event_end_date` | 7,447 | 2.55% | Crossref 11.3% | Drop from main dataset; optional sidecar only |
| `event_sponsor` | 255 | 0.09% | Crossref 0.4% | Drop from main dataset |
| `source_set_specs` | 41,742 | 14.30% | Repositories 33.0% | Keep as repository provenance; deduplicate values |
| `raw_identifiers` | 152,625 | 52.29% | Repositories 100.0%; SLJOL 100.0% | Keep as provenance; deduplicate and normalize DOI/URL text |
| `raw_source_json` | 0 | 0.00% | none | Drop from final dataset |

## Merge And Drop Rules

### 1. Citation count

`cited_by_count` and `is_referenced_by_count` were identical in the previous merged output because the merge script copied one source's count into the other source-specific column. The final public dataset now keeps the best available `citation_count` and moves source-specific count details to `publication_count_audit.csv`.

Final rule:

```text
citation_count = merged cited_by_count
is_referenced_by_count = Crossref is-referenced-by-count
citation_count_difference_oa_minus_crossref = OpenAlex cited_by_count - Crossref is-referenced-by-count
citation_count_divergence_flag = abs(citation_count_difference_oa_minus_crossref) >= 10
main dataset drops is_referenced_by_count after writing the count-audit sidecar
```

If only one count source is present, `citation_count` keeps that available value and the OpenAlex-vs-Crossref difference fields stay empty.

### 2. Reference count

`reference_count` is the best available reference count from the configured field policy. `referenced_works_count` is retained in `publication_count_audit.csv` for source comparison when available.

Final rule:

```text
reference_count = merged reference_count
referenced_works_count = OpenAlex referenced_works_count
reference_count_difference_oa_minus_crossref = referenced_works_count - reference_count
reference_count_divergence_flag = reference_count_difference_oa_minus_crossref != 0
main dataset drops referenced_works_count after writing the count-audit sidecar
```

Rows with only one source should leave the difference and divergence flag empty.

### 3. References JSON

`references_json` contains detailed Crossref reference-list payloads for 39,377 rows. This is too heavy and sparse for the main publication table, but it is valuable for citation-network or reference-level analysis.

Final rule:

```text
move references_json to publication_references.csv or another sidecar table
main dataset should not carry references_json
```

Suggested sidecar fields:

```text
publication_key
doi
reference_index
reference_doi
reference_title
reference_author
reference_year
raw_reference_json
```

### 4. Topic fields

OpenAlex topic fields are source-specific but useful. They should not be merged with Crossref/local fields because there are no equivalent columns in the other sources.

Final rule:

```text
keep concepts
keep topics
keep primary_topic
keep primary_field
keep primary_subfield
keep primary_domain
```

Use `primary_domain`, `primary_field`, `primary_subfield`, and `primary_topic` for clean grouping. Use `topics` and `concepts` for search, tagging, and exploratory analysis.

### 5. Funding fields

Funding metadata is sparse but high-value. `funder_doi` is clean enough to keep. `funder_id` is not clean enough as-is because values contain JSON-like strings and mixed identifier types.

Final rule:

```text
keep funder_name
keep funder_doi
modify funder_id -> funder_identifier
keep funder_award
```

Required cleanup for `funder_identifier`:

```text
extract IDs from JSON-like strings
deduplicate identifiers inside each cell
normalize DOI identifiers to lowercase
preserve ROR identifiers such as https://ror.org/...
join multiple IDs with "; "
```

Observed detail: 36 rows have `funder_id` values without `funder_doi`; these are ROR-style identifiers, so dropping `funder_id` outright would lose information.

### 6. Event fields

Conference/event fields are very sparse and are not required for a clean publication-level dataset. They are useful only if the research question specifically includes conferences, proceedings, event locations, or event sponsors.

Final rule:

```text
drop event_name from the main dataset
drop event_acronym from the main dataset
drop event_location from the main dataset
drop event_start_date from the main dataset
drop event_end_date from the main dataset
drop event_sponsor from the main dataset
```

If event analysis is needed later, create an optional sidecar table instead of carrying these sparse fields in every publication row.

Suggested optional sidecar fields:

```text
publication_key
doi
event_name
event_acronym
event_location
event_start_date
event_end_date
event_sponsor
```

Reason for dropping from the main dataset:

```text
too many missing values
only Crossref provides these fields
not needed for most publication-level analysis
adds width without improving core dataset quality
can be recovered later from Crossref/source data if needed
```

### 7. Provenance fields

`source_set_specs` and `raw_identifiers` are not analytical metadata, but they are important for tracing repository and SLJOL records.

Final rule:

```text
keep source_set_specs
keep raw_identifiers
deduplicate semicolon-separated values inside each cell
normalize DOI-like values using the project DOI normalizer
normalize URL-like values by trimming spaces and trailing punctuation
```

If a slim public dataset is required, move these two fields to a provenance sidecar table. For the internal final dataset, keep them.

### 8. Raw source JSON

`raw_source_json` is empty in the current file because the merge script only fills it when run with `--include-raw-json`.

Final rule:

```text
drop raw_source_json from the final dataset
```

Keep it only in a separate audit build if the pipeline is rerun with raw JSON enabled.

## Final Dataset Readiness Checklist

Before publishing the final dataset, apply these checks to the last 26-column block:

| Check | Expected result |
|---|---|
| Source-specific citation field removed from public table | `is_referenced_by_count` absent from main CSV and present in `publication_count_audit.csv` |
| Source-specific reference field removed from public table | `referenced_works_count` absent from main CSV and present in `publication_count_audit.csv` |
| Empty raw JSON removed | `raw_source_json` absent |
| Citation divergence is auditable | `citation_count_difference_oa_minus_crossref` and `citation_count_divergence_flag` present; source counts in sidecar |
| Reference divergence is auditable | `reference_count_difference_oa_minus_crossref` and `reference_count_divergence_flag` present; source counts in sidecar |
| Funding identifiers normalized | no JSON-like wrappers in `funder_identifier` |
| Multi-value cells deduplicated | repeated IDs/topics/specs removed within each cell |
| Event fields removed from main dataset | `event_name`, `event_acronym`, `event_location`, `event_start_date`, `event_end_date`, and `event_sponsor` absent |
| Reference-list payload separated | `references_json` moved out of main publication table |

## Recommended Implementation Order

1. Add a final-cleaning step after `common_publications_all_records.csv` or after deduplication.
2. Create `citation_count` from OpenAlex `cited_by_count`.
3. Preserve Crossref `is_referenced_by_count` and OpenAlex `referenced_works_count` in `publication_count_audit.csv`.
4. Normalize `funder_id` into `funder_identifier`.
5. Deduplicate multi-value text fields: `concepts`, `topics`, `funder_name`, `funder_doi`, `funder_identifier`, `funder_award`, `source_set_specs`, `raw_identifiers`.
6. Move `references_json` into a sidecar table if reference-level analysis is needed.
7. Drop event fields from the final main dataset unless a separate conference/event analysis is required.
8. Drop `is_referenced_by_count`, `referenced_works_count`, and `raw_source_json` from the final main dataset.

## Final Verdict

The last 26 columns contain useful enrichment and provenance metadata. The clean final dataset should keep the OpenAlex open-access/topic fields, selected Crossref funding fields, best-available count fields with divergence flags, and local provenance fields, while dropping event fields from the main table and moving heavy raw reference JSON plus source-specific count details out of the main publication dataset.
