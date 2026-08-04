# False Duplicate Match Analysis

**Analysis date:** 2026-08-04

This report reviews duplicate-candidate pairs that are likely to become false
positive merges if title, year, or fuzzy-title similarity is promoted from
manual review to automatic deduplication.

## Inputs

| Input | Purpose | Rows reviewed |
|---|---|---:|
| `notebooks/candidate_duplicate_pairs.csv` | High-similarity title/fuzzy candidate pairs | 464 pairs |
| `data/processed/common/common_publications_all_records.csv` | Same-DOI groups before deduplication | 211,611 source rows |
| `outputs/sri_lanka/automatic_matches.csv` | Existing framework DOI auto-merge candidates | 29,459 candidates |
| `outputs/sri_lanka/manual_review_matches.csv` | Existing framework exact-title review candidates | 30,511 candidates |

The candidate-pair file does not contain human labels, so the analysis measures
false-positive risk patterns rather than a final reviewed false-positive rate.

## Reproduce

Run the reusable analysis script from `backend/`:

```bash
python scripts/quality/analyze_false_duplicate_matches.py
```

Default outputs are written to
`data/processed/common/duplicate_match_analysis/`:

- `false_duplicate_candidate_risk_summary.csv`
- `same_doi_conflict_summary.csv`
- `same_doi_conflict_groups.csv`
- `severe_same_doi_conflicts.csv`
- `severe_same_doi_source_summary.csv`

## Candidate-Pair Findings

| Risk signal | Count | Share of candidate pairs | Interpretation |
|---|---:|---:|---|
| Both records have DOI values, but the normalized DOIs differ | 182 | 39.2% | Strong evidence against automatic title/fuzzy merging. |
| Exact normalized title, same year, different DOI | 96 | 20.7% | A perfect title score is not enough to auto-merge. |
| Non-identical normalized titles | 205 | 44.2% | Fuzzy scoring creates many review-only candidates. |
| Title mentions figure, table, dataset, supplementary, or additional file | 48 | 10.3% | Research artifacts can share parent-work titles while representing distinct records. |
| One DOI missing | 141 | 30.4% | Identity cannot be confirmed automatically. |
| Neither DOI present | 141 | 30.4% | Highest uncertainty; keep manual-review only. |
| Repository-involved pair | 323 | 69.6% | Local metadata is valuable, but weak identifiers are common. |
| Same source-label pair | 305 | 65.7% | Repeated records within a source label need source-specific review. |
| Score >= 99 with different DOI | 126 | 27.2% | Very high fuzzy scores still include unsafe matches. |
| Score >= 95 with one or no DOI | 211 | 45.5% | Thresholds alone would over-merge DOI-poor records. |

Important examples from `candidate_duplicate_pairs.csv`:

- Identical title and year can still point to different DOI records, such as an
  article DOI paired with a Figshare or Zenodo DOI.
- Numbered artifacts create high fuzzy scores while referring to distinct
  objects, for example `Additional file 13` vs `Additional file 3`, or
  `FIGURE 14` vs `FIGURE 18`.
- Dataset versions can share a title while the DOI suffix indicates a distinct
  version, for example `.1` vs `.2`.

## Same-DOI Group Findings

The all-records scan found 147,422 rows with normalized DOI values. Within
those rows, 27,277 DOI groups had more than one source row, covering 56,739
input rows.

Same-DOI conflicts are the main false-positive risk for the current automatic
merge rule, because DOI is the only automatic identity key.

| Same-DOI risk signal | Count |
|---|---:|
| DOI groups with title or year disagreement | 839 |
| DOI groups with title similarity below 0.95 | 134 |
| DOI groups with title similarity below 0.90 | 120 |
| DOI groups with title similarity below 0.80 | 93 |
| DOI groups with publication-year disagreement | 591 |
| DOI groups with publication-year span greater than one year | 56 |
| Severe groups: title similarity below 0.80 or year span greater than one year | 142 |

Severe same-DOI conflicts are concentrated in cross-source groups:

| Source combination | Severe groups |
|---|---:|
| OpenAlex + repositories | 64 |
| Crossref + OpenAlex + repositories | 37 |
| repositories only | 14 |
| Crossref + OpenAlex | 13 |
| OpenAlex + repositories + SLJOL | 8 |
| OpenAlex only | 4 |
| OpenAlex + SLJOL | 1 |
| repositories + SLJOL | 1 |

Representative severe examples:

- `10.1109/icitr51448.2020.9310817` appears on multiple unrelated-looking
  titles across 2016 and 2020.
- `10.1371/journal` appears as a truncated or malformed DOI shared by unrelated
  repository records.
- Several `10.54389/...` groups contain different conference-paper titles under
  the same DOI-like value.
- Short-title records such as `PARROT`, `Eatery`, and `Paradigm` produce large
  normalized-title divergence when paired with their expanded titles.

These examples do not prove that every same-DOI conflict is a false merge. Some
are punctuation, capitalization, subtitle, or publication-date differences.
They do show that DOI auto-merge needs an audit layer for severe disagreement.

## Conclusions

1. Title/year and fuzzy-title matches must remain manual-review candidates.
   The candidate file contains many high-score pairs with different DOI values,
   artifact titles, or missing identifiers.
2. A fuzzy score threshold, even at 99 or 100, is not safe as an automatic
   duplicate rule by itself.
3. Different valid DOIs should be treated as a hard blocker for automatic
   merging unless a curated relationship table says they are versions of the
   same publication.
4. DOI auto-merge remains the best default automatic rule, but severe same-DOI
   title/year conflicts should be flagged for audit before final publication
   counts are treated as definitive.
5. Repository records are the largest source of duplicate uncertainty, mostly
   because DOI coverage and source identifiers vary by repository route.

## Threshold Implications

Recommended inputs for the threshold-finalization step:

- Keep `doi` as the only automatic merge method.
- Keep exact title, title/year, title/year/first-author, and fuzzy title matches
  as `manual_review`.
- Block automatic merges when both sides have non-empty normalized DOI values
  and the values differ.
- Add a same-DOI severity flag for review when normalized title similarity is
  below `0.80` or the publication-year span is greater than `1`.
- Add an artifact-title review flag for titles containing `additional file`,
  `supplementary`, `supplemental`, `figure`, `fig.`, `table`, `dataset`,
  `appendix`, `annex`, `image`, or `plate`.
- Do not use fuzzy score alone. Require identifier compatibility plus source,
  year, author, and artifact checks before any future non-DOI auto-merge is
  considered.

## Follow-Up Checks

- Review the 142 severe same-DOI groups and decide whether they should be
  excluded from automatic merge, quarantined, or corrected at source-normalization
  time.
- Analyze missed duplicate records separately, focusing on DOI-less repository
  records and SLJOL/repository overlap.
- After both false-positive and missed-duplicate reviews are complete, finalize
  duplicate-detection thresholds in `docs/normalization_and_merge.md` and the
  implementation tests.
