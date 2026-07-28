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
| `sources` block in Sri Lanka config | Lists OpenAlex, Crossref, SLJOL, and repository source groups. | Active execution still uses a single `source`/`input` path, while `sources` is mostly descriptive. | Decide whether multi-source orchestration should be implemented or whether `sources` should become documentation-only metadata. |
| Entity resolution | Resolves exact normalized aliases from the Sri Lanka registry. | No fuzzy/identifier-based matching for institution variants outside the alias file. | Add ROR-aware and controlled fuzzy matching for unresolved Sri Lanka affiliations. |
| Collaboration analytics | Classifies domestic and international collaboration. | Collaboration edges are built from institution co-occurrence only; author-level or funder-level networks are not represented. | Add optional author, funder, and country collaboration exports if needed by the dashboard. |
| Source validation | Preview and validation work for adapter records. | Validation report is mostly structural; it does not fully assess Sri Lanka-specific metadata quality thresholds. | Add national validation checks for LK association, institution resolution rate, DOI coverage, and year ranges. |
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
| Multi-source execution from `sources` | Sri Lanka data sources are listed, but the framework currently runs one active source at a time. | High |
| Crossref adapter wiring in Sri Lanka config | Crossref is listed as enabled but not fully configured as an active framework source. | High |
| SLJOL and repository adapters wired into framework config | Legacy scripts collect these sources, but framework orchestration does not yet collect all of them end-to-end. | High |
| Full API raw payload export strategy | `raw_record` now preserves complete OpenAlex payloads, but CSV files become very large and awkward to parse. | Medium |
| Database load stage | `load_database` exists in config but is not implemented in `ResearchPipeline.run_all()`. | Medium |
| Classification/topic modeling stages | `classify` and `topic_modeling` flags exist but do not drive implemented stages. | Medium |
| Semantic search and forecasting stages | Config has flags for these, but no pipeline implementation is wired. | Low/Medium |
| Dashboard/API serving layer | Exports exist, but no framework-owned API/dashboard layer is connected here. | Medium |
| Provenance report per source | Raw records are saved, but there is no source-level lineage summary for merged national outputs. | Medium |
| Data-quality thresholds | Data quality is reported, but pass/fail thresholds are not configurable. | Medium |

## Needs refactoring

| Refactor target | Current issue | Recommended direction |
| --- | --- | --- |
| `ResearchPipeline.run_all()` | Always calls `resolve_entities()` even when `pipeline.resolve_entities` is false. | Respect the stage flag or remove the unused flag. |
| `sources` vs `source` config model | Both exist, but only one source is actively built by `build_adapter_from_config()`. | Choose one model for Sri Lanka production runs, or implement a `MultiSourcePipeline`. |
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

1. Decide whether the production framework should execute all Sri Lanka sources from the `sources` block, or keep using the merged CSV as the single active input.
2. If multi-source execution is needed, add a `MultiSourcePipeline` that collects each enabled Sri Lanka source, preserves source provenance, and merges before cleaning/deduplication.
3. Document the full raw API retention policy: use `source_records.json` for complete raw payloads, and keep CSV rows focused on normalized reporting fields.
4. Add national data-quality thresholds for DOI coverage, institution resolution rate, publication year validity, and LK-only OpenAlex filtering.
5. Mark older analysis docs as historical if their numbers do not reflect the latest regenerated outputs.
