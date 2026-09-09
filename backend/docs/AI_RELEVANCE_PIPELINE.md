# AI Relevance Pipeline

This pipeline identifies AI-related publications before topic modelling. It preserves the original publication datasets and writes separate AI relevance artifacts under `backend/data/processed/ai/`.

## Definition

A publication is AI-related when AI is a substantial part of the research objective, methodology, application, evaluation, analysis, or main subject of discussion.

Labels:

- `AI`: enough metadata evidence shows AI is central or substantial.
- `NON_AI`: enough metadata evidence shows AI is not central or substantial.
- `REVIEW`: metadata is genuinely insufficient or ambiguous.

Generic words such as prediction, classification, optimisation, automation, algorithm, modelling, data, digital, intelligent, smart, forecasting, statistical analysis, or decision support are not enough by themselves.

## Input Dataset

Canonical local input:

`backend/data/processed/common/common_publications_final.csv`

Relevant columns currently available include `record_number`, `openalex_id`, `doi`, `title`, `abstract`, `keywords`, `concepts`, `topics`, `primary_topic`, `primary_field`, `primary_subfield`, `primary_domain`, `publication_year`, `source_dataset`, `source_institution_id`, and `source_record_id`.

The classifier prompt uses only supplied publication metadata. It does not use authors, institutions, countries, citations, journal reputation, year, or external web knowledge to decide AI relevance.

## Environment

Required for a direct Google Gemini run:

```bash
export GEMINI_API_KEY="..."
export GEMINI_MODEL="gemini-3.8-flash"
export AI_PROMPT_VERSION="v1"
```

For OpenRouter instead:

```bash
export AI_LLM_PROVIDER="openrouter"
export OPENROUTER_API_KEY="..."
export GEMINI_MODEL="google/gemini-2.5-flash"
export AI_PROMPT_VERSION="v1"
```

Use an OpenRouter model slug that supports structured outputs. The OpenRouter client sends requests to `https://openrouter.ai/api/v1/chat/completions` with `response_format.type=json_schema` and `provider.require_parameters=true`.

For local Ollama instead:

```bash
export AI_LLM_PROVIDER="ollama"
export AI_LLM_MODEL="llama3.1:8b"
export OLLAMA_BASE_URL="http://localhost:11434/api/chat"
export AI_PROMPT_VERSION="v1"
export GEMINI_MAX_RETRIES="3"
export GEMINI_TIMEOUT_SECONDS="180"
```

Use the exact model name shown by `ollama list`. The Ollama client uses local `/api/chat` with JSON-schema formatting. Token counts are read from Ollama's `prompt_eval_count` and `eval_count` fields when available, and estimated cost remains `$0` unless you set price environment variables.

Optional controls:

```bash
export GEMINI_MAX_RETRIES="3"
export GEMINI_TIMEOUT_SECONDS="60"
export GEMINI_MAX_CONCURRENCY="1"
export GEMINI_INPUT_PRICE_PER_MILLION="0"
export GEMINI_OUTPUT_PRICE_PER_MILLION="0"
```

Pricing defaults to `0` so stale prices are not baked into the code. Set the two price variables before a run if you want the displayed `ESTIMATED COST` to reflect the provider pricing you have verified. Environment files such as `.env` and `.env.*` are already ignored by Git.

## Candidate Sampling

Build the reproducible candidate sample:

```bash
cd backend
python scripts/ai_relevance/build_ai_candidate_sample.py \
  --input data/processed/common/common_publications_final.csv \
  --output data/processed/ai/ai_llm_5000_candidates.csv \
  --target-size 5000 \
  --random-seed 42
```

Output:

`backend/data/processed/ai/ai_llm_5000_candidates.csv`

Sampling is informative rather than purely random. Buckets target AI-looking OpenAlex topics/concepts, strong AI text candidates, cross-domain AI candidates, Computer Science hard negatives, borderline ambiguous records, and field-stratified random records. Keyword matching is used only to construct candidates; it is not a permanent AI label. Every selected publication has one `sampling_bucket`, and duplicates are removed by `publication_id`.

## First Gemini Test

Do not run this until you are ready to make the paid Gemini API call.

The first test command is:

```bash
cd backend
python scripts/ai_relevance/run_gemini_ai_relevance.py \
  --input data/processed/ai/ai_llm_5000_candidates.csv \
  --limit 10 \
  --first-test \
  --output data/processed/ai/ai_llm_test_10_predictions.csv \
  --selected-ids-output data/processed/ai/ai_llm_test_10_ids.csv \
  --random-seed 42
```

The `--first-test` guard rejects any limit other than exactly `10`.

Outputs:

- `backend/data/processed/ai/ai_llm_test_10_predictions.csv`
- `backend/data/processed/ai/ai_llm_test_10_ids.csv`

Prediction columns include `publication_id`, `ai_llm_label`, `ai_llm_confidence`, `ai_llm_category`, `ai_llm_reason`, `ai_llm_evidence`, `ai_llm_model`, `ai_prompt_version`, `ai_llm_status`, `ai_llm_error`, `ai_llm_processed_at`, `ai_llm_input_tokens`, `ai_llm_output_tokens`, `ai_llm_total_tokens`, and `sampling_bucket`.

After the 10 selected records are processed, the runner prints:

`FIRST 10-RECORD TEST COMPLETED.`

`No further Gemini calls were made.`

`10-record Gemini test completed. No further publication classification was started.`

## Resume

If a run stops, rerun the same command with `--resume`. Existing successful `publication_id` rows are skipped so the API is not called again for them.

```bash
cd backend
python scripts/ai_relevance/run_gemini_ai_relevance.py \
  --input data/processed/ai/ai_llm_5000_candidates.csv \
  --limit 10 \
  --first-test \
  --resume \
  --output data/processed/ai/ai_llm_test_10_predictions.csv \
  --selected-ids-output data/processed/ai/ai_llm_test_10_ids.csv \
  --random-seed 42
```

## Prompt Versioning

Prompt v1 lives in `src/ai_relevance/prompt.py`. Each prediction stores `AI_PROMPT_VERSION`. Do not silently overwrite v1 outputs with a later prompt version. Use a new output filename when testing a new prompt, for example `data/processed/ai/ai_llm_test_10_predictions_v2.csv`.

## Human Review

Later, export a review sample from Gemini predictions:

```bash
cd backend
python scripts/ai_relevance/export_human_review_sample.py \
  --input data/processed/ai/ai_llm_5000_predictions.csv \
  --output data/processed/ai/ai_human_review_sample.csv \
  --sample-size 500 \
  --random-seed 42
```

The export includes empty `human_label` and `human_notes` fields. Allowed human labels are `AI`, `NON_AI`, and `REVIEW`.

## Evaluation

After human labels are completed:

```bash
cd backend
python scripts/ai_relevance/evaluate_gemini_human_labels.py \
  --input data/processed/ai/ai_human_review_sample.csv \
  --output-dir data/reports/ai_relevance \
  --run-name gemini_ai_relevance_v1
```

Outputs include metrics JSON, a confusion matrix CSV, false positives, and false negatives. By default, human `REVIEW` rows are excluded from binary AI vs NON_AI metrics. Pass `--include-human-review` to evaluate REVIEW as a third class.

Metrics include accuracy, AI precision, AI recall, AI F1-score, macro F1, and a confusion matrix. Precision matters because the final corpus should contain only AI-related publications.

## Topic Modelling

Topic modelling comes after AI filtering:

all publications -> AI relevance filtering -> verified AI-only corpus -> topic modelling.

Existing topic modelling outputs are not used as the AI/non-AI classifier.
