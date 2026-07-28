# Conflicting Metadata Between Sources

**Status:** Complete (Notebook 04)  
**Primary notebook:** `notebooks/04_conflict_and_data_quality_analysis.ipynb`  
**Key outputs:** `notebooks/outputs/notebook04/`

---

## 1. Scope

Conflicts are measured on **shared DOIs** where **both sides have a value**.

| Comparison | Common DOIs |
|------------|------------:|
| OpenAlex ∩ Crossref | 65,891 |
| OpenAlex ∩ Local | 13,710 |

Normalization:

- Titles: lowercase, strip punctuation
- Years: numeric equality
- Types: shared canonical vocabulary (`journal_article`, `conference_paper`, …)
- Publisher / journal / ISSN: lowercase trimmed strings (exact match — naming variants inflate “conflict”)

---

## 2. OpenAlex vs Crossref conflict rates

| Field | Both present | Match % | Conflict % | Notes |
|-------|-------------:|--------:|-----------:|-------|
| title | 65,805 | 99.10 | **0.90** | Safe SoT = OpenAlex |
| publication_year | 65,724 | 97.04 | **2.96** | Only 0.15% differ by ≥2 years |
| language | 31,405 | 99.39 | 0.61 | Rare true conflict |
| volume | 44,648 | 99.98 | **0.02** | Extremely consistent |
| issue | 36,776 | 99.95 | **0.05** | Extremely consistent |
| canonical_type | 65,891 | 90.89 | 9.11 | Vocabulary residue after mapping |
| journal | 51,962 | 47.38 | 52.62 | Mostly **naming variants** |
| publisher | 38,044 | 33.75 | **66.25** | Naming variants / imprint differences |
| issn | 50,293 | 27.25 | 72.75 | Format / multi-ISSN encoding differences |

### Numeric conflicts

| Metric | Exact match % | \|diff\| ≥ 10 % | Flagged divergence % |
|--------|--------------:|----------------:|----------------------:|
| citation_count (OA `cited_by_count` vs CR `is-referenced-by-count`) | 62.61 | **3.59** | 1.57 |
| reference_count | 31.39 | 25.10 | — |

Mean |citation diff| ≈ 1.84 (median 0). Large outliers exist; store both values.

---

## 3. OpenAlex vs Local conflict rates

| Field | Both present | Match % | Conflict % |
|-------|-------------:|--------:|-----------:|
| title | 13,709 | 97.64 | 2.36 |
| publication_year | 13,710 | 97.72 | 2.28 |
| journal | 8,966 | 89.01 | 10.99 |
| canonical_type | 13,710 | 82.47 | 17.53 |
| publisher | 4,014 | 5.03 | 94.97 |

Local publisher strings are often repository/publisher labels, not Crossref-style imprint names — treat as **weak conflict signal**.

---

## 4. Type-wise conflict patterns (OA vs CR)

- **journal_article:** title conflicts ~0.9%; year ~3.7%; publisher string conflicts high but expected.
- **conference_paper:** higher type-mapping disagreements; event metadata is CR-only enrichment, not a conflict.
- **preprint / review / other:** elevated type conflicts — keep raw type from both sources, prefer OA canonical for analytics.

Full table: `conflicts_by_publication_type.csv`.

---

## 5. Conflict handling policy

The automated merge uses an explicit field-level source policy with record
completeness as a tie-breaker inside each source. The built-in policy can be
overridden with `scripts/processing/kaggle_merge_common_dataset.py --field-source-policy`.
Conflicting fields remain auditable in the merge log.

| Field group | Automated action |
|-------|--------|
| DOI/title/year/type | choose by the configured field policy; log conflicts |
| authors / affiliations / identifiers | retain multi-value evidence and provenance |
| publisher / journal / ISSN | choose by the configured field policy; treat string mismatches as review signals, not automatic errors |
| volume / issue / page | choose by the configured field policy and fill gaps |
| citation_count | keep best available count in the main CSV; move Crossref `is_referenced_by_count` to the count-audit sidecar; flag OpenAlex-vs-Crossref divergence when both are present |
| reference_count | keep best available count in the main CSV; move OpenAlex `referenced_works_count` to the count-audit sidecar; flag OpenAlex-vs-Crossref divergence when both are present |
| abstract / keywords | use the configured policy/fallbacks; review important conflicts manually |

Notebook exports such as `conflict_resolution_policy.csv` are analysis guidance,
and may be translated into the JSON field policy used by the merge script.

---

## 6. What is *not* a true conflict

1. **Publisher / journal / ISSN string mismatch** without semantic difference (abbreviations, imprints, multi-ISSN lists).
2. **Citation / reference count differences** from different indexes — expected; dual-store.
3. **Type labels** before canonical mapping (`article` vs `journal-article`).
4. **Missing vs present** — that is a completeness/enrichment issue (docs 03–04), not a conflict.

---

## 7. Engineering recommendation

```text
load built-in field source policy plus optional JSON overrides
for each field:
    order duplicate rows by configured source list, then completeness
    use the first non-empty value
    union multi-value/provenance fields
log fields whose normalized values disagree
flag citation/reference divergence when both OA and CR counts exist
```
