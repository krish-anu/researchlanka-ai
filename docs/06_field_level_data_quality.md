# Field-Level Data Quality Statistics

**Status:** Complete (Notebooks 02 + 04)  
**Primary notebook:** `notebooks/04_conflict_and_data_quality_analysis.ipynb`  
**Supporting:** `notebooks/02_metadata_completeness_analysis.ipynb`, `notebooks/03_cross_source_metadata_analysis.ipynb`  
**Key output:** `notebooks/outputs/notebook04/field_level_data_quality_scorecard.csv`

---

## 1. DQ definition used

For each canonical field:

| Component | Meaning |
|-----------|---------|
| Completeness % | Non-missing rate per source (OpenAlex / Crossref / Local) |
| Conflict % | Disagreement rate on OA∩CR when both present |
| Enrichment fillable % | Share of common DOIs where OA missing and CR present |
| Preferred source | Policy-aware primary (OpenAlex SoT where applicable) |
| DQ score | `primary_completeness − 0.5 × conflict%` (clipped 0–100) |
| Quality band | Excellent ≥90, Good ≥70, Fair ≥40, Poor &lt;40 |

This balances “how complete is the preferred value?” against “how often sources disagree?”.

---

## 2. Field-level scorecard (computed)

| Field | OA % | CR % | Local % | Preferred | Conflict % | Fillable % | DQ score | Band |
|-------|-----:|-----:|--------:|-----------|-----------:|-----------:|---------:|------|
| publication_type | 100 | 100 | 99.19 | OpenAlex | — | — | 100.0 | Excellent |
| authors | 100 | 60.06* | 98.21 | OpenAlex | — | — | 100.0 | Excellent |
| title | 99.88 | 99.87 | 99.99 | OpenAlex | 0.90 | — | 99.43 | Excellent |
| publication_year | 100 | 99.75 | 100 | OpenAlex | 2.96 | — | 98.52 | Excellent |
| citation_count | 100 | 100 | 0 | OpenAlex | 3.59† | 0 | 98.20 | Excellent |
| doi | 97.42 | 100 | 41.78 | OpenAlex | — | — | 97.42 | Excellent |
| language | 91.35 | 47.70 | 66.49 | OpenAlex | 0.61 | — | 91.04 | Excellent |
| reference_count | 100 | 100 | 0 | keep both | 25.10† | 0 | 87.45 | Good |
| volume | 65.66 | 67.81 | 0 | Crossref | 0.02 | 0.05 | 67.80 | Fair |
| keywords | 0 | 0 | 64.78 | Local | — | — | 64.78 | Fair |
| journal | 83.51 | 94.31 | 29.65 | OpenAlex | 52.62‡ | 15.46 | 57.20 | Fair |
| issue | 52.01 | 55.84 | 0 | Crossref | 0.05 | 0.04 | 55.82 | Fair |
| license | 47.60 | 61.07 | 0.66 | OA+CR | — | 30.23 | 47.60 | Fair |
| abstract | 0 | 44.39 | 70.91 | Crossref | — | 44.41 | 44.39 | Fair |
| issn | 71.05 | 76.44 | 0 | Crossref | 72.75‡ | 0.11 | 40.06 | Fair |
| publisher | 57.73 | 99.99 | 88.41 | OpenAlex | 66.25‡ | 42.25 | 24.60 | Poor |

\* Crossref author completeness here is from the scorecard column used in NB04 (presence of `author_name` on raw rows can differ from aggregated unique-DOI views in NB02).  
† For counts, “conflict %” is `% with |OA−CR| ≥ 10`.  
‡ High conflict % is largely **string/format variation**, not bibliographic identity failure — interpret with the conflict doc.

**Summary:** 7 Excellent, several Fair enrichment targets, **publisher** scores Poor on exact-string DQ because of naming variants despite being fillable from Crossref.

---

## 3. Statistics to report externally

### Completeness (presence)

Use `notebooks/outputs/notebook02/field_completeness_matrix.csv` and `critical_metadata_fields.csv`.

### Conflict

Use `notebooks/outputs/notebook04/conflicts_openalex_vs_crossref.csv` and `numeric_conflict_summary.csv`.

### Enrichment opportunity

Use `notebooks/outputs/notebook03/enrichment_opportunity_matrix.csv`.

### Combined scorecard

Use `notebooks/outputs/notebook04/field_level_data_quality_scorecard.csv`.

---

## 4. Data-quality findings for the final report

1. **Identity fields (DOI, title, authors, year, type)** are high quality under OpenAlex as SoT; conflicts with Crossref are rare for title/year.
2. **Impact fields (citations, references)** are complete but dual-sourced; report both and a divergence flag (~3.6% of common DOIs have citation |Δ| ≥ 10).
3. **Venue fields (journal, publisher, ISSN)** need enrichment + careful matching; exact-string conflict rates are high and should not be treated as hard errors.
4. **Content enrichment fields (abstract, keywords, ORCID, funding, event, references list)** are completeness-limited in OpenAlex; Crossref/Local fill is the quality improvement path.
5. **Local DOI quality** is the largest corpus-level DQ risk (41.8% DOI coverage; several repos at 0%).

---

## 5. Recommended pipeline QA checks

| Check | Threshold / rule |
|-------|------------------|
| DOI normalize + uniqueness within source | flag duplicate DOI rows |
| Title conflict OA vs CR | log if normalized titles differ (~0.9%) |
| Year conflict | log if \|Δ\| ≥ 2 (~0.15%) |
| Citation divergence | flag if \|Δ\| ≥ 10 and ratio ≥ 1.5 or ≤ 2/3 |
| Required fields after enrich | doi **or** (title + authors); year; type |
| Local no-DOI share by repo | monitor; drive title-matching backlog |

---

## 6. Related documents

- [03_missing_values_analysis.md](03_missing_values_analysis.md)
- [04_metadata_completeness_analysis.md](04_metadata_completeness_analysis.md)
- [05_conflicting_metadata_analysis.md](05_conflicting_metadata_analysis.md)
- [01_metadata_enrichment.md](01_metadata_enrichment.md)
