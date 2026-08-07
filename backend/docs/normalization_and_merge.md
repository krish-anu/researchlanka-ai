# Dataset Merge Rules

The common-dataset merge creates one canonical publication row from normalized
Crossref, OpenAlex, repository, and SLJOL records. These rules define when
records are allowed to merge, which value wins for each field, and what evidence
must remain auditable.

Sources are not treated as equal, and no external source is treated as absolute
truth for every field.

Default source roles:

- OpenAlex: primary discovery and analytics backbone.
- Crossref: DOI-backed and publisher-deposited metadata evidence.
- Local repositories and SLJOL: national coverage, local-only records, and
  provenance.
- ResearchLanka output tables: final operational canonical dataset for the app.

The executable implementation is
`src/pipeline/kaggle_merge_common_dataset.py`. The runbook entry is
`docs/PIPELINE_RUNBOOK.md` section 3.

## 1. Identity Rules

| Rule ID | Rule | Output behavior |
|---|---|---|
| RM-001 | Normalize DOI values before matching. DOI URLs, `doi:` prefixes, case, spaces, and trailing punctuation are removed. Only values matching the `10.<registrant>/<suffix>` DOI shape are accepted. | Invalid or empty DOI values are ignored for automatic identity matching. |
| RM-002 | Auto-merge records with the same normalized DOI. | The merge key is `doi:<normalized_doi>` and the merge method is `doi`. |
| RM-003 | Do not auto-merge DOI-less records across sources by title, year, author, URL, or venue alone. | A DOI-less record with a source identifier is kept under `source_record:<source_dataset>|<source_record_id>`. |
| RM-004 | Preserve DOI-less records that also lack a source record ID. | The record is kept under `row:<input_row_number>` so it cannot collapse into another weakly identified row. |
| RM-005 | Generate manual-review candidates for DOI-less records that share normalized title, publication year, and first author. | Candidate groups are written to `common_publications_manual_review_candidates.csv` with review method `title_year_first_author`. |
| RM-006 | Generate lower-confidence manual-review candidates for DOI-less records that share normalized title and publication year but have no usable first author. | Candidate groups are written with review method `title_year`. |
| RM-007 | Title, year, and author similarities are review signals only. | They must not create automatic merges unless a future rule explicitly changes this document and the implementation. |
| RM-008 | Fuzzy title matches are review-only even when enabled in the framework config. | `fuzzy_title_match.threshold` creates `manual_review` candidates; it does not remove records. |

## 2. Value Selection Rules

| Rule ID | Rule | Output behavior |
|---|---|---|
| RM-010 | Normalize comparable values before conflict checks. | DOI, title, year, boolean, integer, and multi-value fields are compared in normalized form. |
| RM-011 | Select scalar field values by field-specific source policy when the field has a policy. | The first non-empty value from the highest-priority source wins. |
| RM-012 | Use record completeness as a tie-breaker. | Within the same source priority, rows with more non-empty common fields are searched first. |
| RM-013 | Use completeness-only ordering for scalar fields without an explicit source policy. | The first non-empty value from the most complete row wins. |
| RM-014 | Union multi-value fields instead of selecting one source. | Values are split on semicolons, blanks are dropped, duplicates are removed, and the ordered unique values are joined with `; `. |
| RM-015 | Always retain source provenance as unioned evidence. | `source_dataset`, `source_institution_id`, `source_record_id`, `source_datestamp`, `source_set_specs`, and `raw_identifiers` preserve all non-empty source evidence. |
| RM-016 | Treat empty containers and placeholder strings as blank. | `""`, `nan`, `none`, `null`, `na`, `n/a`, `[]`, and `{}` do not win field selection. |

Multi-value columns are:

`source_dataset`, `source_institution_id`, `source_record_id`,
`source_datestamp`, `authors`, `author_names`, `author_affiliations`,
`author_orcids`, `sri_lankan_authors`, `contributors`, `editors`,
`institutions`, `sri_lankan_institutions`, `countries`, `issn`, `keywords`,
`concepts`, `topics`, `funder_name`, `funder_doi`, `funder_id`,
`funder_award`, `event_sponsor`, `source_set_specs`, and `raw_identifiers`.

## 3. Default Field Source Policy

The default policy applies only to scalar fields listed below. Any common field
not listed here follows RM-013.

| Field group | Fields | Default priority |
|---|---|---|
| DOI | `doi` | Crossref -> OpenAlex -> SLJOL -> repositories |
| OpenAlex identifier | `openalex_id` | OpenAlex only |
| Core citation metadata | `title`, `publication_year`, `publication_date`, `published_date`, `type`, `subtype`, `publication_type` | Crossref -> OpenAlex -> SLJOL -> repositories |
| Abstract | `abstract` | Crossref -> repositories -> SLJOL -> OpenAlex |
| Publisher and venue | `publisher`, `publisher_location`, `journal`, `container_title`, `source_name`, `issn_l`, `volume`, `issue`, `page`, `first_page`, `last_page`, `article_number` | Crossref -> OpenAlex -> SLJOL -> repositories |
| Source type and language | `source_type`, `language` | OpenAlex -> Crossref -> SLJOL -> repositories |
| Rights and license | `rights` | repositories -> SLJOL -> Crossref -> OpenAlex |
| License details | `license`, `license_url` | Crossref -> OpenAlex -> repositories -> SLJOL |
| Open access status | `oa_status`, `is_oa` | OpenAlex -> Crossref -> SLJOL -> repositories |
| Citation count | `cited_by_count` | OpenAlex -> Crossref |
| Crossref citation count | `is_referenced_by_count` | Crossref only |
| Reference count | `reference_count` | Crossref -> OpenAlex |
| OpenAlex reference count | `referenced_works_count` | OpenAlex only |
| References | `references_json` | Crossref -> OpenAlex -> SLJOL -> repositories |
| Topic classification | `primary_topic`, `primary_field`, `primary_subfield`, `primary_domain` | OpenAlex only |
| Conference or event | `event_name`, `event_acronym`, `event_location`, `event_start_date`, `event_end_date` | Crossref -> OpenAlex -> SLJOL -> repositories |

Funding fields that are multi-value, such as `funder_name`, `funder_doi`,
`funder_id`, and `funder_award`, are unioned under RM-014.

## 4. Audit Rules

| Rule ID | Rule | Output behavior |
|---|---|---|
| RM-020 | Write one merge-log row for every final row, including singletons. | `common_publications_merge_log.csv` records action, merge method, merge key, source datasets, source record IDs, final key fields, completeness, conflicts, and input row numbers. |
| RM-021 | Log normalized field conflicts for automatic merge groups. | `conflict_fields` lists common fields, excluding provenance fields and `raw_source_json`, where more than one normalized value exists. |
| RM-022 | Audit citation-count divergence between OpenAlex and Crossref. | `citation_count_difference_oa_minus_crossref` is OpenAlex `cited_by_count` minus Crossref `is_referenced_by_count`; `citation_count_divergence_flag` is true when the absolute difference is at least 10. |
| RM-023 | Audit reference-count divergence between OpenAlex and Crossref. | `reference_count_difference_oa_minus_crossref` is OpenAlex `referenced_works_count` minus Crossref `reference_count`; `reference_count_divergence_flag` is true when the difference is non-zero. |
| RM-024 | Preserve all normalized source rows before deduplication. | `common_publications_all_records.csv` remains available for source-level inspection. |
| RM-025 | Flag automatic DOI merge groups that cross finalized duplicate-review thresholds. | Merge log fields `duplicate_threshold_review_flag`, `duplicate_threshold_review_reason`, `duplicate_title_similarity_min`, `duplicate_publication_year_span`, and `duplicate_artifact_title_flag` identify audit-required groups. |

## 5. Duplicate Thresholds

| Threshold | Value | Action |
|---|---:|---|
| DOI auto-merge normalized DOI equality | 100% exact DOI key match | Auto-merge, with merge-log audit. |
| Non-DOI automatic merge threshold | Disabled | Never auto-merge on title, year, author, URL, venue, or fuzzy score alone. |
| Exact title + same year + first author | Exact normalized match | Manual review only. |
| Exact title + same year, no first author | Exact normalized match | Manual review only. |
| Framework fuzzy title score | Configurable, default 90 | Manual review only, requiring compatible publication year and first-author evidence when configured. |
| Same-DOI title-similarity review threshold | Below 0.80 | Keep the DOI merge, but flag for audit in `common_publications_merge_log.csv`. |
| Same-DOI publication-year span threshold | Greater than 1 year | Keep the DOI merge, but flag for audit. |
| Artifact-title threshold | Title contains `additional file`, `supplementary`, `supplemental`, `figure`, `fig.`, `table`, `dataset`, `appendix`, `annex`, `image`, or `plate` | Flag for audit. |

## 6. Override Rules

Field source priority can be overridden at runtime:

```bash
python scripts/processing/kaggle_merge_common_dataset.py --field-source-policy policy.json
```

Example override:

```json
{
  "title": ["openalex", "crossref", "sljol", "repositories_combined"],
  "abstract": ["crossref", "repositories_combined", "sljol", "openalex"]
}
```

Override constraints:

- The policy file must be a JSON object.
- Keys must be valid common-schema field names.
- Each value must be a non-empty list of source dataset names.
- Overrides change only field-value priority. They do not change automatic
  identity matching, manual-review candidate generation, conflict logging, or
  provenance retention.

## 7. Change Control

- Any rule that changes automatic identity matching must update this document,
  implementation tests, and downstream runbook language.
- Any rule that changes canonical field priority must update this document and
  the built-in field source policy.
- Any rule that removes or suppresses evidence from the canonical dataset must
  keep that evidence in `common_publications_all_records.csv`, the merge log, a
  sidecar table, or raw source JSON.
