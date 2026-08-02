# Missing Values Analysis

**Status:** Complete (Notebooks 01–03)  
**Primary notebooks:** `notebooks/01_Dataset_Overview_and_Corpus_Profiling.ipynb`, `notebooks/02_metadata_completeness_analysis.ipynb`, `notebooks/03_cross_source_metadata_analysis.ipynb`  
**Key outputs:** `notebooks/outputs/notebook01/`, `notebook02/`, `notebook03/`

---

## 1. Corpus snapshot (2016+)

| Source | Records | Columns | DOI coverage |
|--------|--------:|--------:|-------------:|
| OpenAlex | 73,289 | 34 | 97.42% |
| Crossref | 65,946 | 55 | 100.00% |
| Local | 60,812 | 19 | 41.78% |

OpenAlex is the merge backbone. Crossref is DOI-complete by construction. Local has the largest **missing-DOI** problem.

---

## 2. Where values are missing

### Structural absences (field not in export)

| Field | OpenAlex | Crossref | Local |
|-------|----------|----------|-------|
| abstract | missing column (0%) | 44.39% | 70.91% |
| author ORCID | missing | 32.84% | missing |
| funding / funders | missing | 16.28% | missing |
| event metadata | missing | 14.40% | missing |
| keywords | missing | missing | 64.78% |
| topics / research field | strong | missing | missing |
| open access status | 100% | missing | missing |

### Partial missingness (column exists)

| Field | OpenAlex | Crossref | Local |
|-------|---------:|---------:|------:|
| doi | 97.42% | 100% | 41.78% |
| publisher | 57.73% | 99.99% | 88.41% |
| journal / venue | 83.51% | 94.31% | 29.65% |
| issn | 71.05% | 76.44% | 0% |
| volume | 65.66% | 67.81% | 0% |
| issue | 52.01% | 55.84% | 0% |
| license | 47.60% | 61.07% | 0.66% |
| pdf_url | 41.77% | 0% | 0% |

---

## 3. Missing values by publication type

### DOI coverage (selected)

| Type | OpenAlex DOI % | Local DOI % |
|------|---------------:|------------:|
| journal_article | 98.05 | 57.64 |
| conference_paper | 96.48 | (lower; type mix noisy) |
| thesis (OpenAlex) | 77.55 | many Local theses lack DOI |
| dataset | 100 | — |

**Interpretation:** DOI-only joins are safe for most OpenAlex journal/conference works. Local theses and grey literature need **title (+ year/type)** matching.

---

## 4. Missing values by institution / repository

### Local repositories (DOI gap = primary missing-value lever)

| Repository | Records | DOI % | No-DOI records | Matched OpenAlex (of DOI) |
|------------|--------:|------:|---------------:|--------------------------:|
| sljol | 18,032 | 100.0 | 0 | 51.1% |
| sliit | 3,463 | 75.4 | 851 | 71.6% |
| cmb | 2,786 | 33.5 | 1,852 | 87.7% |
| uom | 10,339 | 31.3 | 7,104 | 59.8% |
| seu | 4,022 | 4.6 | 3,837 | 86.0% |
| ruh | 10,804 | 3.8 | 10,396 | 82.1% |
| uwu / pdn / busl / nsf / sltc | 11,366 | **0.0** | 11,366 | — |

**Interpretation:** For no-DOI repos, use title-based linkage to OpenAlex/Crossref, not DOI join.

OpenAlex Sri Lankan institutions generally have **≥95% DOI** coverage (e.g. Colombo, Peradeniya, Moratuwa).

---

## 5. How many missing values Crossref / Local can fill

On **65,891** OpenAlex ∩ Crossref DOIs (`enrichment_opportunity_matrix.csv`):

| Field | OA missing + CR present | % of common DOIs |
|-------|------------------------:|-----------------:|
| references | 39,333 | 59.7% |
| abstract | 29,263 | 44.4% |
| publisher | 27,838 | 42.3% |
| ORCID | 21,649 | 32.9% |
| license | 19,919 | 30.2% |
| funding | 10,705 | 16.3% |
| journal | 10,184 | 15.5% |
| event name | 9,496 | 14.4% |

On **13,710** OpenAlex ∩ Local DOIs:

| Field | OA missing + Local present | % |
|-------|---------------------------:|--:|
| abstract | 9,573 | 69.8% |
| publisher | 9,415 | 68.7% |
| keywords | 4,558 | 33.3% |

---

## 6. Missing-value handling rules

1. Use the configured field-level merge policy for automatic dataset values; log conflicts for review.
2. Preserve source-specific count fields in the count-audit sidecar where available, and flag OpenAlex-vs-Crossref divergence.
3. Fill missing fields from any available source; always retain `source_institution_id` as provenance.
4. **No-DOI Local works:** keep as first-class records; attempt title match; do not drop.
5. **Do not invent values:** leave null if no source provides the field.

See also: `notebooks/outputs/notebook02/missing_value_handling_playbook.csv`, `notebooks/outputs/notebook03/final_enrichment_rules.csv`.
