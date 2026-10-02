# ResearchLanka AI Classification Presentation

This slide script explains the full project path for the AI relevance classification work: what we built first, what results we got, what problems we found, and how each update improved the system.

## Slide 1: Title

**ResearchLanka AI: AI Publication Classification Path**

Subtitle:

Building a human-validated AI relevance classifier for Sri Lankan scholarly publications.

Presenter note:

This presentation explains how the project moved from raw publication collection to a production AI relevance classifier. The focus is not only the final model, but the full improvement path.

## Slide 2: Project Goal

**Goal:** identify scholarly publications that are truly related to Artificial Intelligence and connected to Sri Lanka.

Why this matters:

- The platform should show reliable Sri Lankan AI research.
- General research records must be filtered before topic modelling and dashboards.
- The final dataset should avoid false AI records as much as possible.

Clear definition:

A publication is AI-related when AI is a substantial part of the research objective, method, application, evaluation, analysis, or main subject.

## Slide 3: Full Data Path

```text
External publication sources
        |
        v
Collection
        |
        v
Common schema mapping
        |
        v
Cleaning and normalization
        |
        v
Deduplication
        |
        v
Sri Lanka ownership filtering
        |
        v
AI relevance classification
        |
        v
Human review and model improvement
        |
        v
AI-only publication dataset
        |
        v
Database, API, and dashboard
```

Presenter note:

AI classification is one stage inside a larger research analytics pipeline. Before classification, the records must be collected, cleaned, normalized, deduplicated, and checked for Sri Lanka relevance.

## Slide 4: Data Sources

Records were collected from multiple scholarly metadata sources:

- OpenAlex
- Crossref
- SLJOL
- Institutional repositories
- OAI-PMH repositories
- DSpace REST sources
- HTML metadata sources

Important point:

The project keeps source provenance using fields such as `source_dataset`, `source_institution_id`, and `source_record_id`.

## Slide 5: Preprocessing and Common Schema

After collection, records were converted into one common structure.

Main updates:

- Normalized publication identifiers such as DOI and OpenAlex ID.
- Standardized publication dates and year fields.
- Normalized author and institution fields.
- Preserved topics, concepts, keywords, abstracts, and source metadata.
- Prepared the dataset for repeatable analysis.

Result:

The project moved from many source formats to one unified publication dataset.

## Slide 6: Sri Lanka Relevance Gate

Before AI classification, the dataset checks whether a publication has valid Sri Lanka evidence.

Examples of Sri Lanka evidence:

- Sri Lankan authors
- Sri Lankan institutions
- Country fields
- Ownership decision
- Ownership confidence
- Ownership reason and evidence

Final dataset rule:

Only records with accepted Sri Lanka ownership evidence should enter the final application dataset.

## Slide 7: First AI Classification Direction

Initial AI relevance work used candidate sampling and LLM-assisted review.

Candidate sample design:

- AI-looking OpenAlex topics and concepts
- Strong AI text candidates
- Cross-domain AI candidates
- Computer Science hard negatives
- Borderline ambiguous records
- Field-stratified random records

Important lesson:

Keyword matching and LLM labels helped find useful examples, but they were not enough for final benchmark evidence.

## Slide 8: Human Review Becomes the Standard

The project found and used human-labelled review data.

Human-labelled pool:

- Early human audit
- Later human review
- Deduplicated human pool: 1,147 rows
- Hidden human test set: 500 rows
- Human training remainder: 641 rows

Hidden test label distribution:

- AI: 388
- NON_AI: 112

Improvement:

The project moved from model-generated label evaluation to human-label agreement.

## Slide 9: Leakage Prevention

To make the benchmark fair, hidden test rows were removed from training data.

Matching used:

- DOI
- OpenAlex ID
- Source record ID
- Normalized title and publication year

Why this matters:

If test records appear in training data, the model can look better than it really is. Removing overlap gives a more trustworthy evaluation.

## Slide 10: Multi-Model Comparison

Several models were compared on the same clean human test set:

- Logistic Regression
- Ridge Classifier
- Multinomial Naive Bayes
- SGD Classifier
- XGBoost

Best standard result by macro F1:

| Model | Accuracy | Macro F1 | AI Precision | NON_AI Recall |
| --- | ---: | ---: | ---: | ---: |
| XGBoost | 0.7220 | 0.6414 | 0.8567 | 0.5536 |
| Logistic Regression | 0.7440 | 0.6221 | 0.8283 | 0.3929 |
| Ridge Classifier | 0.7380 | 0.6119 | 0.8237 | 0.3750 |
| SGD Classifier | 0.7420 | 0.6071 | 0.8198 | 0.3482 |
| Multinomial NB | 0.7040 | 0.5659 | 0.8046 | 0.3125 |

Conclusion:

XGBoost gave the best macro F1 and became the strongest direction.

## Slide 11: Validation-First Model Selection

Problem:

Tuning directly on the frozen test set can leak information.

Update:

A validation-first workflow was introduced:

1. Keep the 500-row human test set frozen.
2. Split remaining human labels into training and validation.
3. Remove validation and test overlap from machine-labelled training data.
4. Train candidate models.
5. Tune human label weight on validation.
6. Tune threshold on validation.
7. Evaluate once on frozen human test.

Result:

Selected model: XGBoost  
Human label weight: 3.0  
Threshold: 0.49

## Slide 12: Validation-First Results

Validation result:

- Accuracy: 0.7720
- Macro F1: 0.6652

Frozen test result:

- Accuracy: 0.7560
- Macro F1: 0.6576

Confusion matrix on frozen test:

```text
Labels: [AI, NON_AI]

              Pred AI   Pred NON_AI
Actual AI        323        70
Actual NON_AI     52        55
```

Improvement:

This created a more reliable model-selection process because the final test set stayed separate.

## Slide 13: Human Label Re-Audit

During error analysis, some human `NON_AI` labels looked suspicious.

Examples re-reviewed as AI-related:

- Online pharmaceutical ordering platform
- Game-centric e-learning application
- Radiograph dataset for machine learning
- Visually impaired note identification system
- Recommendation system for phylogenetic inference

Update:

Human files now support:

- `human_final_label`
- `human_review_status`
- `human_reaudit_notes`

Improvement:

The training and evaluation labels became cleaner.

## Slide 14: False Positive Analysis

The project studied cases where:

```text
human label = NON_AI
model prediction = AI
```

After re-audit, 52 false-positive AI rows remained.

Main false-positive categories:

| Category | Count |
| --- | ---: |
| IoT or smart system without clear AI | 18 |
| Manual-pattern cases | 13 |
| Statistical prediction or forecasting | 7 |
| Generic intelligent or algorithmic wording | 6 |
| Signal/image processing without clear AI | 5 |
| Education or assessment automation | 3 |

Improvement:

These examples became hard-negative `NON_AI` training data.

## Slide 15: Metadata Ablation

The team tested which metadata fields helped or hurt classification.

Feature sets:

- A1: title + abstract
- A2: title + abstract + keywords
- A3: title + abstract + keywords + primary topic
- A4: all current metadata fields

Key result:

Broad metadata fields improved recall in some cases but added misleading AI signals and hurt clean NON_AI detection.

## Slide 16: Ablation Results

| Features | Accuracy | Macro F1 | AI Precision | AI Recall | NON_AI Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| A2 title + abstract + keywords | 0.7320 | 0.6601 | 0.8843 | 0.7583 | 0.6355 |
| A1 title + abstract | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 |
| A4 all fields | 0.7640 | 0.6340 | 0.8395 | 0.8651 | 0.3925 |
| A3 title + abstract + keywords + primary topic | 0.7400 | 0.6261 | 0.8433 | 0.8219 | 0.4393 |

Interpretation:

A2 had the highest macro F1 in the first ablation, but A1 gave stronger AI precision and better NON_AI recall.

## Slide 17: Intermediate A2 Model

Intermediate model:

- Model: XGBoost
- Features: title + abstract + keywords
- Threshold: 0.35

Frozen-test scores:

- Accuracy: 0.7320
- Macro F1: 0.6601
- AI precision: 0.8843
- AI recall: 0.7583
- NON_AI recall: 0.6355

Improvement over older clean SVM:

- Old SVM macro F1: 0.5917
- A2 XGBoost macro F1: 0.6601
- Improvement: +0.0684

## Slide 18: Pending Records Prediction

The intermediate A2 model was applied to 1,207 pending rows.

Metadata joined:

- 1,207 / 1,207 rows

Three-way decision result:

| Decision | Rows |
| --- | ---: |
| AUTO_AI | 854 |
| REVIEW | 290 |
| AUTO_NON_AI | 63 |

Meaning:

- `AUTO_AI`: accept as AI
- `REVIEW`: send to manual review
- `AUTO_NON_AI`: reject as non-AI

## Slide 19: Final Production Model

Final production direction:

- Model ID: `ai-relevance-xgb-a1-precision-v1`
- Model type: XGBoost
- Features: title + abstract
- Calibration: sigmoid-v1
- Production decision: `AUTO_AI / REVIEW / AUTO_NON_AI`
- Main priority: high AI precision

Thresholds:

- AUTO_AI threshold: 0.929405
- AUTO_NON_AI threshold: 0.4000
- Binary evaluation threshold: 0.4000

## Slide 20: Why A1 Became Final

A1 and A2 were very close for routed Auto-AI precision, but A1 had better balance.

| Decision Factor | A1 | A2 | Winner |
| --- | ---: | ---: | --- |
| Accuracy | 0.7120 | 0.6940 | A1 |
| Macro F1 | 0.6571 | 0.6502 | A1 |
| AI precision | 0.9055 | 0.9225 | A2 |
| AI recall | 0.7074 | 0.6667 | A1 |
| Auto-AI precision | 0.9934 | 0.9935 | Tie |
| Auto-AI false positives | 1 | 1 | Tie |
| Review rows | 155 | 160 | A1 |

Final decision:

A1 was selected because it had better accuracy, macro F1, AI recall, and lower review workload.

## Slide 21: Calibration and Routing Results

Production uses calibrated scores and high-confidence routing.

Calibration validation at AUTO_AI threshold 0.929405:

- AI precision: 1.0000
- AI recall: 0.2867
- Auto-AI true positives: 43
- Auto-AI false positives: 0

Frozen test at AUTO_AI threshold 0.929405:

- AI precision: 0.9914
- AI recall: 0.2926
- Auto-AI true positives: 115
- Auto-AI false positives: 1

Interpretation:

The model automatically accepts only very confident AI records and sends uncertain cases to review.

## Slide 22: Hard-Negative Constraint Layer

After scoring, the pipeline applies a conservative rule.

If a record:

- is predicted as AI,
- matches a known false-positive category,
- and does not contain strong AI evidence,

then it is changed from automatic AI to `REVIEW`.

Saved fields:

- `ai_classification_pre_constraint_label`
- `ai_hard_negative_constraint_applied`
- `ai_hard_negative_constraint_category`
- `ai_hard_negative_constraint_evidence`

Improvement:

Known false-positive patterns are controlled before records enter the final AI corpus.

## Slide 23: Final AI Classification Path Summary

```text
1. Collect publication metadata
2. Normalize into common schema
3. Clean identifiers, dates, authors, institutions, topics, and abstracts
4. Deduplicate records
5. Apply Sri Lanka ownership gate
6. Build AI candidate samples
7. Use human review to create trusted labels
8. Compare baseline models
9. Select XGBoost using validation-first workflow
10. Re-audit suspicious human labels
11. Analyze false positives
12. Add hard negatives
13. Test metadata feature sets
14. Calibrate model probabilities
15. Route records as AUTO_AI, REVIEW, or AUTO_NON_AI
16. Publish AI-only dataset to database, API, and dashboard
```

## Slide 24: New Model Experiments

After the production A1 XGBoost model was selected, we tested more model families.

New models tested:

- Classical TF-IDF models: Linear SVM, Logistic Regression, Ridge, SGD, Naive Bayes
- Boosting models: XGBoost, LightGBM, CatBoost
- Sentence-transformer embeddings with multiple classifiers
- SciBERT fine-tuning on CPU for 1 epoch

Combined result file:

```text
backend/data/models/ai_relevance/all_model_scores.csv
```

Presenter note:

These runs were research experiments. They help us check whether a newer model should replace the production model.

## Slide 25: New Model Scores

| Model | Accuracy | Macro F1 | AI Precision | AI Recall | NON_AI Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production A1 XGBoost | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 |
| Sentence-transformer + Logistic Regression | 0.7360 | 0.6382 | 0.8556 | 0.7990 | 0.5047 |
| Validation-selected SGD Classifier | 0.6760 | 0.6082 | 0.8667 | 0.6947 | 0.6075 |
| Sentence-transformer + XGBoost | 0.7940 | 0.5355 | 0.8021 | 0.9796 | 0.1121 |
| SciBERT CPU, 1 epoch | 0.7860 | 0.4401 | 0.7860 | 1.0000 | 0.0000 |

Interpretation:

Sentence-transformer logistic regression was the best new experimental model, but it did not beat production A1 XGBoost overall.

## Slide 26: Best New Candidate

Best new experimental candidate:

```text
Sentence-transformer embeddings + Logistic Regression
```

Strengths:

- Higher AI recall than production A1 XGBoost
- Good frozen-test macro F1 among the new runs
- Useful future research direction

Limitations:

- Lower AI precision than production A1 XGBoost
- Lower NON_AI recall
- More false positives than the precision-routed production model

Decision:

Keep it as a research candidate, not the production replacement yet.

## Slide 27: SciBERT Result

SciBERT was tested as a quick CPU fine-tuning run:

```text
Model: allenai/scibert_scivocab_uncased
Epochs: 1
Batch size: 4
Max length: 128
```

Result:

```text
Accuracy: 0.7860
Macro F1: 0.4401
AI recall: 1.0000
NON_AI recall: 0.0000
```

Interpretation:

The model predicted every frozen-test record as AI. This run is not usable for production. It does not prove SciBERT is bad; it shows that this quick CPU run was not enough.

## Slide 28: Final Model Decision After New Experiments

Current production model remains:

```text
Model ID: ai-relevance-xgb-a1-precision-v1
Model: XGBoost
Features: title + abstract
Calibration: sigmoid-v1
Decision: AUTO_AI / REVIEW / AUTO_NON_AI
```

Why we keep it:

- Highest overall score balance
- Strong AI precision
- Better NON_AI recall than the new embedding models
- Supports calibrated high-confidence routing
- Only 1 Auto-AI false positive in routed frozen-test evaluation

## Slide 29: Main Improvements Over Time

| Stage | Problem Found | Update Made | Improvement |
| --- | --- | --- | --- |
| LLM/self-label stage | Metrics did not prove human agreement | Switched to human-reviewed evaluation | More trustworthy benchmark |
| Early model comparison | Needed best model family | Compared Logistic, Ridge, NB, SGD, XGBoost | XGBoost selected |
| Threshold tuning | Test-set tuning risk | Added validation-first selection | Reduced leakage risk |
| Human labels | Some labels were questionable | Re-audited suspicious labels | Cleaner supervision |
| False positives | Smart/IoT/prediction records looked like AI | Built hard-negative dataset | Better control of false AI records |
| Metadata features | Broad metadata created misleading signals | Ran ablation tests | Final model used cleaner title + abstract features |
| Production decision | Binary output was too simple | Added calibrated three-way routing | High-confidence auto decisions plus review queue |
| New-model experiments | Needed to test newer approaches | Tried LightGBM, CatBoost, sentence transformers, and SciBERT | Production A1 XGBoost still best overall |

## Slide 30: Final Message

The final AI classification system is not just one model. It is a full evidence-based workflow:

- reliable data collection,
- common schema processing,
- Sri Lanka relevance filtering,
- human-reviewed AI labels,
- validation-first model selection,
- false-positive analysis,
- hard-negative constraints,
- calibrated three-way routing,
- and final publication through the ResearchLanka dashboard.

Closing sentence:

The main improvement was moving from broad AI-looking signals to a human-validated, precision-focused classifier that protects the quality of the final Sri Lankan AI research dataset.

Latest conclusion:

The strongest new experiment is sentence-transformer logistic regression, but the project should keep the calibrated A1 XGBoost model for production.
