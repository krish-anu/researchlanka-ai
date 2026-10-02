# AI Relevance Model Development Report

This document summarizes the current AI relevance model work, human-reviewed
evaluation, production A1 XGBoost selection, calibration, and remaining-pending
predictions.

## 1. Current Production Direction

Deprecated LLM-label self-evaluation runs have been removed from the benchmark
narrative. Those earlier results measured reproduction of generated labels
rather than independent human-label agreement and should not be used as project
performance evidence.

The current production direction is:

```text
Model: A1 XGBoost
Features: title + abstract
Calibration: sigmoid-v1
Production decision: AUTO_AI / REVIEW / AUTO_NON_AI
Primary priority: maximum AI precision
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

## 2A. Human Annotation Protocol and Benchmark Stability

The project now distinguishes between:

| Label set type | Purpose | Benchmark interpretation |
| --- | --- | --- |
| Human-verified operational labels | Resolve uncertain cases, improve training data, calibrate scores, and audit false positives | Useful for curation and model improvement |
| Blinded adjudicated benchmark labels | Estimate stable model performance | Suitable for benchmark reporting |

The historical review batches used in this report do not consistently record
all benchmark-stability metadata:

- guideline version, currently `ai-relevance-annotation-v1.1`;
- number of independent annotators;
- whether annotators were blinded to model predictions, confidence scores, and
  LLM reasoning;
- inter-annotator agreement;
- adjudication procedure;
- label changes after observing model errors;
- treatment of ambiguous `REVIEW` cases.

Future reviewed rows should also record `label`, `confidence`,
`evidence_span`, `reason`, and `ambiguous_flag`. First-pass labels should be
created independently before annotators see model predictions or confidence
scores.

Therefore, current human labels should be described as **human-verified
operational labels** unless a specific batch documents independent blinded
annotation, agreement, and adjudication. This does not invalidate the labels for
training, calibration, and false-positive analysis, but it limits claims about
the stability of the human benchmark.

For future benchmark reporting, use the protocol in:

```text
backend/docs/AI_RELEVANCE_ANNOTATION_PROTOCOL.md
```

Minimum required reporting for benchmark labels:

```text
Guideline version
Number of annotators
Blinding status
Overlap size
Percent agreement
Cohen's kappa
Adjudication rule
Final adjudicated label column
REVIEW handling rule
```

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

### Deprecated SVM Baselines Removed

Deprecated baseline details have been removed from this report to avoid
confusing them with the current production model. The current report focuses on
the validated XGBoost/A1 production path and human-test evidence.

## 4. Multi-Model Comparison

We compared:

```text
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
| 2 | Logistic Regression | 0.7440 | 0.6221 | 0.8283 | 0.3929 |
| 3 | Ridge Classifier | 0.7380 | 0.6119 | 0.8237 | 0.3750 |
| 4 | SGD Classifier | 0.7420 | 0.6071 | 0.8198 | 0.3482 |
| 5 | Multinomial NB | 0.7040 | 0.5659 | 0.8046 | 0.3125 |

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

The widened sklearn search is retained only as diagnostic context. It is not the
production selection and is not used as the headline model result.

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
| Manual-pattern cases | 13 |
| Statistical prediction or forecasting | 7 |
| Generic intelligent or algorithmic wording | 6 |
| Signal/image processing without clear AI | 5 |
| Education or assessment automation | 3 |

These rows are now maintained as a hard-negative `NON_AI` training set:

```text
backend/data/processed/ai/hard_negative_false_positive_non_ai.csv
```

The prediction pipeline also applies these categories as a conservative
post-score constraint layer. If a record is predicted as `AI`, matches a known
false-positive category, and lacks strong AI evidence in title, abstract, or
keywords, the output is changed to `review`. The original label and constraint
details are stored in:

```text
ai_classification_pre_constraint_label
ai_hard_negative_constraint_applied
ai_hard_negative_constraint_category
ai_hard_negative_constraint_evidence
```

Detailed file:

```text
backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/validated_human_selection_xgboost_fast/false_positive_analysis/false_positive_ai_cases.csv
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

**Earlier macro-F1 conclusion:** the best feature representation in this
initial ablation was:

```text
title + abstract + keywords
```

Broad metadata such as `topics`, `concepts`, `primary_field`, `primary_subfield`, and `primary_domain` appears to improve AI recall but hurts NON_AI recall and macro F1. It can inject misleading AI signals.

This A2 result was kept as an intermediate experiment. It was not the final
project-wide production choice after the precision-routed comparison was added.

## 9. Intermediate A2 Model

Intermediate selected model for this stage:

```text
Model: XGBoost
Features: title + abstract + keywords
Threshold: 0.35
```

Intermediate frozen-test scores:

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
The A2 model is stricter and cleaner than the broad-metadata variants.
It accepts fewer borderline AI records automatically, but improves AI precision and NON_AI recall.
```

Compared with clean old SVM on human test:

```text
Clean old SVM macro F1: 0.5917
Intermediate A2 XGBoost macro F1: 0.6601
Improvement: +0.0684
```

## 10. Remaining 1,207 Pending Rows

We applied the intermediate A2 model to:

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
backend/scripts/ai_relevance/build_balanced_human_audit_sample.py
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

## 13. Production Update: Precision-Routed A1 Model

The production manifest was updated on 2026-09-28 to use the precision-oriented
routed model:

```text
Model ID: ai-relevance-xgb-a1-precision-v1
Model: XGBoost
Features: title + abstract
Calibrator: sigmoid-v1
Calibrator artifact: backend/data/models/ai_relevance/metadata_ablation_precision_092/calibration/probability_calibrator_sigmoid.joblib
Auto-AI threshold: 0.929405
Auto-NON_AI threshold: 0.40
Binary evaluation threshold: 0.40
Artifact: backend/data/models/ai_relevance/metadata_ablation_precision_092/A1_title_abstract.joblib
```

Calibration status:

```text
Production calibration is enabled.
A sigmoid calibrator was fitted on the human validation split and evaluated on
the frozen human test split.
```

Calibrated AUTO_AI evaluation:

```text
Calibration validation at threshold 0.929405:
AI precision: 1.0000
AI recall: 0.2867
Auto-AI true positives: 43
Auto-AI false positives: 0

Frozen test at threshold 0.929405:
AI precision: 0.9914
AI recall: 0.2926
Auto-AI true positives: 115
Auto-AI false positives: 1
```

Binary frozen-test scores:

```text
Accuracy: 0.7120
Macro F1: 0.6571
AI precision: 0.9055
AI recall: 0.7074
NON_AI recall: 0.7290
Binary false positives: 29
```

Three-way routed frozen-test scores:

```text
Auto-AI rows: 152
Review rows: 155
Auto-NON_AI rows: 193
Auto-AI false positives: 1
Auto-AI precision: 0.9934
Review rate: 0.3100
```

The routed score is the production-facing metric because uncertain records are
not forced into binary acceptance or rejection.

Raw ablation scores are retained for model comparison. Production confidence
values now pass through the configured sigmoid calibrator.

### A1 vs A2 final decision

The project-wide final selection is **A1**.

Although A2 had slightly higher raw binary AI precision in the current
precision-ablation run, A1 provided the better overall project score balance:

| Metric | A1 title + abstract | A2 title + abstract + keywords | Selected |
|---|---:|---:|---|
| Accuracy | 0.7120 | 0.6940 | A1 |
| Macro F1 | 0.6571 | 0.6502 | A1 |
| AI precision | 0.9055 | 0.9225 | A2 |
| AI recall | 0.7074 | 0.6667 | A1 |
| NON_AI recall | 0.7290 | 0.7944 | A2 |
| Auto-AI precision | 0.9934 | 0.9935 | Tie / negligible A2 edge |
| Auto-AI false positives | 1 | 1 | Tie |
| Auto-AI rows | 152 | 155 | A2 |
| Review rows | 155 | 160 | A1 |

The A2 advantage in routed Auto-AI precision is only 0.0001 and both models
produce the same number of routed Auto-AI false positives. A1 is therefore the
better final project choice because it keeps near-identical safe Auto-AI
precision while improving macro F1, accuracy, AI recall, and review workload.

## 14. Final Recommendation

## 14A. New Model Experiment Update

Additional model families were tested after the production A1 XGBoost decision:

```text
Classical TF-IDF models:
Linear SVM, Logistic Regression, Ridge Classifier, SGD Classifier,
Multinomial Naive Bayes, XGBoost, LightGBM, CatBoost

Embedding models:
Sentence-transformer embeddings with Logistic Regression, Linear SVM,
Random Forest, and XGBoost classifiers

Transformer fine-tuning:
SciBERT, CPU run, 1 epoch
```

Combined score file:

```text
backend/data/models/ai_relevance/all_model_scores.csv
```

Headline results:

| Model / experiment | Split | Accuracy | Macro F1 | AI precision | AI recall | NON_AI recall | Interpretation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Production A1 XGBoost, title + abstract | frozen test | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 | Current production model remains best overall |
| sentence_transformer_logistic_regression | frozen test | 0.7360 | 0.6382 | 0.8556 | 0.7990 | 0.5047 | Best new experimental candidate by frozen-test macro F1 |
| sgd_classifier, validation-selected | frozen test | 0.6760 | 0.6082 | 0.8667 | 0.6947 | 0.6075 | Best validation-selected classical new run |
| SciBERT CPU, 1 epoch | frozen test | 0.7860 | 0.4401 | 0.7860 | 1.0000 | 0.0000 | Not usable; predicts all rows as AI |

The new experiments did not beat the production A1 XGBoost score balance.
Sentence-transformer logistic regression is the best new research candidate,
but its AI precision and NON_AI recall are weaker than the production model.
The one-epoch CPU SciBERT run collapsed to all-AI predictions and should not be
used as evidence that transformer fine-tuning is unsuitable; it only shows that
this quick run was insufficient.

Current new-experiment recommendation:

```text
Keep production A1 XGBoost.
Keep sentence_transformer_logistic_regression as a future candidate.
Retrain SciBERT only with stronger settings before reconsidering it.
```

For the current project stage, use:

```text
XGBoost with title + abstract
Sigmoid calibration enabled
Auto-AI threshold: 0.929405
Auto-NON_AI threshold: 0.40
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
3. Continued calibration monitoring as more human labels are added.
4. Two-threshold AUTO_AI / REVIEW / AUTO_NON_AI validation.
5. Sentence-transformer embeddings as a next-generation experiment.
```
