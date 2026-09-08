# Sri Lanka National Framework Gap Analysis

This gap analysis reviews the current Sri Lanka national research analytics
framework after removing unrelated country/example scaffolding. The categories
below describe what can be reused within the Sri Lanka pipeline, what remains
hard-coded, and what should be improved before the framework is treated as a
stable national workflow.

## Already reusable

| Area | Current state | Evidence | Notes |
| --- | --- | --- | --- |
| Pipeline stage orchestration | The same `ResearchPipeline` methods run collect, transform, validate, clean, resolve entities, deduplicate, analyze, and export stages from configuration. | `research_analytics/pipeline.py` | Good base for Sri Lanka source runs and staged execution. |
| Standard publication schema | All source adapters map into one standard publication record. | `research_analytics/schema.py` | Supports consistent CSV/JSON exports and analytics. |
| Local file adapters | CSV, JSON, Excel, and XML adapters share common mapping, validation, transformations, and provenance handling. | `research_analytics/adapters/local_file.py` | Useful for repository-combined and curated Sri Lanka datasets. |
| Generic API adapter | REST API adapter supports headers, auth, response paths, and page/offset/cursor/next-link pagination. | `research_analytics/adapters/api.py` | Can support Sri Lanka source APIs without new adapter code when response shape is simple. |
| Source adapter registry | Built-in adapters are selected by `source.type`. | `research_analytics/adapters/registry.py` | Keeps source selection centralized. |
| Field transformations | DOI normalization, year extraction, string splitting, and stripping are config-driven. | `research_analytics/transformations.py` | Covers common Sri Lanka data cleanup needs. |
| Institution registry | Institution aliases and national resolution come from CSV. | `research_analytics/institutions.py`, `configurations/sri_lanka/institutions.csv` | Strong fit for Sri Lanka institution normalization. |
| Field-aware analytics | Analytics skip unavailable metadata gracefully instead of failing. | `research_analytics/analytics.py` | Helpful while Sri Lanka source coverage is uneven. |
| Export layout | Standard exports are generated in one place. | `research_analytics/exporters.py` | Keeps dashboard/data consumers stable. |
| Tests for core behavior | Pipeline, adapters, schema mapping, OpenAlex category mapping, and strict LK filtering are covered. | `tests/` | Good regression base. |

## Partially reusable

| Area | Current state | Gap | Suggested action |
| --- | --- | --- | --- |
| OpenAlex framework adapter | Uses config for country code, years, mapping, transformations, and strict national filtering. | Some normalization helpers still expose Sri Lanka-specific function names and columns. | Keep behavior, but align names if the framework code should read purely as the Sri Lanka national implementation. |
| `sources` block in Sri Lanka config | Lists OpenAlex, Crossref, SLJOL, and repository source groups. | Implemented for collectable source entries; descriptive entries without a path/API configuration are skipped with a log message. | Keep descriptive entries for planning, and add adapter details when a source should run in framework orchestration. |
| Entity resolution | Resolves exact normalized aliases from the Sri Lanka registry. | No fuzzy/identifier-based matching for institution variants outside the alias file. | Add ROR-aware and controlled fuzzy matching for unresolved Sri Lanka affiliations. |
| Collaboration analytics | Classifies domestic and international collaboration and summarizes author, country, and funder collaboration networks when those fields exist. | Network depth depends on available metadata. | Add dashboard controls if users need to choose network type interactively. |
| Source validation | Preview and validation work for adapter records. | Validation report is mostly structural; it does not fully assess Sri Lanka-specific metadata quality thresholds. | Add national validation checks for LK association, institution resolution rate, DOI coverage, and year ranges. |
| Dashboard/API design | Read-only API contract is documented in `docs/API_DESIGN.md`; MVP service code lives in `src/api/`. | Not yet connected to a deployed dashboard. | Harden the MVP API against PostgreSQL `final_publications`, then connect the dashboard. |
| Documentation | Main docs now describe Sri Lanka national scope. | Some older analysis docs still describe decisions from historical datasets rather than current pipeline behavior. | Mark older analysis docs as historical or update them against current outputs. |

## Hard-coded

| Area | Hard-coded value or behavior | Impact | Recommended fix |
| --- | --- | --- | --- |
| Sri Lanka constants in OpenAlex normalizer | `SRI_LANKA_COUNTRY_CODE = "LK"` and `sri_lankan_*` field names. | Appropriate for this project, but the normalizer and framework adapter use slightly different country-scope mechanisms. | Keep constants for national output fields; document them as intentional Sri Lanka schema fields. |
| Legacy OpenAlex script names and outputs | `scripts/kaggle_collect_openalex_sri_lanka.py`, `openalex_sri_lanka_works.*`. | Fine for current scope, but duplicates some framework adapter behavior. | Keep as legacy collection path; avoid adding new framework logic there unless still needed. |
| Makefile OpenAlex defaults | Output paths and strict flag wording are Sri Lanka-specific. | Correct for this repository after narrowing scope. | Can remain unless output folder strategy changes. |
| Export filenames | `national_publications.csv`, `research_categories.csv`, `source_records.json`, etc. | Stable for consumers, but adding/removing exports requires code edits. | Keep stable names; add config only if dashboard/export consumers require variants. |
| Analytics limits | Top institution/category counts are fixed in code. | Dashboard may need different limits or full ranked files. | Move limits to analytics config if this becomes a user-facing control. |
| Dedup auto-merge behavior | Only DOI auto-merge removes right-side duplicates; fuzzy title matching is disabled by default. | Conservative but may under-deduplicate Sri Lanka repository records without DOI. | Keep conservative defaults; add reviewed fuzzy workflow before enabling. |

## Missing

| Missing capability | Why it matters | Suggested priority |
| --- | --- | --- |
| Multi-source execution from `sources` | Implemented for enabled sources with concrete collection config. The current Sri Lanka config keeps some source entries descriptive. | Closed |
| Crossref adapter wiring in Sri Lanka config | Crossref adapter support exists, including first-author Sri Lanka filtering. The config needs an affiliation query if Crossref should run directly from the framework. | Configuration task |
| SLJOL and repository adapters wired into framework config | Framework can run configured local/API/OAI sources; current legacy scripts and prepared merged CSV remain the production path for entries without adapter details. | Configuration task |
| Full API raw payload export strategy | `raw_record` now preserves complete OpenAlex payloads, but CSV files become very large and awkward to parse. | Medium |
| Database load stage | Implemented: `load_database` now loads deduplicated records into PostgreSQL `final_publications` using the latest finalized dataset columns. | Closed |
| Classification/topic modeling stages | Implemented: `classify` runs the existing model-comparison workflow and `topic_modeling` runs the existing NMF pipeline when enabled. | Closed |
| Semantic search and forecasting stages | Config has flags for these, but no pipeline implementation is wired. | Low/Medium |
| Dashboard/API implementation | The read-only API MVP and frontend routes are implemented locally; production deployment remains outside this framework audit. | Deployment task |
| Provenance report per source | Raw records are saved, but there is no source-level lineage summary for merged national outputs. | Medium |
| Data-quality thresholds | Data quality is reported, but pass/fail thresholds are not configurable. | Medium |

## Needs refactoring

| Refactor target | Current issue | Recommended direction |
| --- | --- | --- |
| `ResearchPipeline.run_all()` | Now respects `pipeline.resolve_entities`; when false, cleaned records are carried forward. | Keep enabled only when national registry enrichment is required. |
| `sources` vs `source` config model | `source` remains the explicit single-source override; `sources` can now run multiple collectable source entries when `source` is absent. | Add concrete path/API details to descriptive `sources` entries before expecting collection. |
| OpenAlex filtering logic | Framework adapter has generic strict-country filtering; legacy collector has Sri Lanka-specific broad/strict filtering. | Consolidate shared LK filtering semantics to avoid drift. |
| Source-specific metadata handling | Flattened helper fields go to `source_specific_metadata`; full API payload goes to `raw_record`. | Add explicit docs for where dashboard/API consumers should read each class of metadata. |
| Export of nested data in CSV | Lists/dicts are stringified in CSV, especially `raw_record`. | Add JSONL export for transformed/deduplicated records or keep large raw payloads in `source_records.json` only. |
| Config defaults | Some defaults still describe generic source behavior, even though project scope is Sri Lanka. | Keep flexible mechanics, but align docstrings and defaults to Sri Lanka where user-facing. |
| Test naming | Some tests validate generic adapter behavior. | Keep the tests, but ensure fixtures and names stay Sri Lanka-shaped where possible. |

## Can remain unchanged

| Area | Reason |
| --- | --- |
| Standard schema field list | It is broad enough for Sri Lanka national publication analytics and stable for exports. |
| DOI normalization and title normalization | Current behavior is simple, tested, and low-risk. |
| Conservative deduplication defaults | DOI and exact-title matching avoid unsafe merges. |
| Source adapter interface | The `connect`, `collect`, `transform`, `validate` contract is clear and sufficient. |
| CSV/JSON exports | Current export set matches national reporting needs and supports downstream dashboard work. |
| Institution alias CSV structure | Simple CSV is easy to edit and review for Sri Lanka institutions. |
| Field-aware skipped analytics | Graceful degradation is useful because source metadata completeness varies. |
| Legacy collection scripts | They remain valuable for collection, validation, and one-off maintenance while framework orchestration matures. |
| Docker and Compose defaults | They now point to the Sri Lanka config and can stay as project defaults. |

## Recommended next steps

1. Add concrete adapter details to descriptive `sources` entries when those sources should run directly through framework orchestration.
2. Document the full raw API retention policy: use `source_records.json` for complete raw payloads, and keep CSV rows focused on normalized reporting fields.
3. Add national data-quality thresholds for DOI coverage, institution resolution rate, publication year validity, and LK-only OpenAlex filtering.
4. Add deployment configuration for the API/frontend if production hosting becomes part of the project scope.
5. Mark older analysis docs as historical if their numbers do not reflect the latest regenerated outputs.
