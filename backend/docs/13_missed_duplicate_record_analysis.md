# Missed Duplicate Record Analysis

**Analysis date:** 2026-08-04

This report identifies records that survived deduplication but still look like
possible duplicates. These are not automatic merges; they are review queues for
improving deduplication coverage without relaxing the conservative merge rules.

## Reproduce

Run from `backend/`:

```bash
python scripts/quality/analyze_missed_duplicate_records.py
```

Default outputs are written to
`data/processed/common/missed_duplicate_analysis/`:

- `missed_duplicate_summary.csv`
- `missed_duplicate_candidate_groups.csv`
- `missed_duplicate_source_summary.csv`

## Input

| Input | Purpose | Rows reviewed |
|---|---|---:|
| `data/processed/common/common_publications_deduplicated.csv` | Canonical rows after DOI deduplication | 182,149 |

## Findings

| Candidate type | Groups | Candidate records | Interpretation |
|---|---:|---:|---|
| Duplicate DOI after deduplication | 0 | 0 | The DOI merge pass left no repeated normalized DOI groups in the reviewed file. |
| Same title + same year + same first author | 5,997 | 12,616 | Strongest missed-duplicate review queue; many are article/preprint, repository copy, or source-version pairs with different or missing DOI evidence. |
| Same title + same year, no first author evidence | 79 | 218 | Lower-confidence queue caused by weak author metadata. |
| Same title + same first author + publication-year span <= 1 | 915 | 2,022 | Year-drift queue for records that may differ because sources disagree on online, print, or repository dates. |
| Total | 6,991 | 14,856 | Review candidates, not confirmed duplicates. |

DOI state across candidate groups:

| DOI state | Groups | Meaning |
|---|---:|---|
| `all_missing` | 4,031 | No DOI evidence in the group. |
| `different_doi` | 2,732 | More than one non-empty DOI appears, so automatic merging remains blocked. |
| `some_missing` | 228 | At least one row has DOI evidence and at least one row lacks it. |

Top source combinations:

| Source combination | Candidate groups |
|---|---:|
| repositories_combined | 4,085 |
| openalex | 2,134 |
| crossref + openalex | 375 |
| crossref | 127 |
| openalex + SLJOL | 96 |
| SLJOL | 65 |
| openalex + repositories | 63 |

## Interpretation

The missed-duplicate analysis confirms that the current DOI-only automatic
merge policy is conservative. It avoids unsafe merges, but it leaves a large
manual-review queue where DOI evidence is missing, versioned, or source-specific.

The largest queue is repository-only records. That is expected: local repository
metadata often has weak DOI coverage, and a repository copy can share title,
year, and first author with an OpenAlex/Crossref record while still lacking a
matching DOI.

Different DOI groups should not be auto-merged. Many examples are legitimate
relationships, such as preprint vs journal article, article vs book chapter, or
repository copy vs publisher record, but some are distinct works with identical
titles. They require explicit review or a curated version/relation table.

## Threshold Implications

- Keep duplicate DOI after deduplication as a high-severity data-quality defect.
- Treat same title + year + first author as a medium-confidence manual-review
  queue, not an automatic merge rule.
- Treat same title + year without first author as low-confidence manual review.
- Treat same title + first author with year span <= 1 as low-confidence manual
  review for date-drift cases.
- Keep different DOI values as an automatic-merge blocker unless a curated
  relationship table later proves equivalence.

## Next Action

Use `missed_duplicate_candidate_groups.csv` as the review input for improving
repository aliases, DOI enrichment, and curated version relationships. Do not
change production counts from these candidates until reviewed.
