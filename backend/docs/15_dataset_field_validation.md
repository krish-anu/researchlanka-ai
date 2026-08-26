# Dataset Field Validation

Four validators over the analysis dataset: authors, institutions, citations and
collaboration. Each answers a different question, and each reports counted
metrics, quality gates with an explicit threshold, and a sample of the offending
records.

Code: [`src/quality/validate_analysis_dataset.py`](../src/quality/validate_analysis_dataset.py).
Tests: [`tests/test_validate_analysis_dataset.py`](../tests/test_validate_analysis_dataset.py).

Nothing here changes data. A validator that finds a problem reports it; fixing it
belongs to the pipeline stage that produced the column.

---

## Running

```bash
make validate-dataset PYTHON=python
# or
python -m src.quality.validate_analysis_dataset
python -m src.quality.validate_analysis_dataset --checks citations,collaboration
python -m src.quality.validate_analysis_dataset --strict     # exit 1 on a failed gate
```

The input defaults to the most-normalized dataset present, in this order:

1. `common_publications_final_author_disambiguated.csv`
2. `common_publications_final_institution_normalized.csv`
3. `common_publications_final.csv`

Later stages add the columns the institution and collaboration validators need,
so validating the furthest-along dataset gives the most complete answer. A
validator whose columns are absent reports the gate as `skipped` rather than
failing it.

The dataset is streamed once and every validator sees every row, so adding a
check costs no extra pass.

## Output

Three files per check, in `data/reports/validation/`:

| File | Contents |
|---|---|
| `<check>_validation_summary.csv` | Every metric, issue count and gate status. |
| `<check>_validation_gates.csv` | One row per gate: value, threshold, comparison, pass/FAIL. |
| `<check>_validation_issues.csv` | Offending records: `record_id`, `column`, `issue`, `value`, `detail`. |

Issue samples are capped by `--max-issues` (default 5,000) so a systematic fault
cannot produce a 200MB file. **Counts stay complete** whatever the cap —
`issues_truncated` in the summary says whether the sample was cut. Every issue
carries a record identifier (`record_number`, else `openalex_id`, `doi`,
`source_record_id`, else the row number), so a number can always be traced back
to rows.

---

## 1. Authors

| Check | Issue |
|---|---|
| Authors present | `missing_authors` |
| Names parse into surname + given names | `unparseable_author_name` |
| Placeholders occupying an author slot | `placeholder_author_name` ("Anonymous", "et al", "Unknown", …) |
| Names long enough to be an unsplit list | `overlong_author_name` (>120 chars) |
| Same person twice in one record | `duplicate_author_in_record` |
| `author_count` agrees with the names | `author_count_mismatch` |
| ORCID check digit | `invalid_orcid` (ISO 7064 MOD 11-2) |
| ORCID repeated in one record | `duplicate_orcid_in_record` |
| ORCID list length vs author count | `orcid_count_not_aligned_with_authors` |
| `author_ids` count vs parseable names | `author_id_count_mismatch` |

Gates: `author_presence_rate` ≥ 0.90, `author_name_parse_rate` ≥ 0.98,
`author_count_agreement_rate` ≥ 0.95, `orcid_validity_rate` ≥ 0.95.

Unaligned ORCID lists are **reported, not failed**: sources compact the list, so
a record with five authors and two ORCIDs is normal. It does mean those ORCIDs
cannot be tied to author positions — see
[14_author_disambiguation.md](14_author_disambiguation.md) §3.

## 2. Institutions

| Check | Issue |
|---|---|
| Institutions present | `missing_institutions` |
| Affiliation text with no institution extracted | `affiliation_present_without_institution` |
| `national_institution_ids` exist in the registry | `unknown_registry_identifier` |
| Country codes are real | `unrecognised_country` |
| National institution implies the national country | `national_institution_without_national_country` |
| `institution_source` vocabulary | `unknown_institution_source` |

Gates: `institution_coverage` ≥ 0.85, `unknown_registry_identifiers` == 0,
`country_validity_rate` ≥ 0.99, `unknown_institution_source_values` == 0.

Registry checks need `configurations/sri_lanka/institutions.csv`
(`--registry-csv`). Without it those gates are skipped and
`registry_loaded` is `False`. Resolution uses the same alias index the
normalization pipeline uses, so this measures the registry as it actually
behaves — see [10_institution_and_affiliation_standardization.md](10_institution_and_affiliation_standardization.md).

## 3. Citations

| Check | Issue |
|---|---|
| Counts are numbers | `citation_count_not_numeric`, `citation_count_not_an_integer` |
| Counts are non-negative | `negative_citation_count`, `negative_reference_count` |
| Counts are plausible | `implausible_citation_count` (>500,000), `implausible_reference_count` (>10,000) |
| Publication year is plausible | `implausible_publication_year` (outside 1900–next year) |
| Citations on a work not yet published | `citations_on_future_publication` |

Gates: `citation_numeric_validity_rate` == 1.0, `negative_citation_counts` == 0,
`implausible_citation_counts` == 0, `negative_reference_counts` == 0.

Missing and zero are counted separately (`rows_missing_citation_count` vs
`zero_citation_rows`). They mean different things — no data versus no citations —
and collapsing them would overstate coverage.

## 4. Collaboration

`collaboration_type` and `collaboration_scope` are **derived** fields, so this
validator checks them against the fields they were derived from. A disagreement
is a pipeline defect, not a data-quality observation, which is why the gates are
`== 0` rather than a rate.

| Check | Issue |
|---|---|
| Type vocabulary | `unknown_collaboration_type` |
| Scope vocabulary | `unknown_collaboration_scope` |
| Scope recomputes from type | `scope_does_not_match_type` |
| International implies a foreign country | `international_without_foreign_country` |
| Multi-institution implies ≥2 institutions | `multi_institution_without_two_institutions` |
| Single-institution implies exactly 1 | `single_institution_count_mismatch` |
| Unresolved implies unresolved names | `unresolved_without_unresolved_institutions` |
| Not-national implies no national ids | `not_national_with_national_institutions` |

Gates: `collaboration_presence_rate` ≥ 0.99, `unknown_collaboration_types` == 0,
`scope_type_mismatches` == 0, `collaboration_inconsistencies` == 0.

Country *validity* is the institution validator's job; this one only checks
internal consistency, so a record is never flagged twice for the same fault.

---

## Reading a failure

A failed gate names the metric, its value and the threshold:

```
collaboration.scope_type_mismatches: 1.0000 == 0
```

Open `collaboration_validation_issues.csv`, filter to that issue, and the
`record_id` and `detail` columns say which records and why. `--strict` turns any
failure into a non-zero exit, for use in a pipeline; without it the run reports
and exits 0.
