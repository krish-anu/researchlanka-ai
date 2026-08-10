# Metadata-Quality Limitations

**Status:** Complete  
**Applies to:** OpenAlex, Crossref, SLJOL, local repository harvests, merged common datasets, analysis-ready outputs, and PostgreSQL `final_publications` loads  
**Related docs:** [03_missing_values_analysis.md](03_missing_values_analysis.md), [04_metadata_completeness_analysis.md](04_metadata_completeness_analysis.md), [05_conflicting_metadata_analysis.md](05_conflicting_metadata_analysis.md), [06_field_level_data_quality.md](06_field_level_data_quality.md), [10_data_cleaning_rules.md](10_data_cleaning_rules.md)

## 1. Purpose

This document records the known limits of the metadata corpus so users do not
over-interpret the final dataset as a complete or perfectly authoritative
national publication registry. The pipeline is designed to preserve evidence,
normalize values, log conflicts, and expose missingness, but it cannot create
metadata that no source provides or verify every bibliographic claim manually.

Use this document when writing reports, interpreting dashboards, planning
additional enrichment, or comparing institutions, fields, publication types, and
years.

## 2. High-Level Limitation Summary

| Area | Limitation | Practical implication |
|---|---|---|
| Coverage | The corpus combines large public sources and harvestable local repositories, but blocked, stale, private, or technically broken sources remain incomplete. | Counts are best read as "observed in the harvested sources," not definitive national totals. |
| DOI identity | OpenAlex and Crossref are DOI-rich, while local repositories are often DOI-poor. | DOI-only matching undercounts local theses, grey literature, and repository-only records. |
| Field completeness | Content, funding, ORCID, license, event, and keyword fields are sparse or source-specific. | Analyses using those fields must report denominator and missingness. |
| Source conflicts | Shared DOI records can disagree on publisher, journal, ISSN, type, year, citation count, and reference count. | Use configured field-level policy and conflict logs; do not treat a single exported value as the only source truth. |
| Source bias | OpenAlex, Crossref, and repositories have different inclusion rules and metadata incentives. | International journal articles are better represented than some local, older, non-DOI, thesis, conference, and grey-literature outputs. |
| Timeliness | Source databases and repository indexes update on different schedules. | Recent-year counts may lag, and source snapshots should be dated in reports. |
| Normalization | Cleaning standardizes values for analysis but does not guarantee semantic equivalence. | String variants can remain, and some exact-string "conflicts" are formatting differences rather than true bibliographic errors. |

## 3. Corpus Coverage Limits

The dataset is a best-effort integration of reachable and usable sources. It is
not a legal deposit record, university-submitted census, or exhaustive national
research inventory.

Known coverage limits:

- Repository coverage depends on public access routes. Some repositories expose
  OAI-PMH, some require DSpace REST, some need HTML metadata extraction, and
  some remain blocked or empty despite live landing pages.
- A live OAI-PMH endpoint does not guarantee harvestable records. Several
  repositories have stale or empty OAI indexes even when `Identify` and
  `ListMetadataFormats` work.
- Web application firewalls, disabled OAI endpoints, intranet redirects, broken
  TLS, pagination faults, and unbuilt indexes can prevent complete automated
  collection.
- SLJOL is represented through Crossref DOI metadata rather than direct OJS page
  access. This gives stable bibliographic coverage for DOI-bearing articles but
  usually does not recover abstracts or keywords.
- Institutional repository records may include theses, reports, working papers,
  book chapters, learning materials, and other local objects that global
  bibliographic indexes do not consistently track.
- Publications affiliated with Sri Lanka but missing clear Sri Lankan
  institution evidence in source metadata may be absent from nationally filtered
  extracts.

Required reporting language:

```text
Counts represent records observed in the configured OpenAlex, Crossref, SLJOL,
and harvestable local repository sources at the time of collection. They should
not be interpreted as complete national production totals without institutional
verification.
```

## 4. Source-Specific Limitations

| Source | Strengths | Limitations |
|---|---|---|
| OpenAlex | Strong backbone for DOI-bearing scholarly works, authors, institutions, citations, topics, open-access status, and broad discovery. | Sparse abstracts, ORCIDs, funding details, event details, and source-local provenance; topic classifications are model/index-derived and should not be treated as official classifications. |
| Crossref | DOI-complete by construction for requested DOI/prefix workflows; strong publisher, venue, license, reference-list, funding, event, and deposited metadata evidence. | Covers only registered DOI works; publisher deposits vary in completeness and quality; citation/reference counts differ from OpenAlex; abstracts are available only for a subset. |
| SLJOL via Crossref | Stable DOI route for SLJOL articles under the NSF DOI prefix. | Crossref records usually lack article abstracts and subject keywords; direct OJS metadata was not used where automated access was blocked. |
| Local repositories | Best evidence for local-only, no-DOI, thesis, and institutional records; often include abstracts and repository provenance. | DOI, venue, ISSN, license, ORCID, funding, and normalized type coverage vary sharply by institution; metadata may be free text, incomplete, duplicated, or locally encoded. |

## 5. Field-Level Limitations

### Identity Fields

- `doi`: OpenAlex is high coverage and Crossref is DOI-complete by design, but
  local repository DOI coverage is low overall. Existing analysis measured local
  DOI coverage at 41.78%, with several repositories at 0%.
- `title`: Title coverage is very high, but title strings can still differ by
  punctuation, capitalization, subtitles, transliteration, markup, or repository
  data-entry practices.
- `publication_year` and `publication_date`: Year coverage is strong, but exact
  dates can differ by online publication date, issue date, deposit date, and
  repository accession date.
- `source_record_id`: Source IDs are stable only within their source. They are
  not globally unique unless paired with `source_dataset` or source provenance.

### People and Institutions

- `authors`: Author names are resolved onto `author_ids` using ORCID,
  affiliation and coauthor evidence
  ([14_author_disambiguation.md](14_author_disambiguation.md)), but resolution
  is not complete. Two people sharing one exact spelling remain one identity,
  and identities built from the name alone carry a `low` confidence and a review
  flag. Use `author_disambiguation_level` and `ambiguous_author_flag` when
  author-level counts matter.
- `author_orcids`: ORCID coverage is sparse and mostly comes from Crossref when
  deposited. Missing ORCID does not mean the author lacks an ORCID.
- `institutions`: Institution extraction depends on source affiliation metadata,
  repository source labels, and the configured national institution registry.
  Ambiguous affiliations and multi-institution records require careful
  interpretation.
- Collaboration analytics can undercount partnerships when affiliations are
  missing, collapsed, misspelled, or not resolved to registry entities.

### Bibliographic Fields

- `journal`, `publisher`, and `issn`: Exact-string conflict rates are high
  across sources because of abbreviations, imprints, multi-ISSN lists, casing,
  repository labels, and publisher name changes. These mismatches are review
  signals, not automatic proof that a record is wrong.
- `publication_type`: Source vocabularies differ. Canonical type mapping reduces
  variation, but borderline categories such as proceedings articles, reviews,
  preprints, book chapters, theses, and reports can remain noisy.
- `volume`, `issue`, `first_page`, `last_page`, and `article_number`: Coverage
  is source-dependent and less useful for non-journal outputs.
- `language`: Language metadata may be inferred, deposited, or omitted depending
  on source. It should be treated as helpful but not authoritative for all
  records.

### Content and Topic Fields

- `abstract`: OpenAlex does not provide abstract text in the current final
  field set, while Crossref and local sources are partial. Existing analysis
  measured Crossref abstract coverage at 44.39% and local abstract coverage at
  70.91%.
- `keywords`: Local repositories are the main keyword source. OpenAlex topics
  and concepts are not the same as author-supplied keywords.
- `concepts`, `topics`, `primary_topic`, `primary_field`,
  `primary_subfield`, and `primary_domain`: These are analytical
  classifications from source/index models, not official national subject
  assignments.
- Topic modeling or search over abstracts and keywords must disclose that many
  records lack content text.

### Access, License, Funding, and Impact Fields

- `oa_status` and `is_oa`: Open-access status can change over time and can
  differ from license evidence. Treat as snapshot metadata.
- `license` and `license_url`: License coverage is incomplete, especially in
  local repositories. Missing license does not imply closed access.
- `funder_name`, `funder_doi`, `funder_identifier`, and `funder_award`:
  Funding metadata is sparse and primarily depends on Crossref deposits.
- `citation_count` and `reference_count`: Counts differ by index, update cycle,
  and counting rule. The final dataset keeps best-available values and sidecar
  evidence where available, but citation comparisons should report source and
  snapshot date.

## 6. Deduplication and Merge Limits

The merge is deterministic and auditable, but deduplication is not perfect.

- DOI-backed automatic merging is reliable for most journal and conference
  works, but DOI errors or duplicate DOI deposits can still create false joins.
- No-DOI local records require title/year/type evidence. This can miss true
  duplicates with weak titles or merge near-duplicates if titles are generic.
- Author strings are not used as sole merge evidence because they are noisy.
- Same work, preprint, accepted manuscript, repository copy, conference version,
  and journal version can appear as distinct records depending on DOI and source
  metadata.
- Field-level source priority chooses canonical exported values, but conflict
  logs remain the authority for reviewing disagreements.

Required interpretation:

```text
Deduplicated rows are analysis-ready publication records, not guaranteed unique
intellectual works in every edge case.
```

## 7. Data Cleaning and Normalization Limits

Cleaning rules make values consistent enough for analysis; they do not validate
every value against publisher pages or institutional records.

- DOI, ORCID, ISSN, URL, date, boolean, numeric, and multi-value normalization
  remove many formatting problems but cannot confirm semantic truth.
- Invalid or unparsable values are set missing or logged where the pipeline has
  issue logs; this can reduce apparent completeness after cleaning.
- Exact-string comparison can overstate conflicts for publisher, journal, and
  ISSN fields.
- Normalization may collapse harmless variants but intentionally preserves raw
  source evidence through provenance fields, sidecars, and raw records.
- The PostgreSQL loader coerces values into the final schema and preserves the
  original input record in `raw_record`, but it cannot repair upstream metadata
  quality problems.

## 8. Analytical Implications

| Analysis | What is safe | What needs caveats |
|---|---|---|
| Publication counts | Trends and comparisons within the harvested corpus. | National totals, recent-year completeness, and institutions with blocked or incomplete repositories. |
| Institution productivity | DOI-backed global-index output plus reachable local repository evidence. | No-DOI works, missing affiliations, repository deposit practices, and unresolved institution names. |
| Author productivity | Counts over `author_ids` where the identity is ORCID- or evidence-backed. | Identities merged on the name alone, shared exact spellings, and pairs still sitting in the review queue. |
| Collaboration networks | Stronger when affiliation metadata is present and resolved. | Under-counting from missing affiliations and ambiguous institutional labels. |
| Citation impact | Relative analysis within a stated source and snapshot. | Cross-source count comparisons, recent works, and fields with different citation cultures. |
| Topic/field analysis | OpenAlex topic/concept summaries and keyword/abstract search where text exists. | Official classification claims, topic modeling over sparse abstracts, and keyword comparisons across sources. |
| Open-access analysis | Snapshot OA status and license signals where present. | Legal access conclusions, current availability, and missing license interpretation. |
| Funding analysis | Descriptive analysis of deposited funding metadata. | Full funding coverage or grant compliance claims. |

## 9. Required Quality Disclosures for Outputs

Every dashboard, report, exported analysis notebook, or public-facing summary
that uses this dataset should disclose:

1. Source snapshot date or run date.
2. Included source families: OpenAlex, Crossref, SLJOL via Crossref, and local
   repositories.
3. Whether counts use raw, cleaned, deduplicated, final, or analysis-ready data.
4. Denominator for each percentage.
5. Missingness for fields used in key claims.
6. Conflict policy for fields where multiple sources disagree.
7. Citation-count source and snapshot date.
8. Known exclusions, blocked repositories, or partially harvested repositories
   when institution-level conclusions are made.

## 10. Mitigation Already Implemented

| Risk | Mitigation |
|---|---|
| Missing values | Missing-value reports, completeness matrices, and explicit null-preserving cleaning rules. |
| Source disagreement | Conflict analysis, merge logs, configurable field-level source policy, and source-specific sidecars. |
| DOI variation | DOI normalization, validation, duplicate DOI checks, and DOI-based publication keys. |
| No-DOI local records | Records are kept; they are not dropped solely because DOI is absent. |
| Count divergence | Citation/reference divergence flags and count-audit sidecars. |
| Sparse analytical text | Abstract and keyword missingness flags in analysis-ready preprocessing. |
| Provenance loss | `source_dataset`, `source_record_id`, `raw_identifiers`, `source_specific_metadata`, `raw_record`, and audit outputs. |
| Schema drift | Final PostgreSQL loader follows `FINAL_MAIN_COLUMNS` and applies migrations before loading. |

## 11. Remaining Work and Review Backlog

These limitations are known and should be tracked as future quality-improvement
work:

- Obtain official access or institutional exports for blocked or WAF-protected
  repositories.
- Ask repository administrators to rebuild stale OAI indexes where public OAI is
  live but returns no records.
- Add or improve title/year/type matching for no-DOI local records.
- Expand institution alias coverage and review unresolved affiliations.
- Work the ambiguous-author review queue so name-only identities are confirmed
  or split by a reviewer rather than left at `low` confidence.
- Enrich abstracts and keywords from official local sources when permission and
  access allow.
- Re-run source snapshots on a documented schedule and publish change logs for
  count differences.
- Review high-impact publisher, journal, ISSN, and type conflicts manually
  before using them in formal reporting.

## 12. Non-Goals

The current metadata-quality pipeline does not claim to:

- certify complete national publication output;
- replace institutional research information systems;
- manually verify every publication against publisher pages;
- provide legal open-access determinations;
- fully disambiguate authors;
- guarantee complete grant or funder reporting;
- classify research fields using an official national taxonomy unless one is
  explicitly configured; or
- prove research quality from citation counts alone.

## 13. Acceptance Checklist

Before using the dataset for a conclusion, confirm:

- The relevant source snapshot date is stated.
- The analysis uses the correct dataset stage.
- Missingness is reported for every field used in a key claim.
- No-DOI local records are not silently excluded from local-output analysis.
- Citation and reference counts name their source or policy.
- Institution-level comparisons account for blocked and partially harvested
  sources.
- Conflict logs or sidecars are reviewed for fields with known high variation.
- Conclusions use "observed records" language unless independently verified
  against institutional totals.
