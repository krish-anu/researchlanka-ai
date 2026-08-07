.DEFAULT_GOAL := help

# Python commands. Override these if you want to use a different environment:
#   make test PYTHON=python
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

# Reusable national framework settings.
NATIONAL_CONFIG ?= configurations/sri_lanka/config.json
NATIONAL_SAMPLE_SIZE ?= 5

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
MODEL_API_HOST ?= 127.0.0.1
MODEL_API_PORT ?= 8081
MODEL_API_EXTRA_ARGS ?=
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

.PHONY: help install test publication-counts openalex openalex-sample openalex-resume openalex-rebuild openalex-doi-conflicts openalex-report institution-registry institution-normalize type-journal-normalize model-text model-titles model-abstracts model-keywords model-tfidf train-logreg predict-logreg model-api

# Show available targets and common overrides.
help:
	@echo "ResearchLanka national research analytics targets"
	@echo ""
	@echo "  make install                 Install Python dependencies into .venv"
	@echo "  make test                    Run the test suite"
	@echo "  make publication-counts      Compare publication counts across source datasets"
	@echo "  make openalex                Collect OpenAlex data and write JSONL, CSV, Parquet, DOI conflicts, pagination audit, log"
	@echo "  make openalex-sample         Collect a small OpenAlex sample, default OPENALEX_SAMPLE_RECORDS=1000"
	@echo "  make openalex-resume         Resume an interrupted OpenAlex collection"
	@echo "  make openalex-rebuild        Rebuild CSV, Parquet, DOI conflicts, and summary from existing JSONL"
	@echo "  make openalex-doi-conflicts  Rebuild only the DOI conflict CSV from existing JSONL"
	@echo "  make openalex-report         Print the quality report from existing JSONL"
	@echo "  make model-text              Export text and TF-IDF CSVs for model pipelines"
	@echo "  make model-titles            Export publication titles for model pipelines"
	@echo "  make model-abstracts         Export publication abstracts for model pipelines"
	@echo "  make model-keywords          Export publication keywords for model pipelines"
	@echo "  make model-tfidf             Export compact TF-IDF feature rows and vocabulary"
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

# Print a quality summary from existing raw JSONL.
openalex-report:
	$(PYTHON) -c "from pathlib import Path; from scripts.collection.kaggle_collect_openalex_sri_lanka import collect_quality_report, print_collection_report; print_collection_report(collect_quality_report(Path('$(OPENALEX_JSONL)'), records_skipped=0))"
