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

.PHONY: help install test framework framework-validate framework-preview framework-sri-lanka framework-example openalex openalex-sample openalex-resume openalex-rebuild openalex-doi-conflicts openalex-report

# Show available targets and common overrides.
help:
	@echo "ResearchLanka national research analytics targets"
	@echo ""
	@echo "  make install                 Install Python dependencies into .venv"
	@echo "  make test                    Run the test suite"
	@echo "  make framework               Run the reusable national framework pipeline, default NATIONAL_CONFIG=$(NATIONAL_CONFIG)"
	@echo "  make framework-validate      Validate/preview source mapping before full framework import"
	@echo "  make framework-preview       Show transformed sample records from the framework pipeline"
	@echo "  make framework-sri-lanka     Run Sri Lanka as the first national framework implementation"
	@echo "  make framework-example       Run the second-country reusability demonstration"
	@echo "  make openalex                Legacy Sri Lanka-specific OpenAlex collection script"
	@echo "  make openalex-sample         Collect a small OpenAlex sample, default OPENALEX_SAMPLE_RECORDS=1000"
	@echo "  make openalex-resume         Resume an interrupted OpenAlex collection"
	@echo "  make openalex-rebuild        Rebuild CSV, Parquet, DOI conflicts, and summary from existing JSONL"
	@echo "  make openalex-doi-conflicts  Rebuild only the DOI conflict CSV from existing JSONL"
	@echo "  make openalex-report         Print the quality report from existing JSONL"
	@echo ""
	@echo "Useful variables:"
	@echo "  OPENALEX_LOG_LEVEL=DEBUG"
	@echo "  OPENALEX_EMAIL=you@example.com"
	@echo "  OPENALEX_EXTRA_ARGS='--strict-lk-only'"
	@echo "  OPENALEX_DIR=data/processed/openalex"
	@echo "  NATIONAL_CONFIG=configurations/example_country/config.json"

# Install project dependencies into the configured virtual environment.
install:
	$(PIP) install -r requirements.txt

# Run all automated tests.
test:
	$(PYTHON) -m pytest

# Run the reusable national research analytics framework.
framework:
	$(PYTHON) -m research_analytics.cli run-all --config $(NATIONAL_CONFIG)

# Validate the selected national source before full import.
framework-validate:
	$(PYTHON) -m research_analytics.cli source-validate --config $(NATIONAL_CONFIG) --sample-size $(NATIONAL_SAMPLE_SIZE)

# Preview transformed records from the selected national framework config.
framework-preview:
	$(PYTHON) -m research_analytics.cli preview --config $(NATIONAL_CONFIG) --sample-size $(NATIONAL_SAMPLE_SIZE)

# Run Sri Lanka through the reusable framework pipeline.
framework-sri-lanka:
	$(PYTHON) -m research_analytics.cli run-all --config configurations/sri_lanka/config.json

# Run the second-country proof with the same framework code.
framework-example:
	$(PYTHON) -m research_analytics.cli run-all --config configurations/example_country/config.json

# Run the full OpenAlex API collection pipeline.
# Legacy path: this writes raw JSONL, cleaned CSV, cleaned Parquet, DOI conflicts,
# pagination audit, progress, and logs. Prefer make framework for national analytics.
openalex:
	$(PYTHON) scripts/kaggle_collect_openalex_sri_lanka.py $(OPENALEX_RUN_ARGS)

# Run a smaller API collection for validation before a full collection.
openalex-sample:
	$(PYTHON) scripts/kaggle_collect_openalex_sri_lanka.py $(OPENALEX_RUN_ARGS) --max-records $(OPENALEX_SAMPLE_RECORDS)

# Continue an interrupted collection using the progress JSON file.
openalex-resume:
	$(PYTHON) scripts/kaggle_collect_openalex_sri_lanka.py $(OPENALEX_RUN_ARGS) --resume

# Rebuild cleaned outputs from an existing raw JSONL file.
# This does not call the OpenAlex API.
openalex-rebuild:
	$(PYTHON) -c "from pathlib import Path; from scripts.kaggle_collect_openalex_sri_lanka import rebuild_csv_from_jsonl, write_doi_conflict_report, write_parquet_from_jsonl, collect_quality_report, print_collection_report; jsonl=Path('$(OPENALEX_JSONL)'); rebuild_csv_from_jsonl(jsonl, Path('$(OPENALEX_CSV)')); write_parquet_from_jsonl(jsonl, Path('$(OPENALEX_PARQUET)')); write_doi_conflict_report(jsonl, Path('$(OPENALEX_DOI_CONFLICTS)')); print_collection_report(collect_quality_report(jsonl, records_skipped=0))"

# Rebuild only the DOI conflict CSV from existing raw JSONL.
openalex-doi-conflicts:
	$(PYTHON) -c "from pathlib import Path; from scripts.kaggle_collect_openalex_sri_lanka import write_doi_conflict_report; count=write_doi_conflict_report(Path('$(OPENALEX_JSONL)'), Path('$(OPENALEX_DOI_CONFLICTS)')); print(f'DOI conflicts: {count:,}')"

# Print a quality summary from existing raw JSONL.
openalex-report:
	$(PYTHON) -c "from pathlib import Path; from scripts.kaggle_collect_openalex_sri_lanka import collect_quality_report, print_collection_report; print_collection_report(collect_quality_report(Path('$(OPENALEX_JSONL)'), records_skipped=0))"
