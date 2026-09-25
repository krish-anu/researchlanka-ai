# AI Relevance Model Development Report

This document summarizes the AI relevance model work from the original model through the final validated model and remaining-pending predictions.

## 1. Starting Point: Original AI Relevance Linear SVM

**Goal:** classify publications as AI-related or NON_AI.

**Training data used:**

- `backend/data/processed/ai/ai_llm_5000_predictions_openrouter_gemini_3_8_flash.csv`
- 5,000 Gemini/OpenRouter-labelled candidate records.
- Only successful binary labels were used.
- `REVIEW`, failed, and blank-text rows were excluded.

**Usable rows:**

```text
Input rows: 5,000
Usable binary rows: 4,437
AI: 1,534
NON_AI: 2,903
Train rows: 3,549
Test rows: 888
```

**Features used:**

```text
title
abstract
keywords
topics
concepts
primary_topic
primary_subfield
primary_field
primary_domain
```

**Model:**

```text
TF-IDF + Linear SVM
Best C: 10.0
CV macro F1: 0.9291
```

**Original LLM-label test scores:**

```text
Accuracy: 0.9595
Macro F1: 0.9552
Weighted F1: 0.9595
AI precision: 0.94
AI recall: 0.94
NON_AI precision: 0.97
NON_AI recall: 0.97
```

**Important limitation:** these test labels came from the same LLM-generated labelling process as the training labels. Therefore, this mainly measured:

```text
How well can the model reproduce Gemini/OpenRouter labels?
```

It did not directly measure:

```text
How well does the model agree with human judgement?
```

## 2. Human Audit Discovery

We found a human-labelled audit file:

```text
backend/data/final_ai_corpus_human_audit_sample_stratified - final_ai_corpus_human_audit_sample_stratified (1).csv
```

This file contained a human-labelled audit sample from the final AI corpus.

Initial valid rows:

```text
Human AI: 438
Human NON_AI: 62
Valid evaluated rows: 500
```

Since these records came from the model-accepted AI corpus, this file is strongest as an **AI precision audit**, not a complete unbiased full-corpus classifier test.

## 3. Clean Human-Holdout Experiment

To make a fairer comparison, we combined available human-labelled records:

```text
early 500 human audit
+ later 800 human review
```

Then we deduplicated records and selected a locked hidden human test set.

**Human pool:**

```text
Deduplicated human pool rows: 1,147
Hidden human test rows: 500
Human training remainder rows: 641
Hidden test labels: AI 388, NON_AI 112
```

**Leakage prevention:**

- Hidden-test rows were removed from old model training data.
- Hidden-test rows were removed from new model training data.
- Matching used publication identifiers such as DOI, OpenAlex ID, source record ID, and normalized title/year keys.

### Clean Old SVM vs Clean New SVM

**Old clean model:**

```text
Training rows: 4,361
AI: 1,458
NON_AI: 2,903
Best C: 10.0
CV macro F1: 0.9338
Human-test accuracy: 0.7300
Human-test macro F1: 0.5917
Confusion matrix [AI, NON_AI]: [[328, 60], [75, 37]]
```

**New clean model:**

Training data:

```text
Original LLM 5k labels
+ finished Gemini 1000 labels
+ remaining human-labelled training rows
```

Scores:

```text
Training rows: 5,327
AI: 2,257
NON_AI: 3,070
Best C: 1.0
CV macro F1: 0.9156
Human-test accuracy: 0.7500
Human-test macro F1: 0.6346
Confusion matrix [AI, NON_AI]: [[328, 60], [65, 47]]
```

**Improvement from old clean SVM to new clean SVM:**

```text
Accuracy: +0.0200
Macro F1: +0.0429
NON_AI correct rows: 37 -> 47
False-positive AI cases: 75 -> 65
```

## 4. Multi-Model Comparison

We compared:

```text
Linear SVM
Logistic Regression
Ridge Classifier
Multinomial Naive Bayes
SGD Classifier
XGBoost
```

All models used the same clean training data and the same human test set.

### Standard Comparison

Best by human-test macro F1:

| Rank | Model | Accuracy | Macro F1 | AI Precision | NON_AI Recall |
|---:|---|---:|---:|---:|---:|
| 1 | XGBoost | 0.7220 | 0.6414 | 0.8567 | 0.5536 |
| 2 | Linear SVM | 0.7500 | 0.6346 | 0.8346 | 0.4196 |
| 3 | Logistic Regression | 0.7440 | 0.6221 | 0.8283 | 0.3929 |
| 4 | Ridge Classifier | 0.7380 | 0.6119 | 0.8237 | 0.3750 |
| 5 | SGD Classifier | 0.7420 | 0.6071 | 0.8198 | 0.3482 |
| 6 | Multinomial NB | 0.7040 | 0.5659 | 0.8046 | 0.3125 |

### Threshold-Tuned Exploratory Comparison

Threshold tuning was first explored on the human test set. This was useful for diagnostics, but not final evidence because test-set threshold tuning leaks information.

Best exploratory threshold result:

```text
XGBoost
Threshold: 0.41
Tuned macro F1: 0.6576
Accuracy: 0.7560
AI precision: 0.8500
NON_AI recall: 0.4911
```

### Wide Sklearn Hyperparameter Search

We also widened the sklearn model/vectorizer search.

Best wide sklearn model:

```text
Linear SVM
C: 3.0
TF-IDF max_df: 0.90
TF-IDF min_df: 1
N-grams: 1-2
Sublinear TF: true
Accuracy: 0.7700
Macro F1: 0.6570
AI precision: 0.8421
NON_AI recall: 0.4375
```

This was strong, but it was still part of exploratory comparison.

## 5. Validation-First Model Selection

To avoid using the frozen test set for model choice, we introduced a validation-first selection workflow.

Script:

```text
backend/scripts/ai_relevance/run_validated_human_model_selection.py
```

Process:

```text
1. Keep frozen 500-row human test set separate.
2. Split remaining human labels into human_train and human_validation.
3. Remove validation/test overlap from all machine-labelled training sources.
4. Train candidate models.
5. Tune human-label sample weight using validation.
6. Tune decision threshold using validation.
7. Evaluate selected model once on frozen human test.
```

Selected validation-correct model:

```text
Model: XGBoost
Human label weight: 3.0
Threshold: 0.49
Validation accuracy: 0.7720
Validation macro F1: 0.6652
Frozen-test accuracy: 0.7560
Frozen-test macro F1: 0.6576
Confusion matrix [AI, NON_AI]: [[323, 70], [52, 55]]
```

This result came after correcting five human labels that were re-reviewed as AI-related.

## 6. Human Label Re-Audit

We found suspicious human `NON_AI` labels that appeared AI-related:

```text
PharmaGo-An Online Pharmaceutical Ordering Platform
A Game Centric E-Learning Application For Preschoolers
DenPAR: Annotated Intra-Oral Periapical Radiographs Dataset for Machine Learning
Visually impaired support-system for identification of notes (VISION)
Rule-Based Recommendation System for Phylogenetic Inference
```

These were updated to confirmed AI.

Script:

```text
backend/scripts/ai_relevance/apply_human_label_reaudit.py
```

The human files now support:

```text
human_final_label
human_review_status
human_reaudit_notes
```

Allowed review statuses:

```text
CONFIRMED_AI
CONFIRMED_NON_AI
AMBIGUOUS_REVIEW
```

Current status counts:

```text
Early human file:
CONFIRMED_AI: 445
CONFIRMED_NON_AI: 63
AMBIGUOUS_REVIEW: 8

Late human file:
CONFIRMED_AI: 533
CONFIRMED_NON_AI: 237
AMBIGUOUS_REVIEW: 30
```

Ambiguous rows are excluded from supervised training/evaluation.

## 7. False-Positive Error Analysis

Script:

```text
backend/scripts/ai_relevance/analyze_false_positive_ai_errors.py
```

It extracts cases where:

```text
human label = NON_AI
model prediction = AI
```

After re-audit, false-positive AI rows:

```text
52
```

Auto category summary:

| Error Category | Count |
|---|---:|
| IoT or smart system without clear AI | 18 |
| Needs manual pattern review | 13 |
| Statistical prediction or forecasting | 7 |
| Generic intelligent or algorithmic wording | 6 |
| Signal/image processing without clear AI | 5 |
| Education or assessment automation | 3 |

Detailed file:

```text
backend/data/models/ai_relevance/validated_human_selection_xgboost_fast/false_positive_analysis/false_positive_ai_cases.csv
```

## 8. Metadata Ablation

The false-positive analysis suggested broad metadata fields were injecting misleading AI signals. We tested four feature sets.

Script:

```text
backend/scripts/ai_relevance/run_metadata_ablation.py
```

Ablations:

```text
A1 = title + abstract
A2 = title + abstract + keywords
A3 = title + abstract + keywords + primary_topic
A4 = all current fields
```

Results:

| Ablation | Features | Accuracy | Macro F1 | AI Precision | AI Recall | NON_AI Recall | Threshold |
|---|---|---:|---:|---:|---:|---:|---:|
| A2 | title + abstract + keywords | 0.7320 | 0.6601 | 0.8843 | 0.7583 | 0.6355 | 0.35 |
| A1 | title + abstract | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 | 0.40 |
| A4 | all current fields | 0.7640 | 0.6340 | 0.8395 | 0.8651 | 0.3925 | 0.38 |
| A3 | title + abstract + keywords + primary_topic | 0.7400 | 0.6261 | 0.8433 | 0.8219 | 0.4393 | 0.31 |

**Conclusion:** the best feature representation is:

```text
title + abstract + keywords
```

Broad metadata such as `topics`, `concepts`, `primary_field`, `primary_subfield`, and `primary_domain` appears to improve AI recall but hurts NON_AI recall and macro F1. It can inject misleading AI signals.

## 9. Final Selected Model

Final selected model for the current stage:

```text
Model: XGBoost
Features: title + abstract + keywords
Threshold: 0.35
```

Final frozen-test scores:

```text
Accuracy: 0.7320
Macro F1: 0.6601
AI precision: 0.8843
AI recall: 0.7583
NON_AI recall: 0.6355
```

Confusion matrix:

```text
Labels: [AI, NON_AI]

              Pred AI   Pred NON_AI
Actual AI        298        95
Actual NON_AI     39        68
```

Interpretation:

```text
The final A2 model is stricter and cleaner.
It accepts fewer borderline AI records automatically, but improves AI precision and NON_AI recall.
```

Compared with the original LLM-label SVM test:

```text
Original LLM-label macro F1: 0.9552
Final human-test macro F1: 0.6601
```

These are not directly comparable because the original score measured LLM-label reproduction, while the final score measures human-label agreement.

Compared with clean old SVM on human test:

```text
Clean old SVM macro F1: 0.5917
Final A2 XGBoost macro F1: 0.6601
Improvement: +0.0684
```

## 10. Remaining 1,207 Pending Rows

We applied the final A2 model to:

```text
backend/data/pending-review-split/model_predict_remaining_1207.csv
```

Script:

```text
backend/scripts/ai_relevance/predict_remaining_with_a2_model.py
```

Output:

```text
backend/data/processed/ai/model_predict_remaining_1207_a2_predictions.csv
```

All rows were joined back to metadata:

```text
metadata_joined: 1,207 / 1,207
```

Three-way production decision:

```text
AUTO_AI: 854
REVIEW: 290
AUTO_NON_AI: 63
```

Binary prediction using threshold 0.35:

```text
AI: 1,084
NON_AI: 123
```

Recommended production use:

```text
AUTO_AI -> accept as AI
REVIEW -> keep for manual review
AUTO_NON_AI -> reject as non-AI
```

## 11. Scripts Added

```text
backend/scripts/ai_relevance/update_model_with_finished_reviews.py
backend/scripts/ai_relevance/build_balanced_human_audit_sample.py
backend/scripts/ai_relevance/run_clean_human_holdout_experiment.py
backend/scripts/ai_relevance/compare_clean_human_holdout_models.py
backend/scripts/ai_relevance/run_validated_human_model_selection.py
backend/scripts/ai_relevance/analyze_false_positive_ai_errors.py
backend/scripts/ai_relevance/apply_human_label_reaudit.py
backend/scripts/ai_relevance/run_metadata_ablation.py
backend/scripts/ai_relevance/predict_remaining_with_a2_model.py
```

## 12. Main Output Files

```text
backend/data/models/ai_relevance/clean_human_holdout/clean_human_holdout_metrics.txt
backend/data/models/ai_relevance/clean_human_holdout/model_comparison/model_comparison.csv
backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/model_comparison.csv
backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/model_comparison.csv
backend/data/models/ai_relevance/validated_human_selection_xgboost_fast/validated_selection_metrics.txt
backend/data/models/ai_relevance/validated_human_selection_xgboost_fast/validation_selection_leaderboard.csv
backend/data/models/ai_relevance/validated_human_selection_xgboost_fast/false_positive_analysis/false_positive_ai_cases.csv
backend/data/models/ai_relevance/metadata_ablation/metadata_ablation_comparison.csv
backend/data/processed/ai/model_predict_remaining_1207_a2_predictions.csv
backend/data/processed/ai/model_predict_remaining_1207_a2_prediction_summary.csv
```

## 13. Final Recommendation

For the current project stage, use:

```text
XGBoost with title + abstract + keywords
Threshold: 0.35
Three-way production decision:
AUTO_AI / REVIEW / AUTO_NON_AI
```

Use the final 1,207-row prediction file for pending review resolution:

```text
backend/data/processed/ai/model_predict_remaining_1207_a2_predictions.csv
```

For future improvement, prioritize:

```text
1. Manual categorization of remaining false positives.
2. More hard NON_AI training examples from similar error families.
3. Probability calibration.
4. Two-threshold AUTO_AI / REVIEW / AUTO_NON_AI validation.
5. Sentence-transformer embeddings as a next-generation experiment.
```
