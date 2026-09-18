# Phase 1 ETL / Data Integration Pipeline Test Report

- **Suite:** `phase1_etl_pipeline`
- **Generated (UTC):** 2026-09-12T09:19:46.850278+00:00
- **Total tests:** 78
- **Passed:** 78
- **Failed:** 0
- **Skipped:** 0
- **Pass rate:** 100.0%

## Results by category

| Category | Total | Passed | Failed | Skipped | Pass rate |
|---|---:|---:|---:|---:|---:|
| cleaning | 34 | 34 | 0 | 0 | 100.0% |
| dagster | 3 | 3 | 0 | 0 | 100.0% |
| database | 4 | 4 | 0 | 0 | 100.0% |
| deduplication | 5 | 5 | 0 | 0 | 100.0% |
| disambiguation | 6 | 6 | 0 | 0 | 100.0% |
| e2e_ingestion | 2 | 2 | 0 | 0 | 100.0% |
| entity_resolution | 9 | 9 | 0 | 0 | 100.0% |
| preprocessing | 5 | 5 | 0 | 0 | 100.0% |
| transforming | 10 | 10 | 0 | 0 | 100.0% |

## Detailed results

| Category | Outcome | Duration (s) | Test |
|---|---|---:|---|
| cleaning | passed | 0.000 | `test_clean_record_applies_configured_rules_and_provenance` |
| cleaning | passed | 0.000 | `test_invalid_doi_rejected` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[   -None]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[-None]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[10.1000/abc (online)-10.1000/abc(online]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[DOI: 10.1000/ABC.-10.1000/abc]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[None-None]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[http://dx.doi.org/10.1000/xyz;-10.1000/xyz]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[https://doi.org/10.1000/ABC-10.1000/abc]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[nan-None0]` |
| cleaning | passed | 0.000 | `test_normalize_doi_edge_cases[nan-None1]` |
| cleaning | passed | 0.000 | `test_normalize_list_like_handles_null_markers_and_separators` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[-None]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[2024-03-15-2024-03-15]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[2024-03-15T10:00:00-2024-03-15]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[2024-03-2024-03]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[2024-2024]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[None-None]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[not-a-date-None]` |
| cleaning | passed | 0.000 | `test_normalize_publication_date_edge_cases[raw5-2023-05-01]` |
| cleaning | passed | 0.000 | `test_normalize_publication_year_edge_cases[-None]` |
| cleaning | passed | 0.000 | `test_normalize_publication_year_edge_cases[2024-06-01-2024]` |
| cleaning | passed | 0.000 | `test_normalize_publication_year_edge_cases[2024-2024]` |
| cleaning | passed | 0.000 | `test_normalize_publication_year_edge_cases[None-None]` |
| cleaning | passed | 0.000 | `test_normalize_publication_year_edge_cases[no-year-None]` |
| cleaning | passed | 0.000 | `test_normalize_publication_year_edge_cases[published in 2019 somewhere-2019]` |
| cleaning | passed | 0.000 | `test_normalize_text_collapses_whitespace` |
| cleaning | passed | 0.001 | `test_normalize_title_edge_cases[  Machine   Learning\nfor  Tea  -Machine Learning for Tea]` |
| cleaning | passed | 0.000 | `test_normalize_title_edge_cases[<i>Italic</i> title-Italic title]` |
| cleaning | passed | 0.000 | `test_normalize_title_edge_cases[A &amp;amp; B-A & B]` |
| cleaning | passed | 0.000 | `test_normalize_title_edge_cases[Hello , world !-Hello, world!]` |
| cleaning | passed | 0.000 | `test_normalize_title_edge_cases[None-None]` |
| cleaning | passed | 0.000 | `test_normalize_title_edge_cases[Title<sub>2</sub>O-Title2O]` |
| cleaning | passed | 0.000 | `test_normalize_title_key_casefolds_and_strips_punctuation` |
| dagster | passed | 0.001 | `test_dagster_source_file_declares_pipeline_stages` |
| dagster | passed | 0.001 | `test_definitions_entrypoint_loads` |
| dagster | passed | 1.304 | `test_researchlanka_job_definitions_exist` |
| database | passed | 0.000 | `test_build_final_publication_row_handles_blankish_values` |
| database | passed | 0.001 | `test_build_final_publication_row_normalizes_doi_in_key` |
| database | passed | 0.000 | `test_publication_key_falls_back_to_openalex_then_source_then_title` |
| database | passed | 0.000 | `test_publication_key_prefers_doi` |
| deduplication | passed | 0.000 | `test_blank_doi_does_not_match` |
| deduplication | passed | 0.000 | `test_deduplication_disabled_returns_empty` |
| deduplication | passed | 0.001 | `test_doi_duplicates_auto_merge_even_with_different_titles` |
| deduplication | passed | 0.000 | `test_fuzzy_title_year_gap_beyond_threshold_is_rejected` |
| deduplication | passed | 0.000 | `test_title_year_exact_match_with_compatible_authors` |
| disambiguation | passed | 0.001 | `test_different_orcids_do_not_merge_even_with_same_name` |
| disambiguation | passed | 0.000 | `test_names_compatible_initial_expansion` |
| disambiguation | passed | 0.000 | `test_normalize_orcid_rejects_invalid_checksum` |
| disambiguation | passed | 0.000 | `test_parse_author_name_edge_forms` |
| disambiguation | passed | 0.001 | `test_same_orcid_merges_despite_name_variation` |
| disambiguation | passed | 0.000 | `test_split_author_field_handles_empty_and_semicolon` |
| e2e_ingestion | passed | 0.002 | `test_database_row_contract_from_pipeline_output` |
| e2e_ingestion | passed | 0.008 | `test_end_to_end_pipeline_stages` |
| entity_resolution | passed | 0.000 | `test_alias_resolves_to_preferred_institution` |
| entity_resolution | passed | 0.000 | `test_enrich_national_context_sets_collaboration_type` |
| entity_resolution | passed | 0.000 | `test_lookup_key_expands_abbreviations` |
| entity_resolution | passed | 0.000 | `test_standardize_country_edge_cases[-None]` |
| entity_resolution | passed | 0.000 | `test_standardize_country_edge_cases[LK-LK]` |
| entity_resolution | passed | 0.000 | `test_standardize_country_edge_cases[None-None]` |
| entity_resolution | passed | 0.000 | `test_standardize_country_edge_cases[Sri Lanka-LK]` |
| entity_resolution | passed | 0.000 | `test_standardize_country_edge_cases[United Kingdom-GB]` |
| entity_resolution | passed | 0.000 | `test_unknown_foreign_institution_does_not_force_lk` |
| preprocessing | passed | 0.010 | `test_clean_text_series_collapses_and_strips` |
| preprocessing | passed | 0.004 | `test_cleaning_report_counts_affected_rows` |
| preprocessing | passed | 0.000 | `test_ngram_stopword_filter_drops_function_phrases` |
| preprocessing | passed | 0.000 | `test_strip_boilerplate_placeholders` |
| preprocessing | passed | 0.000 | `test_strip_non_latin_removes_tamil_keeps_english` |
| transforming | passed | 0.000 | `test_apply_transformations_noop_when_rules_missing` |
| transforming | passed | 0.000 | `test_apply_transformations_only_touches_declared_fields` |
| transforming | passed | 0.000 | `test_map_to_standard_schema_fills_standard_fields` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[  spaced  text -rule4-spaced text]` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[  spaced  title -rule3-spaced title]` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[-rule6-expected6]` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[2024-05-01-rule0-2024]` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[A; B; C-rule1-expected1]` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[None-rule5-None]` |
| transforming | passed | 0.000 | `test_transform_value_edge_cases[https://doi.org/10.1000/X-rule2-10.1000/x]` |

## Artifacts

- CSV table: `phase1_etl_pipeline_20260912T091946Z_results.csv`
- JSON summary: `phase1_etl_pipeline_20260912T091946Z_summary.json`
- This report: `phase1_etl_pipeline_20260912T091946Z_report.md`

## Coverage intent (Phase 1)

| Area | What is validated |
|---|---|
| Cleaning | DOI/title/date/null/whitespace normalization and edge cases |
| Preprocessing | Text cleaning, source normalizers, analysis-ready prep |
| Transforming | Config-driven field transforms and schema mapping |
| Deduplication | DOI / title-year / fuzzy matches and merge decisions |
| Disambiguation | Author name/ORCID clustering and review paths |
| Entity resolution | Institution registry matching and national enrichment |
| E2E ingestion | Collect → transform → validate → clean → resolve → dedupe → export/load |
| Dagster | Asset/job wiring for the ResearchLanka pipeline |
| Database | Final row construction and upsert contract |
