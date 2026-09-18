# Phase 2 — Database Integrity, ML & API Test Report

- **Suite:** `phase2_ml_api`
- **Generated (UTC):** 2026-09-12T09:42:54.074842+00:00
- **Total tests:** 47
- **Passed:** 43
- **Failed:** 4
- **Skipped:** 0
- **Pass rate:** 91.49%

## Results by category

| Category | Total | Passed | Failed | Skipped | Pass rate |
|---|---:|---:|---:|---:|---:|
| api | 26 | 24 | 2 | 0 | 92.31% |
| classification | 4 | 4 | 0 | 0 | 100.0% |
| database_integrity | 7 | 5 | 2 | 0 | 71.43% |
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
| api | failed | 0.000 | `test_api_matrix_case[API-008]` |
| api | failed | 0.000 | `test_api_matrix_case[API-012]` |
| api | passed | 0.000 | `test_api_matrix_case[API-001]` |
| api | passed | 5.558 | `test_api_matrix_case[API-002]` |
| api | passed | 0.000 | `test_api_matrix_case[API-003]` |
| api | passed | 0.000 | `test_api_matrix_case[API-004]` |
| api | passed | 0.000 | `test_api_matrix_case[API-005]` |
| api | passed | 0.000 | `test_api_matrix_case[API-006]` |
| api | passed | 0.000 | `test_api_matrix_case[API-007]` |
| api | passed | 0.000 | `test_api_matrix_case[API-009]` |
| api | passed | 0.000 | `test_api_matrix_case[API-010]` |
| api | passed | 0.000 | `test_api_matrix_case[API-011]` |
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
| classification | passed | 0.107 | `test_hierarchical_classifier_trains_and_writes_artifacts` |
| classification | passed | 0.002 | `test_hierarchical_training_requires_label_columns` |
| classification | passed | 0.010 | `test_stratified_test_count_expands_tiny_holdout` |
| database_integrity | failed | 0.000 | `test_final_row_builder_preserves_required_identity_fields` |
| database_integrity | failed | 0.000 | `test_typed_column_sets_do_not_overlap_incorrectly` |
| database_integrity | passed | 0.000 | `test_blank_doi_does_not_collide_across_distinct_sources` |
| database_integrity | passed | 0.000 | `test_expected_core_tables_are_declared` |
| database_integrity | passed | 0.000 | `test_final_publications_table_name_and_columns_are_stable` |
| database_integrity | passed | 0.000 | `test_final_row_builder_allows_missing_title_with_stable_key` |
| database_integrity | passed | 0.000 | `test_publication_key_uniqueness_contract` |
| nmf_topic_modeling | passed | 0.001 | `test_analytics_trends_group_by_nmf_topic` |
| nmf_topic_modeling | passed | 0.004 | `test_emerging_declining_classification_from_shares` |
| nmf_topic_modeling | passed | 0.013 | `test_nmf_fit_and_keyword_extraction_smoke` |
| nmf_topic_modeling | passed | 0.002 | `test_nmf_store_lists_k25_style_topics` |
| nmf_topic_modeling | passed | 0.002 | `test_nmf_topics_api_emerging_filter` |
| semantic_search | passed | 0.077 | `test_generate_embeddings_and_semantic_search` |
| semantic_search | passed | 0.001 | `test_l2_normalized_matrix_handles_zero_rows` |
| semantic_search | passed | 0.039 | `test_related_publications_excludes_self` |
| semantic_search | passed | 0.000 | `test_semantic_search_api_requires_query` |
| semantic_search | passed | 0.000 | `test_semantic_search_api_returns_ranked_rows` |

## Failures

### `tests/phase2/test_phase2_api_matrix.py::test_api_matrix_case[API-008]`

- Category: `api`
- Message: `case = ApiCase(test_id='API-008', endpoint='GET /api/v1/search/suggest?q=Malaria', scenario='Autocomplete suggestions', expec... list with publication type', method='GET', path='/api/v1/search/suggest', query={'q': ['Malaria']}, checker='suggest') api = <src.api.services.publications.ResearchLankaAPI object at 0x7fd7fdee7ce0> request = <FixtureRequest for <Function test_api_matrix_case[API-008]>>      @pytest.mark.parametrize("case", API_CASES, ids=lambda case: case.test_id)     def test_api_matrix_case(case: ApiCase, api: ResearchLankaAPI, request: pytest.FixtureRequest):         attach_api_case(             request,             test_id=case.test_id,             endpoint=case.endpoint,             scenario=case.scenario,             expected=case.expected,         )         checker = CHEC`

### `tests/phase2/test_phase2_api_matrix.py::test_api_matrix_case[API-012]`

- Category: `api`
- Message: `case = ApiCase(test_id='API-012', endpoint='GET /api/v1/topics', scenario='Topic directory (OpenAlex fallback when NMF unavai...payload or service error handled', method='GET', path='/api/v1/topics', query={'source': ['openalex']}, checker='list') api = <src.api.services.publications.ResearchLankaAPI object at 0x7fd7fded1910> request = <FixtureRequest for <Function test_api_matrix_case[API-012]>>      @pytest.mark.parametrize("case", API_CASES, ids=lambda case: case.test_id)     def test_api_matrix_case(case: ApiCase, api: ResearchLankaAPI, request: pytest.FixtureRequest):         attach_api_case(             request,             test_id=case.test_id,             endpoint=case.endpoint,             scenario=case.scenario,             expected=case.expected,         )         checker = CHEC`

### `tests/phase2/test_phase2_database_integrity.py::test_typed_column_sets_do_not_overlap_incorrectly`

- Category: `database_integrity`
- Message: `def test_typed_column_sets_do_not_overlap_incorrectly():         assert INTEGER_COLUMNS.isdisjoint(BOOLEAN_COLUMNS)         for column in INTEGER_COLUMNS | BOOLEAN_COLUMNS: >           assert column in DATABASE_PUBLICATION_COLUMNS E           AssertionError: assert 'citation_count' in ('source_dataset', 'source_institution_id', 'source_record_id', 'source_datestamp', 'openalex_id', 'doi', ...)  tests/phase2/test_phase2_database_integrity.py:52: AssertionError`

### `tests/phase2/test_phase2_database_integrity.py::test_final_row_builder_preserves_required_identity_fields`

- Category: `database_integrity`
- Message: `def test_final_row_builder_preserves_required_identity_fields():         row = build_final_publication_row(             {                 "source_name": "openalex",                 "source_record_id": "W100",                 "doi": "https://doi.org/10.1000/Integrity",                 "title": "Integrity check paper",                 "publication_year": 2024,                 "authors": ["A. Author"],                 "institutions": ["University of Colombo"],                 "primary_field": "Medicine",                 "primary_subfield": "Public Health",                 "is_oa": True,                 "citation_count": 3,             },             row_number=1,         )         assert row["publication_key"] == "doi:10.1000/integrity"         assert row["doi"] == "10.1000/integrity"        `


## API test matrix summary

- Cases: 26
- Passed: 24
- Failed: 2
- Skipped: 0

Full matrix: `phase2_ml_api_20260912T094254Z_api_matrix.md` / `phase2_ml_api_20260912T094254Z_api_matrix.csv`

## Artifacts

- CSV table: `phase2_ml_api_20260912T094254Z_results.csv`
- JSON summary: `phase2_ml_api_20260912T094254Z_summary.json`
- This report: `phase2_ml_api_20260912T094254Z_report.md`
