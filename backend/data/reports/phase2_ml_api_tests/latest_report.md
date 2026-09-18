# Phase 2 — Database Integrity, ML & API Test Report

- **Suite:** `phase2_ml_api`
- **Generated (UTC):** 2026-09-12T09:45:34.635304+00:00
- **Total tests:** 47
- **Passed:** 47
- **Failed:** 0
- **Skipped:** 0
- **Pass rate:** 100.0%

## Results by category

| Category | Total | Passed | Failed | Skipped | Pass rate |
|---|---:|---:|---:|---:|---:|
| api | 26 | 26 | 0 | 0 | 100.0% |
| classification | 4 | 4 | 0 | 0 | 100.0% |
| database_integrity | 7 | 7 | 0 | 0 | 100.0% |
| nmf_topic_modeling | 5 | 5 | 0 | 0 | 100.0% |
| semantic_search | 5 | 5 | 0 | 0 | 100.0% |

## Coverage intent (Phase 2)

| Area | What is validated |
|---|---|
| Database integrity | Schema contract, required tables/columns, key uniqueness rules |
| Classification | Hierarchical field→subfield training/inference contracts |
| NMF topic modeling | k=25 trends, emerging/declining labels, topic API integration |
| Semantic search | Embedding index search/related ranking contracts |
| API | Endpoint matrix (Test ID / Endpoint / Scenario / Expected / Result) |

## Detailed results

| Category | Outcome | Duration (s) | Test |
|---|---|---:|---|
| api | passed | 0.000 | `test_api_matrix_case[API-001]` |
| api | passed | 4.930 | `test_api_matrix_case[API-002]` |
| api | passed | 0.000 | `test_api_matrix_case[API-003]` |
| api | passed | 0.000 | `test_api_matrix_case[API-004]` |
| api | passed | 0.000 | `test_api_matrix_case[API-005]` |
| api | passed | 0.000 | `test_api_matrix_case[API-006]` |
| api | passed | 0.000 | `test_api_matrix_case[API-007]` |
| api | passed | 0.000 | `test_api_matrix_case[API-008]` |
| api | passed | 0.000 | `test_api_matrix_case[API-009]` |
| api | passed | 0.000 | `test_api_matrix_case[API-010]` |
| api | passed | 0.000 | `test_api_matrix_case[API-011]` |
| api | passed | 0.000 | `test_api_matrix_case[API-012]` |
| api | passed | 0.000 | `test_api_matrix_case[API-013]` |
| api | passed | 0.000 | `test_api_matrix_case[API-014]` |
| api | passed | 0.000 | `test_api_matrix_case[API-015]` |
| api | passed | 0.000 | `test_api_matrix_case[API-016]` |
| api | passed | 0.000 | `test_api_matrix_case[API-017]` |
| api | passed | 0.000 | `test_api_matrix_case[API-018]` |
| api | passed | 0.000 | `test_api_matrix_case[API-019]` |
| api | passed | 0.000 | `test_api_matrix_case[API-020]` |
| api | passed | 0.000 | `test_api_matrix_case[API-021]` |
| api | passed | 0.000 | `test_api_matrix_case[API-022]` |
| api | passed | 0.000 | `test_api_matrix_case[API-023]` |
| api | passed | 0.000 | `test_api_matrix_case[API-024]` |
| api | passed | 0.000 | `test_api_matrix_case[API-025]` |
| api | passed | 0.000 | `test_api_matrix_case[API-026]` |
| classification | passed | 0.000 | `test_default_classification_artifact_names` |
| classification | passed | 0.098 | `test_hierarchical_classifier_trains_and_writes_artifacts` |
| classification | passed | 0.001 | `test_hierarchical_training_requires_label_columns` |
| classification | passed | 0.002 | `test_stratified_test_count_expands_tiny_holdout` |
| database_integrity | passed | 0.000 | `test_blank_doi_does_not_collide_across_distinct_sources` |
| database_integrity | passed | 0.000 | `test_expected_core_tables_are_declared` |
| database_integrity | passed | 0.000 | `test_final_publications_table_name_and_columns_are_stable` |
| database_integrity | passed | 0.000 | `test_final_row_builder_allows_missing_title_with_stable_key` |
| database_integrity | passed | 0.001 | `test_final_row_builder_preserves_required_identity_fields` |
| database_integrity | passed | 0.000 | `test_publication_key_uniqueness_contract` |
| database_integrity | passed | 0.000 | `test_typed_column_sets_do_not_overlap_incorrectly` |
| nmf_topic_modeling | passed | 0.001 | `test_analytics_trends_group_by_nmf_topic` |
| nmf_topic_modeling | passed | 0.004 | `test_emerging_declining_classification_from_shares` |
| nmf_topic_modeling | passed | 0.008 | `test_nmf_fit_and_keyword_extraction_smoke` |
| nmf_topic_modeling | passed | 0.002 | `test_nmf_store_lists_k25_style_topics` |
| nmf_topic_modeling | passed | 0.002 | `test_nmf_topics_api_emerging_filter` |
| semantic_search | passed | 0.050 | `test_generate_embeddings_and_semantic_search` |
| semantic_search | passed | 0.001 | `test_l2_normalized_matrix_handles_zero_rows` |
| semantic_search | passed | 0.035 | `test_related_publications_excludes_self` |
| semantic_search | passed | 0.000 | `test_semantic_search_api_requires_query` |
| semantic_search | passed | 0.000 | `test_semantic_search_api_returns_ranked_rows` |

## API test matrix summary

- Cases: 26
- Passed: 26
- Failed: 0
- Skipped: 0

Full matrix: `phase2_ml_api_20260912T094534Z_api_matrix.md` / `phase2_ml_api_20260912T094534Z_api_matrix.csv`

## Artifacts

- CSV table: `phase2_ml_api_20260912T094534Z_results.csv`
- JSON summary: `phase2_ml_api_20260912T094534Z_summary.json`
- This report: `phase2_ml_api_20260912T094534Z_report.md`
