.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND_DIR ?= backend
FRONTEND_DIR ?= frontend
SYSTEM_PYTHON ?= python3
BACKEND_PYTHON ?= .venv/bin/python
BACKEND_PIP ?= .venv/bin/pip
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8080
BACKEND_API_EXTRA_ARGS ?=
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 3000
API_BASE_URL ?= http://$(BACKEND_HOST):$(BACKEND_PORT)/api/v1
NPM ?= npm
NEXT_TELEMETRY_DISABLED ?= 1
FRONTEND_NODE_MAX_OLD_SPACE_MB ?= 1536
DEV_SEMANTIC_EMBEDDINGS ?= data/models/publication_text_embeddings_cli_sample.parquet
DEV_SEMANTIC_MODEL ?= data/models/publication_text_embedding_model_cli_sample.joblib

.PHONY: help install install-backend install-frontend backend api frontend dev test check check-backend check-frontend

help:
	@echo "ResearchLanka development shortcuts"
	@echo ""
	@echo "  make install            Install backend and frontend dependencies"
	@echo "  make dev                Run backend API and frontend together"
	@echo "  make backend            Run the backend API on http://$(BACKEND_HOST):$(BACKEND_PORT)/api/v1"
	@echo "  make frontend           Run the frontend on http://$(FRONTEND_HOST):$(FRONTEND_PORT)"
	@echo "  make test               Run backend tests and frontend checks"
	@echo "  make check              Same as make test"
	@echo ""
	@echo "Common overrides:"
	@echo "  BACKEND_PORT=8082 FRONTEND_PORT=3001 make dev"
	@echo "  API_BASE_URL=http://127.0.0.1:8080/api/v1 make frontend"
	@echo "  FRONTEND_NODE_MAX_OLD_SPACE_MB=2048 make dev"
	@echo "  DEV_SEMANTIC_EMBEDDINGS=data/models/publication_text_embeddings_2016_2026.parquet DEV_SEMANTIC_MODEL=data/models/publication_text_embedding_model_2016_2026.joblib make dev"

$(BACKEND_DIR)/.venv/bin/python:
	cd $(BACKEND_DIR) && $(SYSTEM_PYTHON) -m venv .venv

install: install-backend install-frontend

install-backend: $(BACKEND_DIR)/.venv/bin/python
	$(MAKE) -C $(BACKEND_DIR) install PYTHON=$(BACKEND_PYTHON) PIP=$(BACKEND_PIP)

install-frontend:
	$(NPM) --prefix $(FRONTEND_DIR) install

backend: $(BACKEND_DIR)/.venv/bin/python
	cd $(BACKEND_DIR) && RESEARCHLANKA_SEMANTIC_EMBEDDINGS_PATH=$(DEV_SEMANTIC_EMBEDDINGS) RESEARCHLANKA_SEMANTIC_MODEL_PATH=$(DEV_SEMANTIC_MODEL) $(BACKEND_PYTHON) scripts/api/serve_api.py --host $(BACKEND_HOST) --port $(BACKEND_PORT) $(BACKEND_API_EXTRA_ARGS)

api: backend

frontend:
	NEXT_TELEMETRY_DISABLED=$(NEXT_TELEMETRY_DISABLED) NODE_OPTIONS=--max-old-space-size=$(FRONTEND_NODE_MAX_OLD_SPACE_MB) API_BASE_URL=$(API_BASE_URL) $(NPM) --prefix $(FRONTEND_DIR) run dev -- --hostname $(FRONTEND_HOST) --port $(FRONTEND_PORT)

dev: $(BACKEND_DIR)/.venv/bin/python
	@set -e; \
	( cd $(BACKEND_DIR) && RESEARCHLANKA_SEMANTIC_EMBEDDINGS_PATH=$(DEV_SEMANTIC_EMBEDDINGS) RESEARCHLANKA_SEMANTIC_MODEL_PATH=$(DEV_SEMANTIC_MODEL) $(BACKEND_PYTHON) scripts/api/serve_api.py --host $(BACKEND_HOST) --port $(BACKEND_PORT) $(BACKEND_API_EXTRA_ARGS) ) & backend_pid=$$!; \
	NEXT_TELEMETRY_DISABLED=$(NEXT_TELEMETRY_DISABLED) NODE_OPTIONS=--max-old-space-size=$(FRONTEND_NODE_MAX_OLD_SPACE_MB) API_BASE_URL=$(API_BASE_URL) $(NPM) --prefix $(FRONTEND_DIR) run dev -- --hostname $(FRONTEND_HOST) --port $(FRONTEND_PORT) & frontend_pid=$$!; \
	trap 'kill $$backend_pid $$frontend_pid 2>/dev/null' INT TERM EXIT; \
	wait -n $$backend_pid $$frontend_pid; \
	status=$$?; \
	kill $$backend_pid $$frontend_pid 2>/dev/null; \
	wait $$backend_pid $$frontend_pid 2>/dev/null || true; \
	exit $$status

test: check

check: check-backend check-frontend

check-backend: $(BACKEND_DIR)/.venv/bin/python
	$(MAKE) -C $(BACKEND_DIR) test PYTHON=$(BACKEND_PYTHON)

check-frontend:
	$(NPM) --prefix $(FRONTEND_DIR) run typecheck
	$(NPM) --prefix $(FRONTEND_DIR) run check:palette
