# System and Data-Pipeline Architecture

This document defines the first architecture draft for the AI Research Analytics Platform. The goal is to make the data flow clear enough for Week 1 work: collect Sri Lankan research publication records, normalize them, compare sources, and prepare clean datasets for later analytics and dashboard work.

## Scope

The system focuses on publications connected to Sri Lankan researchers or institutions. In the OpenAlex pipeline, a record is considered Sri Lankan-affiliated when OpenAlex authorship or institution metadata contains country code `LK`. For strict Sri Lanka-only analysis, records are kept only when the detected affiliation country-code set is exactly `{"LK"}`.

## High-Level Components

The platform now has **two collection subsystems** that share a common
schema but have separate pipelines, storage layouts and quality reports:

- the **national-scale API pipeline** (OpenAlex/Crossref by country), and
- the **institutional repository subsystem** (per-university harvesting),
  documented in full in [DATA_COLLECTION.md](DATA_COLLECTION.md).

```text
External APIs                        Institutional sources
  |-- OpenAlex works API               |-- DSpace OAI-PMH endpoints
  |-- Crossref works API               |-- DSpace 7/8 REST discover API
  |-- SLJOL pages and article metadata |-- DSpace item pages (DC meta tags)
  |-- PubMed E-utilities               |-- ~35 registered university targets

Collection Layer
  |-- scripts/kaggle_collect_openalex_sri_lanka.py   (country-scale OpenAlex)
  |-- scripts/collect_crossref.py                    (country-scale Crossref)
  |-- notebooks/03-sljol.ipynb
  |-- scripts/validate_repositories.py               (endpoint health)
  |-- scripts/harvest_oai.py / harvest_all.py        (OAI route)
  |-- scripts/harvest_large_repository.py            (date-sliced OAI)
  |-- scripts/harvest_dspace_rest.py                 (REST route)
  |-- scripts/harvest_html_meta.py                   (HTML meta-tag route)
  |-- scripts/collect_openalex_institution.py        (per-institution OpenAlex)
  |-- scripts/collect_crossref_affiliation.py        (blocked-repo recovery)
  |-- scripts/collect_pubmed_affiliation.py          (blocked-repo recovery)

Collector Classes (src/collectors/)
  |-- openalex_collector.py    crossref_collector.py
  |-- oai_pmh_collector.py     dspace_rest_collector.py
  |-- html_meta_collector.py   pubmed_collector.py
  |-- sitemap_collector.py     repository_registry.py
  |-- schema_mapping.py        (all sources -> common schema)

Raw and Interim Storage
  |-- data/raw/<institution_id>/   (per-institution, per-route JSONL)
  |-- data/raw/openalex/           (country-scale)
  |-- data/interim/

Preprocessing and Normalization
  |-- src/preprocessing/openalex_normalizer.py
  |-- src/preprocessing/crossref_normalizer.py
  |-- src/preprocessing/clean_publications.py
  |-- scripts/map_to_common_schema.py
  |-- scripts/jsonl_to_csv.py

Comparison and Quality Checks
  |-- scripts/compare_dois.py                    (OpenAlex vs Crossref)
  |-- scripts/validate_harvested_data.py         (raw vs mapped coverage)
  |-- scripts/validate_institutions.py           (registry institution integrity)
  |-- scripts/detect_registry_drift.py           (registry claims vs evidence)
  |-- scripts/compare_repository_openalex.py     (repository vs OpenAlex overlap)
  |-- tests/

Processed Outputs
  |-- data/processed/repositories/  + repositories_combined.csv
  |-- data/processed/openalex/      + openalex_combined.csv
  |-- data/processed/recovery/      + recovery_combined.csv
  |-- notebooks/analyze_openalex_sri_lanka_only.ipynb

Future Application Layer
  |-- analytics dashboards
  |-- search and filtering interface
  |-- AI/ML publication classification
```

## Pipeline Stages

### 1. Source Collection

OpenAlex collection is the primary source for Sri Lankan-affiliated works because OpenAlex exposes structured institution country codes. The current collector is:

```bash
python scripts/kaggle_collect_openalex_sri_lanka.py --max-records 1000
```

The collector:

- calls the OpenAlex works API
- applies `authorships.institutions.country_code:LK`
- keeps records with at least one Sri Lankan authorship or LK institution
- writes raw JSONL plus flattened CSV and Parquet outputs
- logs cursor-pagination progress and writes a pagination audit JSON file

Crossref collection is used as a secondary source for DOI comparison and metadata coverage checks. SLJOL notebooks support local Sri Lankan journal exploration.

#### Institutional repository collection

The repository subsystem collects per-university output that the
country-scale APIs largely do not index - theses, internal proceedings
and locally published work. Each institution is harvested through
whichever route its server actually supports, recorded in the registry
at `data/config/repositories.json`:

| Route | When it is used |
|---|---|
| OAI-PMH | Default, wherever the OAI index actually returns records |
| DSpace 7/8 REST | OAI index empty or its pagination crashes (pdn, nsf, busl, cmb, uwu) |
| HTML meta tags | Legacy DSpace with dead OAI, no REST, no sitemap (jfn_*) |
| OpenAlex by institution | Complement: the DOI-bearing journal output never deposited locally |
| Crossref/PubMed by affiliation | Recovery: the repository is blocked or offline (kln, sab) |

Two rules keep the outputs honest and are enforced in
`scripts/map_to_common_schema.py`:

- **Repository routes compete, never merge.** When an institution has
  data from several routes, the one that captured the most records wins,
  so the same item cannot be counted twice.
- **Cross-source routes are separate populations.** OpenAlex and the
  recovery routes land in their own processed namespaces and can never
  displace repository records. Their overlap with the repository is
  measured, not assumed - see `scripts/compare_repository_openalex.py`.

Full per-institution status, per-script detail and the affiliation-matching
pitfalls live in [DATA_COLLECTION.md](DATA_COLLECTION.md).

### 2. Raw Storage

Raw API responses should be stored without changing field names or nested structure.

Recommended paths:

```text
data/raw/openalex/
data/raw/crossref/
data/raw/sljol/
```

Raw data files should not be committed when they are large. Commit only small test fixtures or derived documentation.

### 3. File-Naming Conventions

Project dataset outputs use lower snake case:

```text
source_scope_entity[_variant].extension
```

Rules:

- Use lowercase letters, numbers, and underscores only.
- Start with the data source or pipeline area, such as `openalex`, `crossref`, `sljol`, or `doi_comparison`.
- Use `sri_lanka` for Sri Lanka-focused datasets instead of abbreviations such as `lk`.
- Use plural entity names for record collections, such as `works`, `publications`, or `dois`.
- Add a variant only when needed, such as `strict_lk_only`, `doi_enriched`, or `openalex_only`.
- Supported data-output extensions are `.jsonl`, `.json`, `.csv`, `.parquet`, `.txt`, and `.log`.

Examples:

```text
data/raw/openalex/openalex_sri_lanka_works.jsonl
data/raw/openalex/openalex_sri_lanka_works.csv
data/raw/openalex/openalex_sri_lanka_pagination_audit.json
data/processed/crossref/crossref_sri_lanka_works.jsonl
data/processed/crossref/crossref_sri_lanka_works_doi_enriched.jsonl
data/processed/doi_comparison/doi_comparison_openalex_only_dois.txt
```

Code, notebook, and documentation names follow the existing repository style:

- Python modules and scripts: lower snake case, for example `collect_crossref.py`.
- Tests: `test_<module_or_behavior>.py`.
- Notebooks: ordered kebab case, for example `01-data-collection.ipynb`.
- Formal docs: uppercase snake case, for example `SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md`.

The helper in `src/utils/file_naming.py` builds and validates dataset filenames used by pipeline scripts.

### 4. Field Normalization

Normalized datasets should use stable, analysis-friendly field names. The current OpenAlex flat export uses:

```text
openalex_id
doi
title
publication_year
publication_date
type
cited_by_count
author_count
authors
sri_lankan_authors
institutions
sri_lankan_institutions
raw_affiliation_strings
sri_lankan_raw_affiliation_strings
countries
source_name
publisher
is_retracted
is_oa
landing_page_url
pdf_url
locations_count
location_landing_page_urls
location_pdf_urls
location_source_names
location_source_types
location_licenses
location_versions
referenced_works_count
concepts
topics
primary_topic
primary_field
primary_subfield
primary_domain
language
oa_status
license
source_type
issn_l
volume
issue
first_page
last_page
```

`publication_year` is normalized to an integer. `publication_date` is validated
and written as an ISO `YYYY-MM-DD` date string in CSV exports; Parquet exports
store it as a native date value.

Crossref normalization should continue to standardize DOI, title, authors, publication year, source, publisher, and event fields.

### 5. Filtering Rules

The project uses two Sri Lanka filters:

- Broad Sri Lankan-affiliated: at least one detected country code or institution country code is `LK`.
- Strict Sri Lanka-only: the full detected country-code set is exactly `{"LK"}`.

Broad filtering is useful for collection. Strict filtering is useful for final Sri Lanka-only analysis when international collaborations should be excluded.

### 6. Quality Checks

Quality checks should run before a dataset is considered ready for analysis:

- DOI presence and DOI normalization
- duplicate DOI or OpenAlex ID checks
- separate DOI conflict reporting when one normalized DOI maps to multiple OpenAlex IDs
- missing title/year/source checks
- Sri Lankan affiliation validation
- OpenAlex cursor-pagination validation, including repeated/stuck cursor detection
- source comparison between OpenAlex and Crossref
- schema consistency for expected output columns

Automated tests live in `tests/`. OpenAlex sample-record tests verify the collector's filtering and flattening logic without using the live API.

### 7. Processed Outputs

Processed outputs should be saved under:

```text
data/processed/openalex/
data/processed/crossref/
data/processed/doi_comparison/
```

The OpenAlex collector writes raw JSONL, flat CSV, cleaned Parquet, a
separate DOI conflict CSV, and a pagination audit JSON with page-by-page cursor,
kept/skipped count, estimated page count, progress percentage, and API response
timing metadata. The OpenAlex analysis notebook writes strict
Sri Lanka-only analysis tables and charts to `data/processed/openalex/` locally
or `/kaggle/working/openalex_outputs/` on Kaggle.

## Current Implementation Map

| Area | Current file |
|---|---|
| OpenAlex collection (country-scale) | `scripts/kaggle_collect_openalex_sri_lanka.py` |
| OpenAlex normalization | `src/preprocessing/openalex_normalizer.py` |
| OpenAlex analysis | `notebooks/analyze_openalex_sri_lanka_only.ipynb` |
| Crossref collection (country-scale) | `scripts/collect_crossref.py` |
| Crossref collector class | `src/collectors/crossref_collector.py` |
| Crossref normalization | `src/preprocessing/crossref_normalizer.py` |
| DOI comparison | `scripts/compare_dois.py` |
| JSONL to CSV conversion | `scripts/jsonl_to_csv.py` |
| Repository target registry | `data/config/repositories.json`, `src/collectors/repository_registry.py` |
| Endpoint validation | `scripts/validate_repositories.py` |
| OAI harvesting | `scripts/harvest_oai.py`, `scripts/harvest_all.py`, `scripts/harvest_large_repository.py` |
| DSpace REST harvesting | `scripts/harvest_dspace_rest.py`, `src/collectors/dspace_rest_collector.py` |
| HTML meta-tag harvesting | `scripts/harvest_html_meta.py`, `src/collectors/html_meta_collector.py` |
| Per-institution OpenAlex | `scripts/collect_openalex_institution.py` |
| Blocked-repository recovery | `scripts/collect_crossref_affiliation.py`, `scripts/collect_pubmed_affiliation.py`, `src/collectors/pubmed_collector.py` |
| Common-schema mapping (all sources) | `scripts/map_to_common_schema.py`, `src/collectors/schema_mapping.py` |
| Repository data quality | `scripts/validate_harvested_data.py` |
| Institution integrity | `scripts/validate_institutions.py`, `data/config/institutions_reference.json` |
| Registry drift detection | `scripts/detect_registry_drift.py` |
| Repository vs OpenAlex overlap | `scripts/compare_repository_openalex.py` |
| Repository CSV export | `scripts/convert_repositories_jsonl_to_csv.py` |
| Tests | `tests/` |

## Execution Order

For a small validation run:

```bash
python scripts/kaggle_collect_openalex_sri_lanka.py --max-records 1000
pytest -q
```

For a local analysis run:

1. Collect OpenAlex records into JSONL and CSV.
2. Place or copy the output into `data/raw/openalex/` or `data/processed/openalex/`.
3. Run `notebooks/analyze_openalex_sri_lanka_only.ipynb`.
4. Review filter summary, missing-field report, duplicate report, charts, and exported CSV tables.

## Future Architecture Work

The next architecture step is to move repeated notebook logic into reusable pipeline modules under `src/pipeline/`. The first useful modules would be:

- OpenAlex raw-to-flat conversion
- strict Sri Lanka-only filtering
- dataset quality reporting
- source comparison reporting
- final dataset build orchestration

This keeps notebooks focused on exploration while the repeatable production workflow lives in Python modules and tests.
