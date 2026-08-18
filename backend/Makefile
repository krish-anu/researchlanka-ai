.DEFAULT_GOAL := help

# Python commands. Override these if you want to use a different environment:
#   make test PYTHON=python
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

# Reusable national framework settings.
NATIONAL_CONFIG ?= configurations/sri_lanka/config.json
NATIONAL_SAMPLE_SIZE ?= 5

# Reviewed author merge/split verdicts, applied by author-disambiguate.
AUTHOR_DECISIONS ?= configurations/sri_lanka/author_decisions.csv
AUTHOR_REVIEW_LIMIT ?= 20

# Default OpenAlex output folder.
# JSONL is raw API data. CSV/Parquet and DOI conflicts are cleaned outputs.
OPENALEX_DIR ?= data/raw/openalex
OPENALEX_JSONL ?= $(OPENALEX_DIR)/openalex_sri_lanka_works.jsonl
OPENALEX_CSV ?= $(OPENALEX_DIR)/openalex_sri_lanka_works.csv
OPENALEX_PARQUET ?= $(OPENALEX_DIR)/openalex_sri_lanka_works.parquet
OPENALEX_DOI_CONFLICTS ?= $(OPENALEX_DIR)/openalex_sri_lanka_doi_conflicts.csv
OPENALEX_PROGRESS ?= $(OPENALEX_JSONL).progress.json
OPENALEX_PAGINATION ?= $(OPENALEX_DIR)/openalex_sri_lanka_pagination_audit.json
OPENALEX_LOG ?= $(OPENALEX_DIR)/openalex_collection.log

# OpenAlex collection settings.
# Use OPENALEX_EXTRA_ARGS for optional flags such as --strict-lk-only.
OPENALEX_LOG_LEVEL ?= INFO
OPENALEX_FROM_YEAR ?= 2016
OPENALEX_TO_YEAR ?= 2026
OPENALEX_PER_PAGE ?= 200
OPENALEX_SAMPLE_RECORDS ?= 1000
OPENALEX_EMAIL ?=
OPENALEX_EXTRA_ARGS ?=

# Model-ready text extraction settings.
MODEL_TEXT_INPUT ?= data/processed/common/common_publications_final.csv
MODEL_TITLES_OUTPUT ?= data/processed/common/publication_titles_for_model_all_years.csv
MODEL_ABSTRACTS_OUTPUT ?= data/processed/common/publication_abstracts_for_model_all_years.csv
MODEL_KEYWORDS_OUTPUT ?= data/processed/common/publication_keywords_for_model_all_years.csv
MODEL_TFIDF_OUTPUT ?= data/processed/common/publication_tfidf_features_all_years.csv
MODEL_TFIDF_VOCABULARY_OUTPUT ?= data/processed/common/publication_tfidf_vocabulary_all_years.csv
MODEL_TFIDF_SUMMARY_OUTPUT ?= data/processed/common/publication_tfidf_summary_all_years.csv
MODEL_TFIDF_MAX_FEATURES ?= 5000
MODEL_TFIDF_MIN_DF ?= 2
MODEL_TFIDF_MAX_DF ?= 0.95
MODEL_TFIDF_NGRAM_MAX ?= 2
MODEL_TFIDF_TOP_FEATURES_PER_RECORD ?= 50
LOGREG_INPUT ?= $(MODEL_TEXT_INPUT)
LOGREG_LABEL_COLUMN ?= primary_domain
LOGREG_TEXT_COLUMNS ?= title,abstract,keywords
LOGREG_MODEL_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN).joblib
LOGREG_METRICS_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN)_metrics.txt
LOGREG_LABEL_COUNTS_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN)_labels.csv
LOGREG_PREDICTIONS_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN)_predictions.csv
LOGREG_MANIFEST_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN)_manifest.json
LOGREG_INFERENCE_INPUT ?= $(MODEL_TEXT_INPUT)
LOGREG_INFERENCE_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN)_inference_predictions.csv
LOGREG_INFERENCE_MANIFEST_OUTPUT ?= data/models/logistic_regression_$(LOGREG_LABEL_COLUMN)_inference_manifest.json
LOGREG_INFERENCE_METADATA_COLUMNS ?= record_number,publication_year,title,doi,openalex_id,source_dataset,source_institution_id,source_record_id
LOGREG_INFERENCE_EXTRA_ARGS ?=
EMBED_INPUT ?= $(MODEL_TEXT_INPUT)
EMBED_OUTPUT ?= data/models/publication_text_embeddings.parquet
EMBED_MODEL_OUTPUT ?= data/models/publication_text_embedding_model.joblib
EMBED_MANIFEST_OUTPUT ?= data/models/publication_text_embeddings_manifest.json
EMBED_SUMMARY_OUTPUT ?= data/models/publication_text_embeddings_summary.txt
EMBED_TEXT_COLUMNS ?= title,abstract,keywords
EMBED_METADATA_COLUMNS ?= record_number,publication_year,title,doi,openalex_id,source_dataset,source_institution_id,source_record_id
EMBED_DIM ?= 384
EMBED_MAX_FEATURES ?= 50000
EMBED_MIN_DF ?= 2
EMBED_MAX_DF ?= 0.95
EMBED_NGRAM_MAX ?= 2
EMBED_EXTRA_ARGS ?=
MODEL_SPLIT_INPUT ?= data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
MODEL_SPLIT_OUTPUT_DIR ?= data/processed/modeling/publication_classifier
MODEL_SPLIT_LABEL_COLUMN ?= primary_domain
MODEL_SPLIT_TEXT_COLUMNS ?= title,abstract,keywords
MODEL_SPLIT_TRAIN_RATIO ?= 0.70
MODEL_SPLIT_VALIDATION_RATIO ?= 0.15
MODEL_SPLIT_TEST_RATIO ?= 0.15
MODEL_SPLIT_RANDOM_STATE ?= 42
MODEL_SPLIT_MIN_CLASS_COUNT ?= 20
MODEL_SPLIT_EXTRA_ARGS ?=
API_HOST ?= 127.0.0.1
API_PORT ?= 8080
API_EXTRA_ARGS ?=
MODEL_API_HOST ?= 127.0.0.1
MODEL_API_PORT ?= 8081
MODEL_API_EXTRA_ARGS ?=
DB_LOAD_INPUT ?= data/processed/common/common_publications_final_2016_2026.csv
DB_LOAD_BATCH_SIZE ?= 1000
DB_LOAD_YEAR_MIN ?= 2016
DB_LOAD_YEAR_MAX ?= 2026
LOGREG_MAX_FEATURES ?= 50000
LOGREG_MIN_DF ?= 2
LOGREG_MAX_DF ?= 0.95
LOGREG_NGRAM_MAX ?= 2
LOGREG_MIN_CLASS_COUNT ?= 20
LOGREG_TEST_SIZE ?= 0.2
LOGREG_MAX_ITER ?= 1000
LOGREG_EXTRA_ARGS ?=

# Build optional/email args only when values are provided.
OPENALEX_EMAIL_ARG = $(if $(OPENALEX_EMAIL),--email $(OPENALEX_EMAIL),)

# File output arguments shared by collect, sample, and resume targets.
OPENALEX_OUTPUT_ARGS = \
	--jsonl-output $(OPENALEX_JSONL) \
	--csv-output $(OPENALEX_CSV) \
	--parquet-output $(OPENALEX_PARQUET) \
	--doi-conflicts-output $(OPENALEX_DOI_CONFLICTS) \
	--pagination-output $(OPENALEX_PAGINATION) \
	--progress-output $(OPENALEX_PROGRESS)

# Runtime arguments shared by collect, sample, and resume targets.
OPENALEX_RUN_ARGS = \
	$(OPENALEX_OUTPUT_ARGS) \
	--from-year $(OPENALEX_FROM_YEAR) \
	--to-year $(OPENALEX_TO_YEAR) \
	--per-page $(OPENALEX_PER_PAGE) \
	--log-level $(OPENALEX_LOG_LEVEL) \
	--log-file $(OPENALEX_LOG) \
	$(OPENALEX_EMAIL_ARG) \
	$(OPENALEX_EXTRA_ARGS)

.PHONY: help install test publication-counts api load-db-2016-now reset-db-2016-now load-full-db-2016-now reset-full-db-2016-now openalex openalex-sample openalex-resume openalex-rebuild openalex-doi-conflicts openalex-report institution-registry institution-normalize type-journal-normalize author-disambiguate author-review author-decisions model-text model-titles model-abstracts model-keywords model-tfidf model-embeddings model-splits train-logreg predict-logreg model-api

# Show available targets and common overrides.
help:
	@echo "ResearchLanka national research analytics targets"
	@echo ""
	@echo "  make install                 Install Python dependencies into .venv"
	@echo "  make test                    Run the test suite"
	@echo "  make api                     Serve the read-only ResearchLanka API"
	@echo "  make load-db-2016-now        Load only 2016-2026 records into final_publications"
	@echo "  make reset-db-2016-now       Clear final_publications, then load 2016-2026 records"
	@echo "  make load-full-db-2016-now   Load only 2016-2026 records into all database tables"
	@echo "  make reset-full-db-2016-now  Clear database tables, then load 2016-2026 records"
	@echo "  make publication-counts      Compare publication counts across source datasets"
	@echo "  make openalex                Collect OpenAlex data and write JSONL, CSV, Parquet, DOI conflicts, pagination audit, log"
	@echo "  make openalex-sample         Collect a small OpenAlex sample, default OPENALEX_SAMPLE_RECORDS=1000"
	@echo "  make openalex-resume         Resume an interrupted OpenAlex collection"
	@echo "  make openalex-rebuild        Rebuild CSV, Parquet, DOI conflicts, and summary from existing JSONL"
	@echo "  make openalex-doi-conflicts  Rebuild only the DOI conflict CSV from existing JSONL"
	@echo "  make openalex-report         Print the quality report from existing JSONL"
	@echo "  make author-disambiguate     Resolve author mentions onto stable author identities"
	@echo "  make author-review           Show the ambiguous-author review queue"
	@echo "  make author-decisions        Promote reviewed verdicts into the decisions file"
	@echo "  make model-text              Export text and TF-IDF CSVs for model pipelines"
	@echo "  make model-titles            Export publication titles for model pipelines"
	@echo "  make model-abstracts         Export publication abstracts for model pipelines"
	@echo "  make model-keywords          Export publication keywords for model pipelines"
	@echo "  make model-tfidf             Export compact TF-IDF feature rows and vocabulary"
	@echo "  make model-embeddings        Generate dense publication-text embeddings"
	@echo "  make model-splits            Create train/validation/test CSVs for publication classifier datasets"
	@echo "  make train-logreg            Train TF-IDF + Logistic Regression classifier"
	@echo "  make predict-logreg          Run saved classifier inference on publication text"
	@echo "  make model-api               Serve FastAPI model endpoints"
	@echo ""
	@echo "Useful variables:"
	@echo "  OPENALEX_LOG_LEVEL=DEBUG"
	@echo "  OPENALEX_EMAIL=you@example.com"
	@echo "  OPENALEX_EXTRA_ARGS='--strict-lk-only'"
	@echo "  OPENALEX_DIR=data/processed/openalex"
	@echo "  NATIONAL_CONFIG=configurations/sri_lanka/config.json"
	@echo "  MODEL_TEXT_INPUT=data/processed/common/common_publications_final.csv"

# Install project dependencies into the configured virtual environment.
install:
	$(PIP) install -r requirements.txt

# Run all automated tests.
test:
	$(PYTHON) -m pytest

# Compare raw and estimated unique publication counts for each source file.
publication-counts:
	$(PYTHON) scripts/quality/compare_publication_counts.py

# Serve the read-only dashboard/search/profile API.
api:
	$(PYTHON) scripts/api/serve_api.py --host $(API_HOST) --port $(API_PORT) $(API_EXTRA_ARGS)

load-db-2016-now:
	$(PYTHON) scripts/database/load_records.py $(DB_LOAD_INPUT) --batch-size $(DB_LOAD_BATCH_SIZE) --year-min $(DB_LOAD_YEAR_MIN) --year-max $(DB_LOAD_YEAR_MAX)

reset-db-2016-now:
	$(PYTHON) scripts/database/load_records.py $(DB_LOAD_INPUT) --batch-size $(DB_LOAD_BATCH_SIZE) --year-min $(DB_LOAD_YEAR_MIN) --year-max $(DB_LOAD_YEAR_MAX) --reset

load-full-db-2016-now:
	$(PYTHON) -m research_analytics.cli load_database --config $(NATIONAL_CONFIG) --dataset $(DB_LOAD_INPUT) --batch-size $(DB_LOAD_BATCH_SIZE) --full-database --year-min $(DB_LOAD_YEAR_MIN) --year-max $(DB_LOAD_YEAR_MAX)

reset-full-db-2016-now:
	$(PYTHON) -m research_analytics.cli load_database --config $(NATIONAL_CONFIG) --dataset $(DB_LOAD_INPUT) --batch-size $(DB_LOAD_BATCH_SIZE) --full-database --year-min $(DB_LOAD_YEAR_MIN) --year-max $(DB_LOAD_YEAR_MAX) --reset

# Export model-ready text and TF-IDF features from the final dataset.
model-text: model-titles model-abstracts model-keywords model-tfidf

model-titles:
	$(PYTHON) scripts/extraction/extract_publication_titles_for_model.py --input $(MODEL_TEXT_INPUT) --output $(MODEL_TITLES_OUTPUT)

model-abstracts:
	$(PYTHON) scripts/extraction/extract_publication_abstracts_for_model.py --input $(MODEL_TEXT_INPUT) --output $(MODEL_ABSTRACTS_OUTPUT)

model-keywords:
	$(PYTHON) scripts/extraction/extract_publication_keywords_for_model.py --input $(MODEL_TEXT_INPUT) --output $(MODEL_KEYWORDS_OUTPUT)

model-tfidf:
	$(PYTHON) scripts/extraction/build_publication_tfidf_features.py --input $(MODEL_TEXT_INPUT) --output $(MODEL_TFIDF_OUTPUT) --vocabulary-output $(MODEL_TFIDF_VOCABULARY_OUTPUT) --summary-output $(MODEL_TFIDF_SUMMARY_OUTPUT) --max-features $(MODEL_TFIDF_MAX_FEATURES) --min-df $(MODEL_TFIDF_MIN_DF) --max-df $(MODEL_TFIDF_MAX_DF) --ngram-max $(MODEL_TFIDF_NGRAM_MAX) --top-features-per-record $(MODEL_TFIDF_TOP_FEATURES_PER_RECORD)

model-embeddings:
	$(PYTHON) scripts/modeling/generate_publication_text_embeddings.py --input $(EMBED_INPUT) --output $(EMBED_OUTPUT) --model-output $(EMBED_MODEL_OUTPUT) --manifest-output $(EMBED_MANIFEST_OUTPUT) --summary-output $(EMBED_SUMMARY_OUTPUT) --text-columns $(EMBED_TEXT_COLUMNS) --metadata-columns $(EMBED_METADATA_COLUMNS) --embedding-dim $(EMBED_DIM) --max-features $(EMBED_MAX_FEATURES) --min-df $(EMBED_MIN_DF) --max-df $(EMBED_MAX_DF) --ngram-max $(EMBED_NGRAM_MAX) $(EMBED_EXTRA_ARGS)

model-splits:
	$(PYTHON) scripts/modeling/create_dataset_splits.py --input $(MODEL_SPLIT_INPUT) --output-dir $(MODEL_SPLIT_OUTPUT_DIR) --label-column $(MODEL_SPLIT_LABEL_COLUMN) --text-columns $(MODEL_SPLIT_TEXT_COLUMNS) --train-ratio $(MODEL_SPLIT_TRAIN_RATIO) --validation-ratio $(MODEL_SPLIT_VALIDATION_RATIO) --test-ratio $(MODEL_SPLIT_TEST_RATIO) --random-state $(MODEL_SPLIT_RANDOM_STATE) --min-class-count $(MODEL_SPLIT_MIN_CLASS_COUNT) $(MODEL_SPLIT_EXTRA_ARGS)

train-logreg:
	$(PYTHON) scripts/modeling/train_logistic_regression_classifier.py --input $(LOGREG_INPUT) --label-column $(LOGREG_LABEL_COLUMN) --text-columns $(LOGREG_TEXT_COLUMNS) --model-output $(LOGREG_MODEL_OUTPUT) --metrics-output $(LOGREG_METRICS_OUTPUT) --label-counts-output $(LOGREG_LABEL_COUNTS_OUTPUT) --predictions-output $(LOGREG_PREDICTIONS_OUTPUT) --manifest-output $(LOGREG_MANIFEST_OUTPUT) --max-features $(LOGREG_MAX_FEATURES) --min-df $(LOGREG_MIN_DF) --max-df $(LOGREG_MAX_DF) --ngram-max $(LOGREG_NGRAM_MAX) --min-class-count $(LOGREG_MIN_CLASS_COUNT) --test-size $(LOGREG_TEST_SIZE) --max-iter $(LOGREG_MAX_ITER) $(LOGREG_EXTRA_ARGS)

predict-logreg:
	$(PYTHON) scripts/modeling/predict_publication_classifier.py --input $(LOGREG_INFERENCE_INPUT) --model $(LOGREG_MODEL_OUTPUT) --model-manifest $(LOGREG_MANIFEST_OUTPUT) --output $(LOGREG_INFERENCE_OUTPUT) --inference-manifest $(LOGREG_INFERENCE_MANIFEST_OUTPUT) --text-columns $(LOGREG_TEXT_COLUMNS) --metadata-columns $(LOGREG_INFERENCE_METADATA_COLUMNS) $(LOGREG_INFERENCE_EXTRA_ARGS)

model-api:
	$(PYTHON) -m src.api.fastapi_app --host $(MODEL_API_HOST) --port $(MODEL_API_PORT) $(MODEL_API_EXTRA_ARGS)

# Run the full OpenAlex API collection pipeline.
# Legacy path: this writes raw JSONL, cleaned CSV, cleaned Parquet, DOI conflicts,
# pagination audit, progress, and logs. Prefer make framework for national analytics.
openalex:
	$(PYTHON) scripts/collection/kaggle_collect_openalex_sri_lanka.py $(OPENALEX_RUN_ARGS)

# Run a smaller API collection for validation before a full collection.
openalex-sample:
	$(PYTHON) scripts/collection/kaggle_collect_openalex_sri_lanka.py $(OPENALEX_RUN_ARGS) --max-records $(OPENALEX_SAMPLE_RECORDS)

# Continue an interrupted collection using the progress JSON file.
openalex-resume:
	$(PYTHON) scripts/collection/kaggle_collect_openalex_sri_lanka.py $(OPENALEX_RUN_ARGS) --resume

# Rebuild cleaned outputs from an existing raw JSONL file.
# This does not call the OpenAlex API.
openalex-rebuild:
	$(PYTHON) -c "from pathlib import Path; from scripts.collection.kaggle_collect_openalex_sri_lanka import rebuild_csv_from_jsonl, write_doi_conflict_report, write_parquet_from_jsonl, collect_quality_report, print_collection_report; jsonl=Path('$(OPENALEX_JSONL)'); rebuild_csv_from_jsonl(jsonl, Path('$(OPENALEX_CSV)')); write_parquet_from_jsonl(jsonl, Path('$(OPENALEX_PARQUET)')); write_doi_conflict_report(jsonl, Path('$(OPENALEX_DOI_CONFLICTS)')); print_collection_report(collect_quality_report(jsonl, records_skipped=0))"

# Rebuild only the DOI conflict CSV from existing raw JSONL.
openalex-doi-conflicts:
	$(PYTHON) -c "from pathlib import Path; from scripts.collection.kaggle_collect_openalex_sri_lanka import write_doi_conflict_report; count=write_doi_conflict_report(Path('$(OPENALEX_JSONL)'), Path('$(OPENALEX_DOI_CONFLICTS)')); print(f'DOI conflicts: {count:,}')"

# Regenerate the national institution registry from the merged dataset.
# Writes configurations/sri_lanka/institutions.csv for review -- read the diff
# and correct any mis-typed or duplicated entries before committing.
institution-registry:
	$(PYTHON) -m src.pipeline.build_institution_registry

# Standardize institutions, affiliations and countries, and derive the
# collaboration fields. Depends on the registry above being current.
institution-normalize:
	$(PYTHON) -m src.pipeline.build_institution_normalized_dataset

# Standardize publication types and venue names. Reads the institution-normalized
# dataset, so run institution-normalize first.
type-journal-normalize:
	$(PYTHON) -m src.pipeline.build_type_journal_normalized_dataset

# Resolve author mentions onto stable author identities using ORCID, affiliation
# and coauthor evidence. Reads the institution-normalized dataset, so run
# institution-normalize first. Writes the dataset, an author registry, a summary
# and a review queue of the pairs the rules could not settle.
author-disambiguate:
	$(PYTHON) -m src.pipeline.build_author_disambiguated_dataset \
	--decisions-csv $(AUTHOR_DECISIONS)

# Show what is waiting in the ambiguous-author review queue.
author-review:
	$(PYTHON) -m src.quality.review_ambiguous_authors --limit $(AUTHOR_REVIEW_LIMIT)

# Promote decisions filled into the review queue, then validate the result.
# Re-run author-disambiguate afterwards to apply them.
author-decisions:
	$(PYTHON) -m src.quality.review_ambiguous_authors --extract-decisions \
	--decisions-csv $(AUTHOR_DECISIONS)
	$(PYTHON) -m src.quality.review_ambiguous_authors --validate \
	--decisions-csv $(AUTHOR_DECISIONS)

# Print a quality summary from existing raw JSONL.
openalex-report:
	$(PYTHON) -c "from pathlib import Path; from scripts.collection.kaggle_collect_openalex_sri_lanka import collect_quality_report, print_collection_report; print_collection_report(collect_quality_report(Path('$(OPENALEX_JSONL)'), records_skipped=0))"
