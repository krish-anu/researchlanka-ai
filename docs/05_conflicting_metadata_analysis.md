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

## 5. Conflict resolution policy

| Field | Winner | Action |
|-------|--------|--------|
| title | OpenAlex | keep OA; log rare conflicts |
| publication_year | OpenAlex | keep OA; log if \|Δ\| ≥ 2 |
| canonical_type | OpenAlex | keep OA canonical; store raw both |
| publisher / journal | OA if present else CR | prefer OA; fill gaps; **do not** hard-flag all string mismatches |
| issn / volume / issue / page | CR when OA missing | fill from Crossref |
| citation_count | **keep both** | store OA + CR; flag divergence |
| reference_count | **keep both** | store both |
| abstract | Crossref then Local | fill (not a conflict — OA absent) |
| keywords | Local | fill |

Exported: `conflict_resolution_policy.csv`.

---

## 6. What is *not* a true conflict

1. **Publisher / journal / ISSN string mismatch** without semantic difference (abbreviations, imprints, multi-ISSN lists).
2. **Citation / reference count differences** from different indexes — expected; dual-store.
3. **Type labels** before canonical mapping (`article` vs `journal-article`).
4. **Missing vs present** — that is a completeness/enrichment issue (docs 03–04), not a conflict.

---

## 7. Engineering recommendation

```text
if both present and field in {title, year, authors, topics, oa_status}:
    use OpenAlex
    optionally log conflict
elif field in {citations, references}:
    store both + divergence_flag
elif OpenAlex missing and Crossref/Local present:
    enrich
else:
    null
```
