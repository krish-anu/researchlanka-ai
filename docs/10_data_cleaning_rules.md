# Formal Data-Cleaning Rules

**Status:** Prepared for implementation and audit use  
**Applies to:** National Research Analytics Framework publication records  
**Primary datasets:** OpenAlex, Crossref, SLJOL, local institutional repositories, and merged common publication outputs  
**Primary implementation paths:** `research_analytics/cleaning.py`, `research_analytics/validation.py`, `research_analytics/deduplication.py`, `src/pipeline/build_final_common_dataset.py`, and `src/pipeline/build_analysis_ready_dataset.py`

## 1. Purpose

These rules define the formal data-cleaning standard for Sri Lanka national
research publication metadata. They are intended to make cleaning decisions
consistent, reproducible, auditable, and suitable for national-level analytics.

The rules cover normalization, validation, enrichment readiness, deduplication
support, sidecar audit outputs, and analysis-ready preprocessing. They do not
replace field-level merge policy. Source priority decisions remain governed by
`docs/normalization_and_merge.md`.

## 2. Cleaning Principles

| Principle | Requirement |
|---|---|
| Reproducibility | Every cleaning rule must be deterministic and runnable in the pipeline without manual interpretation. |
| Provenance preservation | Raw source values must remain available through `raw_record`, `source_specific_metadata`, sidecar files, or issue logs when values are transformed or removed from the main dataset. |
| Non-destructive cleaning | Cleaning must normalize and flag records by default. Records should not be silently deleted because a field is missing or malformed. |
| Field-level authority | Cleaning must not invent bibliographic truth. When sources disagree, use the configured merge policy and retain conflict evidence. |
| Analysis readiness | Values used for search, grouping, filtering, and statistics must have normalized forms suitable for stable comparisons. |
| National analytics fit | Rules must support country, institution, author, publication, citation, collaboration, and topic analytics. |

## 3. Standard Field Scope

Cleaning applies to the standard publication schema fields where present:

| Field group | Fields |
|---|---|
| Identity | `publication_id`, `source_name`, `source_record_id`, `doi`, `openalex_id`, `title`, `normalized_title`, `url`, `pdf_url` |
| Bibliographic | `publication_year`, `publication_date`, `publication_type` or `type`, `journal`, `publisher`, `volume`, `issue`, `first_page`, `last_page`, `article_number`, `language` |
| People and institutions | `authors`, `author_count`, `author_affiliations`, `author_orcids`, `institutions`, `sri_lankan_institutions`, `countries` |
| Content | `abstract`, `keywords`, `concepts`, `topics`, `primary_topic`, `primary_field`, `primary_subfield`, `primary_domain` |
| Access and impact | `oa_status`, `is_oa`, `license`, `license_url`, `citation_count`, `reference_count` |
| Funding | `funder_name`, `funder_doi`, `funder_identifier`, `funder_award` |
| Provenance and audit | `source_dataset`, `source_specific_metadata`, `raw_record`, `raw_identifiers`, `processing_status`, `_provenance` |

## 4. Formal Rules

### DC-001: Blank and Null Normalization

Values must be treated as missing when they are `None`, empty strings,
whitespace-only strings, `NaN`, empty lists, or common textual null markers such
as `nan`, `none`, `null`, `na`, `n/a`, `[]`, and `{}`.

Acceptance criteria:

- Missing values are represented consistently as `None`, `pd.NA`, or an empty
  list depending on the target field type.
- Textual null markers must not appear as analytical values in final outputs.
- Missingness must be reported rather than used as a silent reason to drop a row.

### DC-002: Whitespace and Text Cleanup

Text fields must be stripped and internal whitespace must be collapsed to a
single space.

Acceptance criteria:

- Leading and trailing whitespace is removed.
- Newlines, tabs, and repeated spaces do not affect equality checks.
- Empty cleaned text becomes missing.

### DC-003: Title Normalization

Publication titles must be normalized for display and matching.

Required transformations:

- Decode nested HTML entities and known source-specific entity errors.
- Preserve useful inline tag content while removing markup.
- Collapse whitespace.
- Remove spacing before closing punctuation and after opening punctuation.
- Produce `normalized_title` or equivalent title key by case-folding and removing
  punctuation while preserving alphanumeric characters, combining marks, and
  supported Unicode word joiners.

Acceptance criteria:

- A title containing HTML tags must produce readable plain text.
- Equivalent title spellings with only case, markup, or punctuation differences
  must produce the same title key where reasonable.
- The original title remains recoverable through source provenance.

### DC-004: DOI Normalization and Validation

DOI values must be normalized before validation, deduplication, merge decisions,
and publication-key generation.

Required transformations:

- Trim whitespace.
- Convert to lowercase.
- Remove leading DOI URL prefixes such as `https://doi.org/`,
  `http://dx.doi.org/`, and `doi:`.
- Remove internal spaces.
- Remove trailing punctuation that is not part of the DOI.

Validation rule:

- A syntactically valid DOI must match `10.<4-9 digits>/<suffix>`.

Acceptance criteria:

- Invalid DOI values are flagged or removed from cleaned identifier cells, not
  treated as valid identity evidence.
- Duplicate DOI checks must use normalized DOI values.
- DOI-backed matches may be auto-merged only when the deduplication policy allows
  DOI automatic merge.

### DC-005: Date and Year Normalization

Publication dates must be normalized to the most precise valid ISO-like value
available: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`.

Required transformations:

- Accept Python `date` and `datetime` values.
- Parse Crossref-style `date-parts` structures.
- Parse common string forms such as `YYYY`, `YYYY-M`, `YYYY-M-D`, and slash dates.
- Derive `publication_year` from `publication_date` when only date-like evidence
  is available.
- Fall back from invalid month/day precision to the nearest valid higher-level
  precision rather than creating impossible dates.

Validation rule:

- A publication year outside the configured minimum and maximum range is invalid.

Acceptance criteria:

- `publication_year` is an integer where available.
- Invalid date strings do not enter final date fields as raw text.
- Ambiguous or invalid date values are flagged through validation or issue logs.

### DC-006: Author Name Normalization

Author fields must be normalized for analysis while preserving source evidence.

Required transformations:

- Split list-like author cells on semicolons, or commas where no semicolon is
  present.
- Remove empty author entries.
- Convert `Family, Given` to `Given Family` when exactly one comma separates the
  name.
- Title-case names that are entirely uppercase.
- Create an `authors_clean` analysis field when building the analysis-ready
  dataset.

Acceptance criteria:

- Author cleaning must not remove the original `authors` field.
- Missing ORCID evidence must be represented by
  `author_disambiguation_available_flag = False` when authors are present and
  ORCIDs are absent.
- Author strings must not be used as the sole basis for automatic record merges.

### DC-007: Institution Normalization

Institution fields must be normalized as list-like values and prepared for
registry-based resolution.

Required transformations:

- Split institution cells on semicolons, or commas where no semicolon is present.
- Trim institution names.
- Remove empty entries.
- Preserve unresolved names for later review.

Acceptance criteria:

- `resolved_institutions` and `unresolved_institutions` must be kept separately
  when entity resolution is enabled.
- National institution identifiers must come from the configured institution
  registry, not from free-text inference alone.
- Sri Lankan institution analysis must use resolved or explicitly configured
  national institution evidence where available.

### DC-008: Multi-Value Field Normalization

Semicolon-separated analytical fields must be normalized and deduplicated.

Applies to:

- `concepts`
- `topics`
- `keywords`
- `funder_name`
- `funder_doi`
- `funder_identifier`
- `funder_award`
- `source_set_specs`
- `raw_identifiers`

Required transformations:

- Split on semicolons.
- Trim each value.
- Normalize DOI-like values through DOI normalization.
- Normalize ROR-like values as lowercase URL identifiers.
- Remove duplicate values using case-insensitive comparison.
- Rejoin values with `; `.

Acceptance criteria:

- Repeated values differing only by case or surrounding spaces appear once.
- `funder_doi` keeps DOI values only.
- Empty multi-value outputs become missing.

### DC-009: URL and External Identifier Normalization

URL-like identifiers must be normalized for stable comparison.

Required transformations:

- Trim whitespace.
- Remove safe trailing punctuation.
- Lowercase URL scheme and host.
- Remove URL fragments.
- Force HTTPS for configured trusted hosts when required.
- Normalize OpenAlex IDs to canonical `https://openalex.org/<ID>` form.
- Normalize ORCID values to `https://orcid.org/<ORCID>` form.
- Normalize ISSN values to `NNNN-NNNN` or `NNNN-NNNX` form.

Acceptance criteria:

- Invalid ORCID and ISSN values are removed from cleaned identifier cells and
  recorded in identifier issue logs.
- Identifier normalization must not modify unrelated free text.
- Canonical identifiers must be used for downstream joins and search.

### DC-010: Numeric Field Normalization

Numeric analytical fields must be converted to numeric types.

Applies to:

- `publication_year`
- `author_count`
- `citation_count`
- `reference_count`
- `citation_count_difference_oa_minus_crossref`
- `reference_count_difference_oa_minus_crossref`

Acceptance criteria:

- Non-numeric values become missing and are recorded in numeric issue logs.
- Count fields must be integer-like after cleaning.
- Missing count values must not be converted to zero unless zero is explicitly
  present in the source data.

### DC-011: Boolean and Controlled-Value Normalization

Boolean-like fields must be normalized to true, false, or missing.

Applies to:

- `is_oa`
- `citation_count_divergence_flag`
- `reference_count_divergence_flag`

Required true values:

- `true`, `t`, `yes`, `y`, `1`

Required false values:

- `false`, `f`, `no`, `n`, `0`

Additional controlled values:

- `oa_status` must be case-folded, whitespace-normalized, hyphenated, and set to
  `unknown` when missing.
- `license` must be case-folded and normalized with hyphen separators.

Acceptance criteria:

- Unrecognized boolean values become missing.
- Missing open-access status is represented as `unknown`, not as a blank
  analytical category.

### DC-012: Required Field Validation

Mapped records must satisfy the configured validation rules.

Default requirements:

- `title` is required.
- At least one identifying field is required from `doi`, `authors`,
  `publication_year`, or `source_record_id`.

Acceptance criteria:

- Validation reports list missing required columns and missing value percentages.
- Record-level validation errors identify missing required fields, invalid DOI
  values, and invalid publication years.
- Failed validation should produce review evidence before records are excluded
  from analysis.

### DC-013: Duplicate Candidate Detection

Duplicate detection must use normalized comparison keys.

Required matching rules:

- DOI matches use normalized DOI values.
- Exact title matches use normalized title keys.
- Exact title matches require the same publication year unless configured
  otherwise.
- DOI matches may be marked `auto_merge` only when configured.
- Exact title matches must be sent to manual review.

Acceptance criteria:

- Duplicate candidate outputs identify both record indexes, match type,
  confidence, and merge decision.
- Uncertain matches must not be merged without review.
- Source records remain traceable after deduplication.

### DC-014: Source Conflict and Merge Audit

Cleaning must preserve evidence needed to understand cross-source disagreement.

Required audit behavior:

- Use field-level source policy for canonical value selection.
- Retain conflicting normalized values in merge logs.
- Retain source-specific citation and reference counts in count audit sidecars.
- Report citation and reference divergence flags.

Acceptance criteria:

- Citation divergence is flagged where OpenAlex and Crossref differ by the
  configured threshold.
- Reference divergence is flagged where source comparison is available.
- Difference and flag fields are blank when the required source pair is absent.

### DC-015: Column Retention and Sidecar Rules

Final dataset construction must keep the main dataset analytically compact while
preserving detailed evidence in sidecar files.

Required behavior:

- Keep best-available citation and reference counts in the main dataset.
- Move source-specific count comparison evidence to
  `publication_count_audit.csv`.
- Move Crossref reference-list payloads to `publication_references.csv`.
- Drop duplicate, derivable, constant, sparse, or raw audit columns from the main
  dataset only when documented in final column-decision reports.

Acceptance criteria:

- Dropped columns are listed in the final dataset summary output.
- Sidecar outputs include publication keys linking back to the main dataset.
- Raw JSON payloads are not retained in the main analytical table unless needed
  for active analysis.

### DC-016: Search and Analysis-Ready Text

Search-oriented text columns must be derived without overwriting display text.

Required derived fields:

- `title_search_text`
- `abstract_search_text`
- `keywords_search_text`

Acceptance criteria:

- Search text is case-folded.
- Keyword search text is split, deduplicated, and rejoined consistently.
- Missing abstract values produce `abstract_missing_flag`.

### DC-017: Missingness Flags for Naturally Sparse Fields

Naturally sparse analytical fields must receive explicit missingness flags in
analysis-ready outputs.

Applies to:

- `abstract`
- `funder_name`
- `funder_doi`
- `funder_identifier`
- `funder_award`
- `license`
- `license_url`
- `pdf_url`
- `author_orcids`
- `article_number`

Acceptance criteria:

- Each configured sparse field receives `<field>_missing_flag` when present.
- Missingness counts are written to preprocessing issue logs.
- Sparse fields are not treated as failed required fields unless configured.

### DC-018: Processing Status and Provenance

Every framework record must expose processing status and rule provenance.

Required behavior:

- Schema mapping sets `processing_status = transformed`.
- Cleaning sets `processing_status = cleaned`.
- `_provenance.cleaning_rules_applied` lists enabled cleaning rules applied to a
  record.

Acceptance criteria:

- Pipeline consumers can distinguish raw, transformed, cleaned, and final
  analysis-ready records.
- Rule provenance is available for audit and debugging.

## 5. Issue Logs and Audit Outputs

Cleaning must produce or preserve the following outputs when the relevant stage
is executed:

| Output | Purpose |
|---|---|
| `common_publications_merge_log.csv` | Cross-source conflicts and merge decisions. |
| `publication_count_audit.csv` | Source-specific citation and reference count evidence. |
| `publication_references.csv` | Reference-list sidecar extracted from Crossref payloads. |
| `common_publications_final_summary.csv` | Final-row, final-column, sidecar, and dropped-column summary. |
| `preprocessing_issues_*/text_issues.csv` | Missing or normalized title, abstract, and keyword evidence. |
| `preprocessing_issues_*/identifier_issues.csv` | Invalid or normalized DOI, OpenAlex, URL, ORCID, ISSN, and funding identifiers. |
| `preprocessing_issues_*/numeric_issues.csv` | Non-numeric values in numeric fields. |
| `preprocessing_issues_*/missingness_issues.csv` | Missingness counts for naturally sparse fields. |
| `preprocessing_issues_*/author_issues.csv` | Author-name normalization and missing author-disambiguation evidence. |
| `preprocessing_issues_*/oa_license_issues.csv` | Open-access and license normalization or missingness. |

## 6. Minimum Quality Gates

Before a cleaned dataset is accepted for national analytics, the following gates
must be checked:

| Gate | Rule |
|---|---|
| Required identity | Each record has a title and at least one configured identifying field. |
| DOI syntax | Non-blank DOI values are valid after DOI normalization. |
| Year range | Non-blank publication years fall inside the configured valid year range. |
| Duplicate evidence | Duplicate DOI and duplicate title-key counts are reported. |
| Source conflict evidence | Merge logs are produced when multi-source values conflict. |
| Count divergence | Citation/reference divergence flags are available when OpenAlex and Crossref are both present. |
| Audit sidecars | Reference and count sidecars are written when source fields exist. |
| Issue logs | Analysis-ready preprocessing issue logs are written for normalized, invalid, and missing values. |

## 7. Rule-to-Code Traceability

| Rule IDs | Primary code path |
|---|---|
| DC-001, DC-002 | `research_analytics/cleaning.py`, `src/pipeline/build_analysis_ready_dataset.py` |
| DC-003 | `research_analytics/cleaning.py` |
| DC-004 | `research_analytics/cleaning.py`, `src/utils/doi.py` |
| DC-005 | `research_analytics/cleaning.py`, `research_analytics/validation.py` |
| DC-006, DC-009, DC-010, DC-011, DC-016, DC-017 | `src/pipeline/build_analysis_ready_dataset.py` |
| DC-007, DC-018 | `research_analytics/cleaning.py`, `research_analytics/schema.py` |
| DC-008, DC-014, DC-015 | `src/pipeline/build_final_common_dataset.py` |
| DC-012 | `research_analytics/validation.py` |
| DC-013 | `research_analytics/deduplication.py` |

## 8. Governance Notes

- Any new cleaning rule must receive a stable rule ID.
- Any rule that changes canonical analytical values must identify its source
  field, target field, transformation, and audit output.
- Rules that remove values from the main dataset must preserve the original
  evidence in raw provenance, sidecar tables, or issue logs.
- Changes to merge source priority must be documented in
  `docs/normalization_and_merge.md`, not only in cleaning code.
- Changes to dropped columns must be documented in the relevant final
  column-decision report and reflected in final dataset summaries.
