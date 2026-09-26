# ResearchLanka AI Project Functionality Map

This document summarizes the main functionality present in the project, grouped by what the code does.

## 1. Data Collection

### Crossref Collection

Files:
- `backend/scripts/collection/collect_crossref.py`
- `backend/src/pipeline/collect_crossref.py`
- `backend/src/collectors/crossref_collector.py`

Functionality:
- Collects publication metadata from Crossref.
- Normalizes Crossref records into project-friendly fields.
- Handles DOI/title/date/publisher/journal metadata.

### OpenAlex Collection

Files:
- `backend/scripts/collection/kaggle_collect_openalex_sri_lanka.py`
- `backend/src/pipeline/kaggle_collect_openalex_sri_lanka.py`
- `backend/src/collectors/openalex_collector.py`

Functionality:
- Collects Sri Lanka-related publication records from OpenAlex.
- Supports AI/publication metadata enrichment from OpenAlex topics, concepts, institutions, authors, DOI, venue, and citation metadata.

### SLJOL Collection

Files:
- `backend/scripts/collection/collect_sljol.py`
- `backend/src/pipeline/collect_sljol.py`

Functionality:
- Collects publication records from Sri Lanka Journals Online sources.
- Adds local journal/repository records into the larger ResearchLanka corpus.

### Repository Collection

Files:
- `backend/scripts/collection/harvest_oai.py`
- `backend/scripts/collection/harvest_oai_by_set.py`
- `backend/scripts/collection/harvest_dspace_rest.py`
- `backend/scripts/collection/harvest_html_meta.py`
- `backend/scripts/collection/harvest_large_repository.py`
- `backend/scripts/collection/harvest_all.py`
- `backend/src/collectors/oai_pmh_collector.py`
- `backend/src/collectors/dspace_rest_collector.py`
- `backend/src/collectors/html_meta_collector.py`
- `backend/src/collectors/sitemap_collector.py`
- `backend/src/collectors/repository_registry.py`

Functionality:
- Harvests university/repository publications through OAI-PMH.
- Harvests DSpace REST API metadata.
- Harvests HTML metadata from repository pages.
- Discovers repository URLs using sitemap logic.
- Combines multiple repository harvest methods.

## 2. Schema Mapping and Normalization

### Common Schema Mapping

Files:
- `backend/scripts/processing/map_to_common_schema.py`
- `backend/src/processing/map_to_common_schema.py`
- `backend/src/collectors/schema_mapping.py`

Functionality:
- Maps different source formats into one common publication schema.
- Standardizes source-specific field names into shared project columns.

### Final Dataset Building

Files:
- `backend/scripts/processing/build_final_common_dataset.py`
- `backend/src/pipeline/build_final_common_dataset.py`
- `backend/scripts/processing/kaggle_merge_common_dataset.py`
- `backend/src/pipeline/kaggle_merge_common_dataset.py`

Functionality:
- Merges OpenAlex, Crossref, SLJOL, and repository records.
- Creates the consolidated final publication dataset.
- Applies source priority rules when multiple sources contain the same metadata.
- Produces final common publication CSV outputs.

### Year Filtering

Files:
- `backend/scripts/processing/build_year_filtered_dataset.py`
- `backend/src/pipeline/build_year_filtered_dataset.py`

Functionality:
- Filters publication records by year range.
- Used for the 2016-2026 ResearchLanka dataset.

### Language Normalization

Files:
- `backend/scripts/processing/build_language_normalized_dataset.py`
- `backend/src/pipeline/build_language_normalized_dataset.py`

Functionality:
- Normalizes language-related fields.
- Helps clean mixed-language or missing-language metadata.

### Multi-value Normalization

Files:
- `backend/scripts/processing/build_multivalue_normalized_dataset.py`
- `backend/src/pipeline/build_multivalue_normalized_dataset.py`

Functionality:
- Normalizes fields that contain multiple values.
- Useful for authors, institutions, countries, keywords, topics, and similar repeated metadata.

### Type, Journal, and Venue Normalization

Files:
- `backend/src/pipeline/build_type_journal_normalized_dataset.py`
- `backend/src/utils/journal_utils.py`
- `backend/src/utils/publisher_utils.py`

Functionality:
- Normalizes publication type.
- Cleans journal/venue/publisher names.
- Helps make publication type and venue analytics consistent.

### Institution Normalization

Files:
- `backend/src/pipeline/build_institution_normalized_dataset.py`
- `backend/src/pipeline/build_institution_registry.py`

Functionality:
- Normalizes institution names.
- Builds institution registry/aliases.
- Improves Sri Lankan institution matching and analytics.

### Author Disambiguation

Files:
- `backend/src/pipeline/build_author_disambiguated_dataset.py`
- `backend/src/utils/author_utils.py`
- `backend/scripts/extraction/extract_authors.py`

Functionality:
- Extracts author metadata.
- Helps normalize and disambiguate author names.
- Supports researcher pages and collaboration analytics.

## 3. Abstract, Keyword, and Text Enrichment

### Abstract Extraction

Files:
- `backend/scripts/extraction/extract_publication_abstracts_for_model.py`

Functionality:
- Extracts non-empty abstracts from the final dataset.
- Creates model-ready abstract text fields.
- Produces cleaned and normalized abstract text.

### Title Extraction

Files:
- `backend/scripts/extraction/extract_publication_titles_for_model.py`
- `backend/scripts/extraction/extract_titles.py`

Functionality:
- Extracts publication titles for modeling and quality checks.
- Creates cleaned title data for downstream model pipelines.

### Keyword Extraction

Files:
- `backend/scripts/extraction/extract_publication_keywords_for_model.py`

Functionality:
- Extracts and prepares keywords for model training.
- Combines keyword metadata with title/abstract text.

### Merge Fetched or Scraped Abstracts

Files:
- `backend/scripts/processing/merge_scraped_results_with_dataset.py`
- `backend/Makefile` target: `make enrich-missing-text`
- `backend/Makefile` target: `make final-common-enriched`

Functionality:
- Merges fetched/scraped `title`, `abstract`, and `keywords` into a current dataset.
- Matches by DOI, OpenAlex ID, or source record ID.
- By default, only fills blank values and preserves existing metadata.
- Can overwrite existing fields if `--overwrite-existing` is used.
- This step should run after data fetching/collection and before preprocessing/model-ready dataset creation.
- If `abstract` or `keywords` are missing, the pipeline tries to fill them from the fetched metadata file.
- Downstream text/model targets now default to `common_publications_final_text_enriched.csv`, so they use enriched abstracts/keywords.

Recent use:
- Merged `backend/data/processed/common/abstract_fetched.csv`.
- Filled missing abstracts and keywords in the final AI-classified dataset.

### Text Cleaning

Files:
- `backend/src/preprocessing/text_cleaning.py`

Functionality:
- Cleans noisy title/abstract/keyword text.
- Removes boilerplate such as “abstract available” and similar non-content strings.
- Normalizes text for model training and inference.

## 4. Duplicate and Record Quality Analysis

### Missed Duplicate Analysis

Files:
- `backend/scripts/quality/analyze_missed_duplicate_records.py`
- `backend/src/quality/analyze_missed_duplicate_records.py`

Functionality:
- Finds records that should probably have been merged but were missed.
- Helps identify duplicate publications across sources.

### False Duplicate Analysis

Files:
- `backend/scripts/quality/analyze_false_duplicate_matches.py`
- `backend/src/quality/analyze_false_duplicate_matches.py`

Functionality:
- Audits cases where records may have been incorrectly merged.
- Helps detect bad DOI/title/source matches.

### DOI Comparison

Files:
- `backend/scripts/quality/compare_dois.py`
- `backend/src/quality/compare_dois.py`
- `backend/src/utils/doi.py`

Functionality:
- Normalizes DOI strings.
- Compares DOI overlap between datasets.
- Finds missing, invalid, duplicate, or conflicting DOI records.

### Publication Count Comparison

Files:
- `backend/scripts/quality/compare_publication_counts.py`
- `backend/src/quality/compare_publication_counts.py`

Functionality:
- Compares publication counts across datasets/sources.
- Helps verify whether pipeline steps lost or duplicated records.

### Harvested Data Validation

Files:
- `backend/scripts/quality/validate_harvested_data.py`
- `backend/src/quality/validate_harvested_data.py`

Functionality:
- Validates harvested raw/source data.
- Checks required metadata and basic record health.

### Repository Validation

Files:
- `backend/scripts/quality/validate_repositories.py`
- `backend/src/quality/validate_repositories.py`

Functionality:
- Validates harvested repository datasets.
- Checks repository records before they are added into the final corpus.

### AI Release Dataset Validation

Files:
- `backend/scripts/quality/validate_ai_release_dataset.py`
- `backend/src/quality/validate_ai_release_dataset.py`

Functionality:
- Validates final AI-publication release files.
- Checks required fields, labels, ownership decisions, DOI quality, and release-readiness.

## 5. Sri Lanka Ownership and Affiliation Auditing

### OpenAlex Sri Lanka Affiliation Audit

Files:
- `backend/scripts/quality/audit_openalex_lk_affiliations.py`
- `backend/src/quality/audit_openalex_lk_affiliations.py`

Functionality:
- Audits whether OpenAlex records genuinely involve Sri Lankan authors/institutions.
- Helps identify false Sri Lanka matches.
- Supports ownership and inclusion/exclusion decisions.

### Crossref Sri Lanka Affiliation Audit

Files:
- `backend/scripts/quality/audit_crossref_lk_affiliations.py`
- `backend/src/quality/audit_crossref_lk_affiliations.py`

Functionality:
- Audits Crossref affiliation evidence for Sri Lanka relevance.
- Helps validate inclusion in the national research corpus.

### Google Maps Institution Location Evidence

Files:
- `backend/scripts/quality/confirm_institution_locations_google_maps.py`
- `backend/src/quality/confirm_institution_locations_google_maps.py`
- `backend/scripts/processing/apply_google_maps_location_evidence.py`
- `backend/src/pipeline/apply_google_maps_location_evidence.py`

Functionality:
- Confirms institution locations using Google Maps-derived evidence.
- Applies location evidence to improve Sri Lanka institution validation.

### Ownership Logic

Files:
- `backend/src/preprocessing/ownership.py`

Functionality:
- Encodes logic for publication ownership/eligibility.
- Helps decide whether a publication belongs in the Sri Lanka-focused corpus.

## 6. AI Relevance Classification

### SVM Training and Prediction

Files:
- `backend/scripts/ai_relevance/train_ai_relevance_svm.py`
- `backend/scripts/ai_relevance/predict_ai_relevance_svm.py`
- `backend/src/ai_relevance/svm_model.py`

Functionality:
- Trains a Linear SVM AI relevance classifier.
- Predicts AI / non-AI / review labels.
- Uses text fields such as title, abstract, keywords, topics, and concepts.

### Gemini / OpenRouter AI Relevance Labelling

Files:
- `backend/scripts/ai_relevance/run_gemini_ai_relevance.py`
- `backend/scripts/ai_relevance/add_openrouter_gemini_predictions.py`
- `backend/src/ai_relevance/gemini_client.py`
- `backend/src/ai_relevance/prompt.py`
- `backend/src/ai_relevance/runner.py`
- `backend/src/ai_relevance/schema.py`
- `backend/src/ai_relevance/config.py`

Functionality:
- Sends publication metadata to Gemini/OpenRouter for AI relevance classification.
- Uses structured prompts and response schemas.
- Stores LLM label, confidence, category, reason, and evidence.

### AI Relevance Sampling and Human Review

Files:
- `backend/scripts/ai_relevance/build_ai_candidate_sample.py`
- `backend/scripts/ai_relevance/export_human_review_sample.py`
- `backend/src/ai_relevance/sampling.py`
- `backend/src/ai_relevance/review.py`

Functionality:
- Builds candidate samples for AI relevance review.
- Exports human-review datasets.
- Supports stratified sampling and review workflows.

### Human Verification Metrics

Files:
- `backend/scripts/ai_relevance/evaluate_gemini_human_labels.py`
- `backend/scripts/ai_relevance/evaluate_ollama_human_verification.py`
- `backend/scripts/ai_relevance/compare_human_verification_model_scores.py`
- `backend/src/ai_relevance/evaluation.py`
- `backend/src/ai_relevance/human_verification_metrics.py`

Functionality:
- Compares model/LLM labels against human labels.
- Computes accuracy, precision, recall, F1, confusion matrices, and agreement metrics.
- Helps understand where AI relevance predictions fail.

### AI Publication Dataset Build

Files:
- `backend/src/pipeline/classify_ai_relevance_dataset.py`
- `backend/src/pipeline/build_ai_publication_dataset.py`

Functionality:
- Applies AI relevance model to the publication corpus.
- Produces classified dataset with `ai_classification_label`, confidence, model, and reason.
- Builds AI-only or AI-review-filtered datasets for downstream dashboard/database loading.

## 7. Model Training, Evaluation, and Feature Engineering

### General Training Pipeline

Files:
- `backend/src/modeling/training.py`
- `backend/src/modeling/inference.py`
- `backend/src/modeling/artifacts.py`

Functionality:
- Trains publication classifiers.
- Runs inference.
- Saves and loads model artifacts.

### Linear SVM Models

Files:
- `backend/scripts/modeling/train_linear_svm_classifier.py`
- `backend/scripts/modeling/train_linear_svm_hierarchical.py`
- `backend/scripts/modeling/compare_linear_svc_configs.py`
- `backend/src/modeling/linear_svm_training.py`
- `backend/src/modeling/linear_svc_evaluation.py`
- `backend/src/modeling/hierarchical_linear_svm.py`

Functionality:
- Trains Linear SVM classifiers.
- Supports hierarchical classification.
- Compares SVM configurations.

### Logistic Regression and Other Model Comparison

Files:
- `backend/scripts/modeling/train_logistic_regression_classifier.py`
- `backend/scripts/modeling/compare_classification_models.py`
- `backend/src/modeling/classification_comparison.py`
- `backend/src/modeling/evaluation.py`

Functionality:
- Trains Logistic Regression classifiers.
- Compares multiple classification models.
- Evaluates model performance using standard classification metrics.

### Dataset Splitting

Files:
- `backend/scripts/modeling/create_dataset_splits.py`
- `backend/src/modeling/dataset_splits.py`

Functionality:
- Creates train/test/validation splits.
- Supports reproducible model evaluation.
- Helps prevent train/test leakage.

### TF-IDF Feature Building

Files:
- `backend/scripts/extraction/build_publication_tfidf_features.py`

Functionality:
- Builds TF-IDF features from publication text.
- Uses fields such as title, abstract, and keywords.

### Text Embeddings

Files:
- `backend/scripts/modeling/generate_publication_text_embeddings.py`
- `backend/src/modeling/embeddings.py`

Functionality:
- Generates vector embeddings for publication text.
- Supports embedding-based model experiments and similarity workflows.

### Topic Modeling

Files:
- `backend/scripts/modeling/run_nmf_topic_modeling.py`
- `backend/src/modeling/nmf_topic_modeling.py`
- `backend/src/modeling/nmf_trends.py`
- `backend/src/api/services/nmf_topics.py`
- `backend/src/api/repositories/nmf_topics.py`

Functionality:
- Runs NMF topic modeling on publication text.
- Produces topic trends over time.
- Exposes topic data through API services.

### Field/Subfield Prediction

Files:
- `backend/scripts/modeling/predict_field_subfield.py`
- `backend/scripts/modeling/predict_publication_classifier.py`

Functionality:
- Predicts publication field/subfield/category labels.
- Applies trained classifiers to publication records.

## 8. Incremental Updates

Files:
- `backend/scripts/admin/run_incremental_update_job.py`
- `backend/src/pipeline/incremental_update.py`
- `backend/src/api/services/incremental_admin.py`
- `frontend/src/app/admin/pipeline/page.tsx`
- `frontend/src/app/api/admin/incremental/run/route.ts`
- `frontend/src/app/api/admin/incremental/status/route.ts`

Functionality:
- Runs incremental data updates.
- Collects new records after an existing pipeline state.
- Classifies new incoming records.
- Loads incremental updates into the database.
- Exposes admin UI/API controls for pipeline runs.

## 9. Database and Migrations

### Database Connection and Loading

Files:
- `backend/scripts/database/load_records.py`
- `backend/src/database/load_records.py`
- `backend/src/database/loader.py`
- `backend/src/database/connection.py`

Functionality:
- Loads CSV/JSON/JSONL records into PostgreSQL.
- Upserts final publications.
- Populates normalized relational tables.
- Backfills AI review records after load.

### Migrations

Files:
- `backend/scripts/database/apply_database_migrations.py`
- `backend/src/database/apply_database_migrations.py`
- `backend/database/migrations/*.sql`
- `backend/database/national_research_schema.sql`

Functionality:
- Applies PostgreSQL schema migrations.
- Creates final publication tables.
- Adds ownership columns.
- Adds AI classification columns.
- Creates AI review workflow tables.
- Creates accepted AI publication views.

### Database Verification

Files:
- `backend/scripts/database/check_database_connection.py`
- `backend/scripts/database/verify_database_schema.py`
- `backend/src/database/check_database_connection.py`
- `backend/src/database/verify_database_schema.py`

Functionality:
- Checks database connectivity.
- Verifies expected schema/tables/columns.

### Pipeline State

Files:
- `backend/src/database/pipeline_state.py`

Functionality:
- Stores and reads pipeline state for incremental updates.

## 10. API Backend

### API Serving

Files:
- `backend/scripts/api/serve_api.py`
- `backend/src/api/server.py`
- `backend/src/api/fastapi_app.py`
- `backend/src/api/transport/fastapi_app.py`
- `backend/src/api/transport/http_server.py`
- `backend/src/api/routing/routes.py`

Functionality:
- Serves the ResearchLanka backend API.
- Provides publication, analytics, admin, AI review, and model endpoints.

### Publication Services

Files:
- `backend/src/api/services/publications.py`
- `backend/src/api/repositories/postgres.py`
- `backend/src/api/repositories/sql.py`
- `backend/src/api/core/query.py`
- `backend/src/api/core/serializers.py`

Functionality:
- Searches and filters publications.
- Provides publication detail pages.
- Provides analytics overview, trends, institutions, fields, topics, collaboration, and data quality metrics.
- Uses the accepted AI publication view for public AI dashboard pages.

### Exports

Files:
- `backend/src/api/core/exports.py`
- `backend/src/api/exports.py`

Functionality:
- Generates CSV/export responses from API data.

### Model Serving

Files:
- `backend/src/api/services/model_serving.py`
- `backend/src/api/model_service.py`
- `backend/src/api/schemas/model_prediction.py`

Functionality:
- Serves model prediction endpoints.
- Accepts publication metadata and returns classification predictions.

## 11. AI Review Workflow

Files:
- `backend/scripts/admin/ai_review_workflow.py`
- `backend/src/api/services/ai_review.py`
- `backend/src/api/services/ai_review_sheets.py`
- `frontend/src/app/admin/ai-review/page.tsx`
- `frontend/src/components/admin/AIReviewCard.tsx`
- `frontend/src/services/workspace/aiReview.ts`
- `frontend/src/services/workspace/types.ts`

Functionality:
- Backfills AI review records from final publications.
- Assigns records to reviewers.
- Tracks pending, auto accepted, human accepted, and human rejected statuses.
- Supports human review decisions.
- Supports Google Sheets sync for review records.
- Provides admin review queue UI.

## 12. Frontend Dashboard and User Interface

### Main Analytics Pages

Files:
- `frontend/src/app/page.tsx`
- `frontend/src/app/publications/page.tsx`
- `frontend/src/app/researchers/page.tsx`
- `frontend/src/app/institutions/page.tsx`
- `frontend/src/app/topics/page.tsx`
- `frontend/src/app/collaboration/page.tsx`
- `frontend/src/app/data-quality/page.tsx`

Functionality:
- Shows AI research overview.
- Lists AI publications.
- Provides researcher, institution, topic, and collaboration views.
- Shows data quality and metadata completeness.

### Detail Pages

Files:
- `frontend/src/app/publications/[...key]/page.tsx`
- `frontend/src/app/researchers/[...key]/page.tsx`
- `frontend/src/app/institutions/[...key]/page.tsx`
- `frontend/src/app/topics/[...key]/page.tsx`

Functionality:
- Shows detailed pages for individual publications, researchers, institutions, and topics.

### Admin Pages

Files:
- `frontend/src/app/admin/page.tsx`
- `frontend/src/app/admin/ai-review/page.tsx`
- `frontend/src/app/admin/pipeline/page.tsx`
- `frontend/src/app/admin/review/page.tsx`
- `frontend/src/app/admin/flags/page.tsx`
- `frontend/src/app/admin/users/page.tsx`

Functionality:
- Provides admin dashboard.
- Shows AI review queue.
- Shows pipeline controls/status.
- Shows flags and account/user administration views.

### Auth and Account

Files:
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/register/page.tsx`
- `frontend/src/app/account/page.tsx`
- `frontend/src/app/account/flags/page.tsx`
- `frontend/src/app/account/saved/page.tsx`
- `frontend/src/services/auth/*`
- `frontend/src/components/auth/*`

Functionality:
- Supports login/register/account pages.
- Handles session and permission logic.
- Provides account menu and role badges.

### Charts, Tables, Filters, and UI Components

Files:
- `frontend/src/components/charts/*`
- `frontend/src/components/analytics/*`
- `frontend/src/components/ui/*`
- `frontend/src/components/publications/*`
- `frontend/src/components/network/*`
- `frontend/src/components/search/SearchBox.tsx`
- `frontend/src/components/layout/*`

Functionality:
- Renders charts, ranking bars, distribution charts, collaboration network, tables, pagination, filter panels, search box, stat tiles, CSV downloads, layout, navigation, and theme toggle.

## 13. Collaboration and Network Analytics

Files:
- `backend/src/analytics/network.py`
- `frontend/src/components/network/CollaborationNetwork.tsx`
- `frontend/src/components/network/NetworkMetrics.tsx`

Functionality:
- Builds collaboration networks between researchers, institutions, countries, or other entities.
- Computes network edges and metrics.
- Displays interactive collaboration visualizations.

## 14. Data Quality Dashboard

Files:
- `frontend/src/app/data-quality/page.tsx`
- `frontend/src/components/analytics/QualityCompleteness.tsx`
- `backend/src/api/services/publications.py`
- `backend/src/api/repositories/postgres.py`

Functionality:
- Shows metadata completeness.
- Shows DOI coverage, abstract coverage, source coverage, and data limitations.
- Uses accepted AI publications as the public dashboard denominator.

## 15. Manual Review UI and Quality Workflows

Files:
- `backend/scripts/quality/manual_review_ui.py`
- `backend/src/quality/manual_review_ui.py`
- `backend/src/quality/review_ambiguous_authors.py`

Functionality:
- Provides local/manual review support for ambiguous records.
- Helps review authors, metadata, and publication records.

## 16. Utility Modules

Files:
- `backend/src/utils/io_utils.py`
- `backend/src/utils/file_naming.py`
- `backend/src/utils/column_resolve.py`
- `backend/src/utils/title_utils.py`
- `backend/src/utils/date_utils.py`
- `backend/src/utils/doi.py`
- `backend/src/utils/author_utils.py`
- `backend/src/utils/journal_utils.py`
- `backend/src/utils/publisher_utils.py`
- `backend/src/utils/referece_utils.py`

Functionality:
- File reading/writing helpers.
- Standardized file naming.
- Column matching/resolution helpers.
- DOI normalization.
- Title normalization.
- Date parsing/normalization.
- Author, journal, publisher, and reference utilities.

## 17. Column and Metadata Analysis

Files:
- `backend/scripts/analysis/columns/analyze_first_25_columns.py`
- `backend/scripts/analysis/columns/analyze_second_25_columns.py`
- `backend/scripts/analysis/columns/analyze_final_26_columns.py`
- `backend/docs/00_metadata_quality_report_index.md`
- `backend/docs/01_metadata_enrichment.md`
- `backend/docs/03_missing_values_analysis.md`
- `backend/docs/04_metadata_completeness_analysis.md`
- `backend/docs/05_conflicting_metadata_analysis.md`
- `backend/docs/06_field_level_data_quality.md`

Functionality:
- Analyzes dataset columns.
- Documents missing values, conflicting metadata, field-level quality, and metadata enrichment decisions.

## 18. Reporting and Pipeline Documentation

Files:
- `backend/scripts/verify_pipeline_outputs_for_report.py`
- `backend/docs/PIPELINE_RUNBOOK.md`
- `backend/docs/SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md`
- `backend/docs/BACKEND_ARCHITECTURE_MAP.md`
- `backend/docs/API_DESIGN.md`
- `backend/docs/DATA_COLLECTION.md`
- `backend/docs/normalization_and_merge.md`
- `backend/docs/AI_RELEVANCE_PIPELINE.md`
- `backend/docs/AI_RELEVANCE_MODEL_SELECTION.md`

Functionality:
- Documents pipeline structure.
- Documents API design and backend architecture.
- Documents AI relevance classification pipeline and model-selection process.
- Verifies pipeline outputs for reports.

## 19. Deployment and Runtime

Files:
- `backend/compose.yml`
- `compose.aws.yml`
- `backend/Makefile`
- `Makefile`

Functionality:
- Runs backend services and database dependencies.
- Provides Makefile commands for common pipeline, database, API, and model tasks.
- Supports local and AWS/container deployment workflows.

## 20. Recent Final AI Dataset Workflow

Recent workflow outputs and actions:
- Final binary AI/non-AI classification was loaded into PostgreSQL.
- Remaining review rows were predicted with the selected AI relevance model.
- Fetched abstracts were merged into the final classified dataset.
- AI review workflow statuses were synced so the dashboard counts accepted AI records correctly.

Important final dataset state:
- AI publications: `4,058`
- non-AI publications: `37,005`
- review publications: `0`
- total publications: `41,063`
- AI abstract coverage after fetched abstract merge: `80.3%`

Important final data artifact:
- `backend/data/processed/common/common_publications_final_2016_2026_ai_classified_all_review_binary_resolved_abstracts_merged.csv`

Important dashboard source:
- Public dashboard pages use `accepted_ai_publications`, not only `final_publications.ai_classification_label`.
- `accepted_ai_publications` depends on `ai_review_records.review_status`.
