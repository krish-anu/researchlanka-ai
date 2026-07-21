# Copilot instructions for researchlanka-ai

- This repository is a Python data pipeline for collecting, normalizing, and comparing publication metadata from Crossref and OpenAlex for Sri Lankan research analytics.
- Keep CLI entry points in `scripts/` and reusable logic in `src/`. New behavior should usually be implemented in `src/` and exposed from a thin script wrapper.
- The main data flow is: `scripts/collect_crossref.py` / `scripts/collect_openalex.py` -> collector classes in `src/collectors/` -> normalization/preprocessing in `src/preprocessing/` -> JSONL/CSV data under `data/`.
- Crossref handling is centered on `src/collectors/crossref_collector.py` and `src/preprocessing/crossref_normalizer.py`. `CrossrefCollector.iter_works()` handles cursor pagination and filters out unsupported record types via `KEEP_TYPES`; `reduce_work()` produces a stable flattened dict that downstream scripts expect.
- OpenAlex handling is centered on `src/collectors/openalex_collector.py`. Prefer passing filter fragments as lists (for example `institutions.country_code:LK`) rather than hard-coding new API logic in scripts.
- Output conventions are simple and file-based: JSONL is the intermediate format for collection scripts, while `scripts/jsonl_to_csv.py` and `scripts/doi_com.py` convert or compare datasets.
- Preserve existing paths and names where possible: Crossref outputs are written to `data/processed/crossref/`, OpenAlex raw data to `data/raw/openalex/`, and DOI comparison outputs to `data/processed/doi_comparison/`.
- Use `src/utils/normalize.py` for DOI normalization and keep DOI handling consistent across collectors and comparison scripts.
- Tests are lightweight and do not depend on live APIs; `tests/test_crossref_collector.py` uses `monkeypatch` to simulate collection responses. When changing pagination or filtering, add or update tests in that style.
- Common workflows:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
  - `pytest`
  - `python scripts/collect_crossref.py inspect --query lanka --limit 3`
  - `python scripts/collect_openalex.py collect-lk --max-records 1000`
  - `python scripts/jsonl_to_csv.py`
- Follow the repository’s git conventions from `CONTRIBUTING.md`: work from a feature branch, use `type/short-description` branch names, and write commit messages like `feat(collector): ...`.
- Do not commit secrets, `.env` files, API keys, or large raw datasets; the repo already includes `.env.example` and data directories for generated outputs.
