# AI Relevance New Model Experiments

Use this runbook to train extra AI relevance models and generate comparison
results. These commands do not replace the production model unless you choose to
promote a result later.

## 1. Validation-First Classical Models

This is the recommended first run because it preserves the frozen human test
set for final evaluation.

```bash
cd backend
python scripts/ai_relevance/run_validated_human_model_selection.py \
  --output-dir data/models/ai_relevance/new_model_comparison_validated \
  --model-families linear_svm,logistic_regression,ridge_classifier,sgd_classifier,multinomial_nb,xgboost \
  --include-xgboost \
  --fast-xgboost
```

Main output:

```text
backend/data/models/ai_relevance/new_model_comparison_validated/validation_selection_leaderboard.csv
backend/data/models/ai_relevance/new_model_comparison_validated/validated_selection_metrics.txt
backend/data/models/ai_relevance/new_model_comparison_validated/validated_selection_summary.json
```

## 2. Optional LightGBM and CatBoost

Install optional packages first if they are not already available:

```bash
cd backend
.venv/bin/pip install lightgbm catboost
```

Then run:

```bash
cd backend
python scripts/ai_relevance/run_validated_human_model_selection.py \
  --output-dir data/models/ai_relevance/new_model_comparison_boosting \
  --model-families linear_svm,logistic_regression,ridge_classifier,sgd_classifier,multinomial_nb,xgboost,lightgbm,catboost \
  --include-xgboost \
  --include-lightgbm \
  --include-catboost \
  --fast-xgboost
```

## 3. Clean Holdout Comparison

This script compares models directly on the locked human holdout. It is useful
for a presentation table, but the validation-first script is better for model
selection.

```bash
cd backend
python scripts/ai_relevance/compare_clean_human_holdout_models.py \
  --output-dir data/models/ai_relevance/new_model_comparison_clean_holdout \
  --model-families linear_svm,logistic_regression,ridge_classifier,multinomial_nb,sgd_classifier,xgboost,lightgbm,catboost \
  --include-xgboost \
  --include-lightgbm \
  --include-catboost \
  --tune-thresholds
```

Main output:

```text
backend/data/models/ai_relevance/new_model_comparison_clean_holdout/model_comparison.csv
backend/data/models/ai_relevance/new_model_comparison_clean_holdout/model_comparison_metrics.txt
```

## 4. Sentence-Transformer Embedding Models

Install optional packages first:

```bash
cd backend
.venv/bin/pip install sentence-transformers
```

Run the validation-first split first if needed, because the sentence-transformer
experiment reads `selection_training_dataset.csv`, `human_validation_set.csv`,
and `frozen_human_test_set.csv` from the selection directory.

```bash
cd backend
python scripts/ai_relevance/run_sentence_transformer_experiment.py \
  --selection-dir data/models/ai_relevance/new_model_comparison_validated \
  --output-dir data/models/ai_relevance/new_model_comparison_sentence_transformer \
  --sentence-transformer-model sentence-transformers/all-MiniLM-L6-v2 \
  --classifiers logistic_regression,linear_svm,random_forest,xgboost
```

Optional if LightGBM and CatBoost are installed:

```bash
cd backend
python scripts/ai_relevance/run_sentence_transformer_experiment.py \
  --selection-dir data/models/ai_relevance/new_model_comparison_validated \
  --output-dir data/models/ai_relevance/new_model_comparison_sentence_transformer_boosting \
  --sentence-transformer-model sentence-transformers/all-MiniLM-L6-v2 \
  --classifiers logistic_regression,linear_svm,random_forest,xgboost,lightgbm,catboost
```

Main output:

```text
backend/data/models/ai_relevance/new_model_comparison_sentence_transformer/sentence_transformer_comparison.csv
backend/data/models/ai_relevance/new_model_comparison_sentence_transformer/sentence_transformer_metrics.txt
```

## 5. SciBERT / Transformer Fine-Tuning

Install optional packages first:

```bash
cd backend
.venv/bin/pip install torch transformers accelerate
```

Run:

```bash
cd backend
python scripts/ai_relevance/run_transformer_finetune_experiment.py \
  --selection-dir data/models/ai_relevance/new_model_comparison_validated \
  --output-dir data/models/ai_relevance/new_model_comparison_scibert \
  --model-name allenai/scibert_scivocab_uncased \
  --epochs 3 \
  --batch-size 8 \
  --max-length 256
```

Main output:

```text
backend/data/models/ai_relevance/new_model_comparison_scibert/transformer_comparison.csv
backend/data/models/ai_relevance/new_model_comparison_scibert/transformer_metrics.txt
backend/data/models/ai_relevance/new_model_comparison_scibert/transformer_frozen_test_predictions.csv
```

## Recommended Comparison Columns

For the final table, compare:

```text
model_family
validation_macro_f1
frozen_test_accuracy
frozen_test_macro_f1
ai_precision
ai_recall
non_ai_recall
false positives
review workload, if using a three-way routed threshold
```

For this project, prefer models that improve AI precision without collapsing
AI recall or NON_AI recall.

## Completed New-Model Results

The latest combined comparison file is:

```text
backend/data/models/ai_relevance/all_model_scores.csv
```

It was generated with:

```bash
cd backend
python scripts/ai_relevance/collect_model_comparison_scores.py \
  --output data/models/ai_relevance/all_model_scores.csv
```

Current result summary:

| Model / experiment | Split used for headline | Accuracy | Macro F1 | AI precision | AI recall | NON_AI recall | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Production A1 XGBoost, title + abstract | frozen test | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 | Current production model remains best overall |
| sentence_transformer_logistic_regression | frozen test | 0.7360 | 0.6382 | 0.8556 | 0.7990 | 0.5047 | Best new experimental candidate by frozen-test macro F1 |
| sgd_classifier, validation-selected | frozen test | 0.6760 | 0.6082 | 0.8667 | 0.6947 | 0.6075 | Best validation-selected classical new run |
| sentence_transformer_xgboost | frozen test | 0.7940 | 0.5355 | 0.8021 | 0.9796 | 0.1121 | High AI recall, poor NON_AI recall |
| sentence_transformer_random_forest | frozen test | 0.7980 | 0.5112 | 0.7980 | 0.9949 | 0.0748 | Mostly predicts AI |
| sentence_transformer_linear_svm | frozen test | 0.7860 | 0.5109 | 0.7967 | 0.9771 | 0.0841 | Mostly predicts AI |
| SciBERT CPU, 1 epoch | frozen test | 0.7860 | 0.4401 | 0.7860 | 1.0000 | 0.0000 | Not usable yet; predicts all rows as AI |

Validation-first selected classical model:

```text
Model: SGD Classifier
Human label weight: 2.0
Threshold: 0.66
Validation macro F1: 0.6841
Frozen-test macro F1: 0.6082
Frozen-test confusion matrix [AI, NON_AI]: [[273, 120], [42, 65]]
```

Current interpretation:

```text
1. Keep production A1 XGBoost for the application.
2. Treat sentence_transformer_logistic_regression as the best new research candidate.
3. Do not promote the one-epoch CPU SciBERT model.
4. For a stronger transformer result, rerun SciBERT with more epochs, better class balance,
   or GPU training, then compare again using all_model_scores.csv.
```
