# Metadata Completeness Analysis

**Status:** Complete (Notebook 02)  
**Primary notebook:** `notebooks/02_metadata_completeness_analysis.ipynb`  
**Key outputs:** `notebooks/outputs/notebook02/`

---

## 1. Method

- Map each **canonical field** to the real source columns (OpenAlex / Crossref / Local).
- A record is complete for a field if **any** mapped column is non-empty (after treating `nan` / `[]` / `{}` as missing).
- Score bands: Excellent ≥95%, Good ≥70%, Weak ≥30%, Poor &lt;30%.
- OpenAlex has strong coverage for many identity and analytics fields, but the implemented merge uses a configurable field-level source policy with conflict logging.

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

| Field | OpenAlex % | Crossref % | Local % | Strong source signal | Suggested action |
|-------|-----------:|-----------:|--------:|-------------------|--------|
| title | 99.88 | 99.87 | 99.99 | OpenAlex / Local | log conflicts |
| authors | 100 | 99.22 | 98.21 | OpenAlex | log conflicts |
| publication_year | 100 | 99.75 | 100 | OpenAlex / Local | log conflicts |
| publication_type | 100 | 100 | 99.19 | OpenAlex / Crossref | log conflicts |
| doi | 97.42 | 100 | 41.78 | Crossref / OpenAlex | normalize and log conflicts |
| citation_count | 100 | 100 | 0 | OpenAlex / Crossref | keep comparison fields |
| topics / research_field | ~98 / high | 0 | 0 | OpenAlex | keep when present |
| open_access_status | 100 | 0 | 0 | OpenAlex | keep when present |
| journal | 83.51 | 94.31 | 29.65 | OpenAlex / Crossref | log string conflicts |
| publisher | 57.73 | 99.99 | 88.41 | Crossref / Local | log string conflicts |
| issn | 71.05 | 76.44 | 0 | Crossref / OpenAlex | fill gaps |
| volume / issue / page | 52–76 | 56–86 | 0 | Crossref / OpenAlex | fill gaps |
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

Average across canonical fields is **not** a ranking of source quality for the pipeline. OpenAlex is strong for identity and analytics fields, while Crossref is strong for venue/rights fields.

Use field-level diagnostics for review and QA; the implemented merge does not hard-code a single field-level winner.

---

## 6. Completeness → enrichment implication

| Completeness pattern | Implication |
|----------------------|-------------|
| OA high, CR/Local high | Keep OA; no fill needed |
| OA high, CR higher on venue | Keep OA; fill only when OA empty |
| OA 0%, CR/Local &gt;0 | Hard enrich from CR/Local |
| All low | Accept null or future harvest |

Playbook: `missing_value_handling_playbook.csv`.
