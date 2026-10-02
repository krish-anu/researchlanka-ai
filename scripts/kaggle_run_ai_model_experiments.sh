#!/usr/bin/env bash
set -euo pipefail

# Kaggle runner for ResearchLanka AI relevance model experiments.
#
# Usage from a Kaggle notebook cell:
#   !bash scripts/kaggle_run_ai_model_experiments.sh
#
# Optional:
#   RUN_SCIBERT=1 !bash scripts/kaggle_run_ai_model_experiments.sh
#   INSTALL_OPTIONAL=0 !bash scripts/kaggle_run_ai_model_experiments.sh

INSTALL_OPTIONAL="${INSTALL_OPTIONAL:-1}"
RUN_SCIBERT="${RUN_SCIBERT:-0}"
SCIBERT_EPOCHS="${SCIBERT_EPOCHS:-3}"
SCIBERT_BATCH_SIZE="${SCIBERT_BATCH_SIZE:-8}"
SCIBERT_MAX_LENGTH="${SCIBERT_MAX_LENGTH:-256}"

if [[ -d "backend" ]]; then
  cd backend
elif [[ "$(basename "$PWD")" == "backend" ]]; then
  :
elif [[ -d "/kaggle/working/researchlanka-ai/backend" ]]; then
  cd /kaggle/working/researchlanka-ai/backend
elif [[ -d "/kaggle/working/researchlanka-ai/researchlanka-ai/backend" ]]; then
  cd /kaggle/working/researchlanka-ai/researchlanka-ai/backend
else
  echo "Could not find backend directory. Run this from the repo root or backend folder."
  exit 1
fi

echo "Running from: $PWD"

python - <<'PY'
from pathlib import Path
required = [
    Path("scripts/ai_relevance/run_validated_human_model_selection.py"),
    Path("scripts/ai_relevance/run_sentence_transformer_experiment.py"),
    Path("scripts/ai_relevance/collect_model_comparison_scores.py"),
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit("Missing required scripts:\n" + "\n".join(missing))
PY

if [[ "$INSTALL_OPTIONAL" == "1" ]]; then
  echo "Installing optional experiment packages..."
  python -m pip install -q xgboost lightgbm catboost sentence-transformers
  if [[ "$RUN_SCIBERT" == "1" ]]; then
    python -m pip install -q torch transformers accelerate
  fi
fi

has_module() {
  python - "$1" <<'PY'
import importlib.util
import sys
raise SystemExit(0 if importlib.util.find_spec(sys.argv[1]) else 1)
PY
}

MODEL_FAMILIES="linear_svm,logistic_regression,ridge_classifier,sgd_classifier,multinomial_nb,xgboost"
INCLUDE_FLAGS=(--include-xgboost --fast-xgboost)

if has_module lightgbm; then
  MODEL_FAMILIES="${MODEL_FAMILIES},lightgbm"
  INCLUDE_FLAGS+=(--include-lightgbm)
else
  echo "LightGBM not available; skipping lightgbm."
fi

if has_module catboost; then
  MODEL_FAMILIES="${MODEL_FAMILIES},catboost"
  INCLUDE_FLAGS+=(--include-catboost)
else
  echo "CatBoost not available; skipping catboost."
fi

echo "1/4 Running validation-first TF-IDF/classical/boosting comparison..."
python scripts/ai_relevance/run_validated_human_model_selection.py \
  --output-dir data/models/ai_relevance/kaggle_model_comparison_validated \
  --model-families "$MODEL_FAMILIES" \
  "${INCLUDE_FLAGS[@]}"

ST_CLASSIFIERS="logistic_regression,linear_svm,random_forest,xgboost"
if has_module lightgbm; then
  ST_CLASSIFIERS="${ST_CLASSIFIERS},lightgbm"
fi
if has_module catboost; then
  ST_CLASSIFIERS="${ST_CLASSIFIERS},catboost"
fi

echo "2/4 Running sentence-transformer embedding comparison..."
python scripts/ai_relevance/run_sentence_transformer_experiment.py \
  --selection-dir data/models/ai_relevance/kaggle_model_comparison_validated \
  --output-dir data/models/ai_relevance/kaggle_model_comparison_sentence_transformer \
  --sentence-transformer-model sentence-transformers/all-MiniLM-L6-v2 \
  --classifiers "$ST_CLASSIFIERS"

if [[ "$RUN_SCIBERT" == "1" ]]; then
  echo "3/4 Running SciBERT fine-tuning..."
  python scripts/ai_relevance/run_transformer_finetune_experiment.py \
    --selection-dir data/models/ai_relevance/kaggle_model_comparison_validated \
    --output-dir data/models/ai_relevance/kaggle_model_comparison_scibert \
    --model-name allenai/scibert_scivocab_uncased \
    --epochs "$SCIBERT_EPOCHS" \
    --batch-size "$SCIBERT_BATCH_SIZE" \
    --max-length "$SCIBERT_MAX_LENGTH"
else
  echo "3/4 Skipping SciBERT. Set RUN_SCIBERT=1 to enable it."
fi

echo "4/4 Collecting all score CSVs..."
python scripts/ai_relevance/collect_model_comparison_scores.py \
  --output data/models/ai_relevance/kaggle_all_model_scores.csv

echo
echo "Done."
echo "Main score file:"
echo "  $PWD/data/models/ai_relevance/kaggle_all_model_scores.csv"
echo
echo "Top rows:"
python - <<'PY'
import pandas as pd
from pathlib import Path
path = Path("data/models/ai_relevance/kaggle_all_model_scores.csv")
df = pd.read_csv(path, dtype=str, keep_default_na=False)
cols = [
    "model_family",
    "frozen_test_macro_f1",
    "validation_macro_f1",
    "frozen_test_accuracy",
    "ai_precision",
    "ai_recall",
    "non_ai_recall",
    "source_file",
]
existing = [col for col in cols if col in df.columns]
print(df[existing].head(20).to_string(index=False))
PY
