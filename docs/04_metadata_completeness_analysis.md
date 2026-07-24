# Metadata Completeness Analysis

**Status:** Complete (Notebook 02)  
**Primary notebook:** `notebooks/02_metadata_completeness_analysis.ipynb`  
**Key outputs:** `notebooks/outputs/notebook02/`

---

## 1. Method

- Map each **canonical field** to the real source columns (OpenAlex / Crossref / Local).
- A record is complete for a field if **any** mapped column is non-empty (after treating `nan` / `[]` / `{}` as missing).
- Score bands: Excellent ≥95%, Good ≥70%, Weak ≥30%, Poor &lt;30%.
- OpenAlex is treated as **source of truth**; highest completeness alone does not override that policy.

Column map (examples):

| Canonical | OpenAlex | Crossref | Local |
|-----------|----------|----------|-------|
| doi | `doi` | `DOI` | `doi` |
| type | `type` | `type` | `publication_type` |
| journal | `source_name` | `container-title` | `journal` |
| authors | `authors` | `author_name` | `authors` |
| institution | `sri_lankan_institutions` | `author_affiliation` | `source_institution_id` |
| citations | `cited_by_count` | `is-referenced-by-count` | — |

---

## 2. Completeness matrix (selected fields)

| Field | OpenAlex % | Crossref % | Local % | Preferred primary | Action |
|-------|-----------:|-----------:|--------:|-------------------|--------|
| title | 99.88 | 99.87 | 99.99 | OpenAlex | keep_openalex |
| authors | 100 | 99.22 | 98.21 | OpenAlex | keep_openalex |
| publication_year | 100 | 99.75 | 100 | OpenAlex | keep_openalex |
| publication_type | 100 | 100 | 99.19 | OpenAlex | keep_openalex |
| doi | 97.42 | 100 | 41.78 | OpenAlex | keep_openalex |
| citation_count | 100 | 100 | 0 | OpenAlex | keep_openalex |
| topics / research_field | ~98 / high | 0 | 0 | OpenAlex | keep_openalex |
| open_access_status | 100 | 0 | 0 | OpenAlex | keep_openalex |
| journal | 83.51 | 94.31 | 29.65 | OpenAlex | keep; fill CR gaps |
| publisher | 57.73 | 99.99 | 88.41 | OpenAlex | consider CR fill |
| issn | 71.05 | 76.44 | 0 | Crossref | enrich when OA missing |
| volume / issue / page | 52–76 | 56–86 | 0 | Crossref | enrich when OA missing |
| license | 47.60 | 61.07 | 0.66 | Crossref | enrich when OA missing |
| abstract | 0 | 44.39 | 70.91 | Crossref then Local | enrich |
| author_orcid | 0 | 32.84 | 0 | Crossref | enrich |
| funding | 0 | 16.28 | 0 | Crossref | enrich |
| event | 0 | 14.40 | 0 | Crossref | enrich (conference) |
| keywords | 0 | 0 | 64.78 | Local | enrich |

Full table: `field_completeness_matrix.csv`, `recommended_field_sources.csv`.

---

## 3. Completeness by publication type

Notebook 02 exports `completeness_by_publication_type.csv` with heatmaps for:

- OpenAlex: DOI, title, authors, journal, venue fields, citations, topics by canonical type
- Local: DOI, abstract, authors, keywords, journal by type

**Findings:**

- **Journal articles** are the richest metadata class across OpenAlex and Crossref.
- **Conference papers** benefit most from Crossref `event.*` fields.
- **Local theses / exam / grey types** are weak on DOI and venue; strong on repository provenance.

---

## 4. Completeness by institution

### OpenAlex (`sri_lankan_institutions`)

Top universities generally show high DOI/title/author completeness; venue/publisher still incomplete for a subset of works.

### Local (`source_institution_id`)

Completeness of DOI / abstract / keywords varies sharply by repository (see missing-values doc). SLJOL is DOI-complete; several university IRs contribute large no-DOI volumes.

Outputs: `completeness_by_institution.csv`.

---

## 5. Source-level average completeness

Average across canonical fields is **not** a ranking of source quality for the pipeline. OpenAlex is preferred for identity and analytics fields even when Crossref averages higher on venue/rights fields.

Use field-level recommendations, not a single source winner.

---

## 6. Completeness → enrichment implication

| Completeness pattern | Implication |
|----------------------|-------------|
| OA high, CR/Local high | Keep OA; no fill needed |
| OA high, CR higher on venue | Keep OA; fill only when OA empty |
| OA 0%, CR/Local &gt;0 | Hard enrich from CR/Local |
| All low | Accept null or future harvest |

Playbook: `missing_value_handling_playbook.csv`.
