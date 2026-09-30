# AI Relevance Model Run Scores

This report consolidates the saved model-score artifacts from the repeated AI relevance training runs. It was generated from the files currently present in `backend/data/models/ai_relevance/` and the archived run artifacts under `backend/data/old_datasets_2026-09-30/`.

## Active Production Model

| Field | Value |
| --- | --- |
| model_id | ai-relevance-xgb-a1-precision-v1 |
| model_type | xgboost |
| model_path | data/models/ai_relevance/metadata_ablation_precision_092/A1_title_abstract.joblib |
| features | title, abstract |
| auto_ai_threshold | 0.8500 |
| auto_non_ai_threshold | 0.4000 |
| selected_binary_threshold | 0.4000 |
| training_dataset | human-reviewed-v4 |
| created_at | 2026-09-28 |
| sha256 | 47acbfca3364b5dcc74e2cf28439d643ba310e3de4ab3cbc189a69a258b311e6 |

## Current XGBoost Metadata Ablation Run: `metadata_ablation_precision_092`

Created at: `2026-09-28T09:11:54.829734+00:00`

| Config | Value |
| --- | --- |
| selection_dir | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/validated_human_selection_xgboost_fast |
| output_dir | backend/data/models/ai_relevance/metadata_ablation_precision_092 |
| human_weight | 3.0000 |
| random_state | 42 |
| threshold_objective | ai_precision |
| min_ai_precision | 0.9200 |
| auto_ai_threshold | 0.8500 |
| auto_non_ai_threshold | 0.4000 |

### Ablation Scores

| Ablation | Columns | Threshold | Val Macro F1 | Val AI Precision | Test Accuracy | Test Macro F1 | Test AI Precision | Test AI Recall | Test NON_AI Recall | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1_title_abstract | title, abstract | 0.4000 | 0.7089 | 0.9256 | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 | [[278, 115], [29, 78]] |
| A2_title_abstract_keywords | title, abstract, keywords | 0.4800 | 0.6937 | 0.9455 | 0.6940 | 0.6502 | 0.9225 | 0.6667 | 0.7944 | [[262, 131], [22, 85]] |
| A4_all_current_fields | title, abstract, keywords, topics, concepts, primary_topic, primary_subfield, primary_field, primary_domain | 0.8400 | 0.5723 | 0.9277 | 0.6180 | 0.5860 | 0.9106 | 0.5700 | 0.7944 | [[224, 169], [22, 85]] |
| A3_title_abstract_keywords_primary_topic | title, abstract, keywords, primary_topic | 0.8600 | 0.5593 | 0.9589 | 0.5660 | 0.5549 | 0.9731 | 0.4606 | 0.9533 | [[181, 212], [5, 102]] |

### Routed Production-Style Scores

| Ablation | Rows | Auto AI Rows | Auto AI TP | Auto AI FP | Auto AI Precision | Review Rows | Review Rate | Auto NON_AI Rows | Auto NON_AI Precision | True AI To Review | True NON_AI To Review |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1_title_abstract | 500 | 152 | 151 | 1 | 0.9934 | 155 | 0.3100 | 193 | 0.4041 | 127 | 28 |
| A2_title_abstract_keywords | 500 | 155 | 154 | 1 | 0.9935 | 160 | 0.3200 | 185 | 0.4108 | 130 | 30 |
| A4_all_current_fields | 500 | 170 | 166 | 4 | 0.9765 | 231 | 0.4620 | 99 | 0.4444 | 172 | 59 |
| A3_title_abstract_keywords_primary_topic | 500 | 156 | 156 | 0 | 1.0000 | 195 | 0.3900 | 149 | 0.3960 | 147 | 48 |

### Final A1 vs A2 Decision

Based only on the saved scores, the final project-wide choice is **A1**.
A2 has slightly higher raw AI precision and a negligible 0.0001 routed Auto-AI
precision edge, but both A1 and A2 have the same routed Auto-AI false positives
(`1`). A1 has better accuracy, better macro F1, better AI recall, and lower
review workload.

| Decision Factor | A1 | A2 | Winner |
| --- | ---: | ---: | --- |
| Accuracy | 0.7120 | 0.6940 | A1 |
| Macro F1 | 0.6571 | 0.6502 | A1 |
| AI precision | 0.9055 | 0.9225 | A2 |
| AI recall | 0.7074 | 0.6667 | A1 |
| Auto-AI precision | 0.9934 | 0.9935 | Tie / negligible A2 edge |
| Auto-AI false positives | 1 | 1 | Tie |
| Review rows | 155 | 160 | A1 |

Therefore A1 is the most suitable overall model for the project score balance.

## XGBoost Human-Selection Run

Created at: `2026-09-25T11:58:21.729019+00:00`

| Row Set | Rows |
| --- | --- |
| training | 5134 |
| human_train | 448 |
| human_validation | 193 |
| frozen_human_test | 500 |

| Selected Model | Human Weight | Threshold | Model SHA256 |
| --- | --- | --- | --- |
| xgboost | 3.0000 | 0.4900 | 71cfed983145e6965c540dddb2d4f11746c0ecd3b196f55b67842e30aabcaf0a |

| Run | Split | Model Family | Human Weight | Threshold | Accuracy | Macro F1 | Weighted F1 | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| XGBoost Human-Selection Run | Validation | xgboost | 3.0000 | 0.4900 | 0.7720 | 0.6652 | 0.7701 | [[129, 21], [23, 20]] |
| XGBoost Human-Selection Run | Frozen Test | xgboost | 3.0000 | 0.4900 | 0.7560 | 0.6576 | 0.7626 | [[323, 70], [52, 55]] |

| Split | Class | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- | --- |
| Validation | AI | 0.8487 | 0.8600 | 0.8543 | 150.0000 |
| Validation | NON_AI | 0.4878 | 0.4651 | 0.4762 | 43.0000 |
| Validation | macro avg | 0.6682 | 0.6626 | 0.6652 | 193.0000 |
| Validation | weighted avg | 0.7683 | 0.7720 | 0.7701 | 193.0000 |
| Frozen Test | AI | 0.8613 | 0.8219 | 0.8411 | 393.0000 |
| Frozen Test | NON_AI | 0.4400 | 0.5140 | 0.4741 | 107.0000 |
| Frozen Test | macro avg | 0.6507 | 0.6680 | 0.6576 | 500.0000 |
| Frozen Test | weighted avg | 0.7712 | 0.7560 | 0.7626 | 500.0000 |

### Full Validation Leaderboard

| model_family | human_weight | threshold | validation_accuracy | validation_macro_f1 | validation_ai_precision | validation_ai_recall | validation_non_ai_recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| xgboost | 3.0000 | 0.4900 | 0.7720 | 0.6652 | 0.8487 | 0.8600 | 0.4651 |
| xgboost | 5.0000 | 0.4300 | 0.7824 | 0.6415 | 0.8293 | 0.9067 | 0.3488 |
| xgboost | 2.0000 | 0.2600 | 0.8083 | 0.6398 | 0.8229 | 0.9600 | 0.2791 |
| xgboost | 1.0000 | 0.4700 | 0.7513 | 0.6348 | 0.8355 | 0.8467 | 0.4186 |

## Sklearn Human-Selection Run

Created at: `2026-09-25T09:47:59.723226+00:00`

| Row Set | Rows |
| --- | --- |
| training | 5134 |
| human_train | 448 |
| human_validation | 193 |
| frozen_human_test | 500 |

| Selected Model | Human Weight | Threshold | Model SHA256 |
| --- | --- | --- | --- |
| sgd_classifier | 3.0000 | 0.5800 | bce5483363a0549fcbea807c2a1f2ced4a25e665d811db04b0726bdbaaa2179c |

| Run | Split | Model Family | Human Weight | Threshold | Accuracy | Macro F1 | Weighted F1 | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sklearn Human-Selection Run | Validation | sgd_classifier | 3.0000 | 0.5800 | 0.7306 | 0.6730 | 0.7491 | [[111, 39], [13, 30]] |
| Sklearn Human-Selection Run | Frozen Test | sgd_classifier | 3.0000 | 0.5800 | 0.6620 | 0.6057 | 0.6879 | [[260, 128], [41, 71]] |

| Split | Class | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- | --- |
| Validation | AI | 0.8952 | 0.7400 | 0.8102 | 150.0000 |
| Validation | NON_AI | 0.4348 | 0.6977 | 0.5357 | 43.0000 |
| Validation | macro avg | 0.6650 | 0.7188 | 0.6730 | 193.0000 |
| Validation | weighted avg | 0.7926 | 0.7306 | 0.7491 | 193.0000 |
| Frozen Test | AI | 0.8638 | 0.6701 | 0.7547 | 388.0000 |
| Frozen Test | NON_AI | 0.3568 | 0.6339 | 0.4566 | 112.0000 |
| Frozen Test | macro avg | 0.6103 | 0.6520 | 0.6057 | 500.0000 |
| Frozen Test | weighted avg | 0.7502 | 0.6620 | 0.6879 | 500.0000 |

### Full Validation Leaderboard

| model_family | human_weight | threshold | validation_accuracy | validation_macro_f1 | validation_ai_precision | validation_ai_recall | validation_non_ai_recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sgd_classifier | 3.0000 | 0.5800 | 0.7306 | 0.6730 | 0.8952 | 0.7400 | 0.6977 |
| sgd_classifier | 5.0000 | 0.6000 | 0.7150 | 0.6659 | 0.9060 | 0.7067 | 0.7442 |
| sgd_classifier | 2.0000 | 0.5700 | 0.7306 | 0.6535 | 0.8657 | 0.7733 | 0.5814 |
| linear_svm | 2.0000 | 0.5700 | 0.7098 | 0.6440 | 0.8730 | 0.7333 | 0.6279 |
| logistic_regression | 3.0000 | 0.5400 | 0.7617 | 0.6439 | 0.8377 | 0.8600 | 0.4186 |
| logistic_regression | 5.0000 | 0.5400 | 0.7617 | 0.6439 | 0.8377 | 0.8600 | 0.4186 |
| linear_svm | 1.0000 | 0.5700 | 0.7047 | 0.6434 | 0.8780 | 0.7200 | 0.6512 |
| logistic_regression | 1.0000 | 0.4800 | 0.7668 | 0.6419 | 0.8344 | 0.8733 | 0.3953 |
| ridge_classifier | 3.0000 | 0.5100 | 0.7668 | 0.6419 | 0.8344 | 0.8733 | 0.3953 |
| logistic_regression | 2.0000 | 0.5100 | 0.7617 | 0.6373 | 0.8333 | 0.8667 | 0.3953 |
| ridge_classifier | 5.0000 | 0.5100 | 0.7617 | 0.6373 | 0.8333 | 0.8667 | 0.3953 |
| linear_svm | 3.0000 | 0.5800 | 0.6995 | 0.6313 | 0.8651 | 0.7267 | 0.6047 |
| linear_svm | 5.0000 | 0.5800 | 0.6995 | 0.6313 | 0.8651 | 0.7267 | 0.6047 |
| ridge_classifier | 2.0000 | 0.5300 | 0.7254 | 0.6246 | 0.8392 | 0.8000 | 0.4651 |
| ridge_classifier | 1.0000 | 0.5000 | 0.7617 | 0.6232 | 0.8250 | 0.8800 | 0.3488 |
| sgd_classifier | 1.0000 | 0.5600 | 0.7202 | 0.6147 | 0.8333 | 0.8000 | 0.4419 |
| multinomial_nb | 1.0000 | 0.7100 | 0.7047 | 0.5700 | 0.8079 | 0.8133 | 0.3256 |
| multinomial_nb | 2.0000 | 0.7300 | 0.7047 | 0.5700 | 0.8079 | 0.8133 | 0.3256 |
| multinomial_nb | 3.0000 | 0.8500 | 0.6528 | 0.5668 | 0.8217 | 0.7067 | 0.4651 |
| multinomial_nb | 5.0000 | 0.8200 | 0.6684 | 0.5624 | 0.8116 | 0.7467 | 0.3953 |

## Clean Human-Holdout Old vs New Run

Created at: `2026-09-25T08:27:19.824154+00:00`

| Human Pool Metric | Value |
| --- | --- |
| early_human_rows | 508 |
| late_human_rows | 770 |
| deduplicated_human_pool_rows | 1147 |
| hidden_test_rows | 500 |
| human_training_remainder_rows | 641 |
| hidden_test_label_counts | {'AI': 388, 'NON_AI': 112} |

| Model | Training Rows | Label Counts | Source Counts | Best C | CV Macro F1 | Human Test Accuracy | Human Test Macro F1 | Human Test Weighted F1 | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Old Original-LLM Model | 4361 | {'NON_AI': 2903, 'AI': 1458} | {'original_llm_5k': 4361} | 10.0000 | 0.9338 | 0.7300 | 0.5917 | 0.7229 | [[328, 60], [75, 37]] |
| New Human-Reviewed Model | 5327 | {'NON_AI': 3070, 'AI': 2257} | {'original_llm_5k': 3886, 'gemini_finished_1000': 856, 'late_human_800': 375, 'early_human_500': 210} | 1.0000 | 0.9156 | 0.7500 | 0.6346 | 0.7479 | [[328, 60], [65, 47]] |

| Model | Class | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- | --- |
| Old Original-LLM Model | AI | 0.8139 | 0.8454 | 0.8293 | 388.0000 |
| Old Original-LLM Model | NON_AI | 0.3814 | 0.3304 | 0.3541 | 112.0000 |
| Old Original-LLM Model | macro avg | 0.5977 | 0.5879 | 0.5917 | 500.0000 |
| Old Original-LLM Model | weighted avg | 0.7170 | 0.7300 | 0.7229 | 500.0000 |
| New Human-Reviewed Model | AI | 0.8346 | 0.8454 | 0.8399 | 388.0000 |
| New Human-Reviewed Model | NON_AI | 0.4393 | 0.4196 | 0.4292 | 112.0000 |
| New Human-Reviewed Model | macro avg | 0.6369 | 0.6325 | 0.6346 | 500.0000 |
| New Human-Reviewed Model | weighted avg | 0.7460 | 0.7500 | 0.7479 | 500.0000 |

## Updated Linear SVM With Finished Reviews

Created at: `2026-09-25T03:38:14.690303+00:00`

| Input Count | Value |
| --- | --- |
| original_binary_rows | 4437 |
| gemini_binary_rows | 889 |
| manual_binary_rows | 770 |
| updated_training_rows_after_dedup | 5671 |
| train_rows | 4536 |
| test_rows | 1135 |
| remaining_predicted_rows | 1207 |

| Model | Best C | Best CV Macro F1 | Same-Split Accuracy | Same-Split Macro F1 | Same-Split Weighted F1 | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- |
| Old Linear SVM |  |  | 0.9630 | 0.9626 | 0.9630 | [[485, 16], [26, 608]] |
| Updated Linear SVM | 1.0000 | 0.9047 | 0.9181 | 0.9171 | 0.9181 | [[460, 41], [52, 582]] |

| Model | Class | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- | --- |
| Old Linear SVM | AI | 0.9491 | 0.9681 | 0.9585 | 501.0000 |
| Old Linear SVM | NON_AI | 0.9744 | 0.9590 | 0.9666 | 634.0000 |
| Old Linear SVM | macro avg | 0.9617 | 0.9635 | 0.9626 | 1135.0000 |
| Old Linear SVM | weighted avg | 0.9632 | 0.9630 | 0.9630 | 1135.0000 |
| Updated Linear SVM | AI | 0.8984 | 0.9182 | 0.9082 | 501.0000 |
| Updated Linear SVM | NON_AI | 0.9342 | 0.9180 | 0.9260 | 634.0000 |
| Updated Linear SVM | macro avg | 0.9163 | 0.9181 | 0.9171 | 1135.0000 |
| Updated Linear SVM | weighted avg | 0.9184 | 0.9181 | 0.9181 | 1135.0000 |

### Same-Split Metrics By Label Source

| Label Source | Model | Rows | Accuracy | Macro F1 | Weighted F1 | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- |
| gemini_finished_1000 | old_model | 185 | 0.9622 | 0.4904 | 0.9436 | [[178, 0], [7, 0]] |
| gemini_finished_1000 | new_model | 185 | 0.9081 | 0.4759 | 0.9158 | [[168, 10], [7, 0]] |
| human_finished_800 | old_model | 119 | 0.7059 | 0.6142 | 0.7011 | [[71, 16], [19, 13]] |
| human_finished_800 | new_model | 119 | 0.6807 | 0.5669 | 0.6695 | [[71, 16], [22, 10]] |
| original_llm_5k | old_model | 831 | 1.0000 | 1.0000 | 1.0000 | [[236, 0], [0, 595]] |
| original_llm_5k | new_model | 831 | 0.9543 | 0.9443 | 0.9545 | [[221, 15], [23, 572]] |
| finished_reviews_only | old_model | 304 | 0.8618 | 0.6523 | 0.8530 | [[249, 16], [26, 13]] |
| finished_reviews_only | new_model | 304 | 0.8191 | 0.5817 | 0.8160 | [[239, 26], [29, 10]] |

## Initial Linear SVM From 5K Gemini Labels

| Metric | Value |
| --- | --- |
| input_csv | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/processed/ai/ai_llm_5000_predictions_openrouter_gemini_3_8_flash.csv |
| label_column | ai_llm_label |
| status_column | ai_llm_status |
| labels_used | AI, NON_AI |
| text_columns | title, abstract, keywords, topics, concepts, primary_topic, primary_subfield, primary_field, primary_domain |
| input_rows | 5000 |
| usable_rows | 4437 |
| train_rows | 3549 |
| test_rows | 888 |
| class_count | 2 |
| best_C | 10.0 |
| cv_macro_f1 | 0.9291 |
| accuracy | 0.9595 |
| macro_f1 | 0.9552 |
| weighted_f1 | 0.9595 |

```text
precision    recall  f1-score   support

          AI       0.94      0.94      0.94       307
      NON_AI       0.97      0.97      0.97       581

    accuracy                           0.96       888
   macro avg       0.96      0.96      0.96       888
weighted avg       0.96      0.96      0.96       888
```

## Earlier Model Selection Run

| Field | Value |
| --- | --- |
| best_model_name | logreg_word12_C10.0 |
| best_vectorizer | word_1_2 |
| selection_metric | validation_macro_f1 |
| train_rows | 3105 |
| validation_rows | 666 |
| test_rows | 666 |
| final_train_plus_validation_rows | 3771 |
| review_confidence_threshold_for_rest_predictions | 0.6000 |

### Best Model Test Metrics

| Metric | Value |
| --- | --- |
| accuracy | 0.9580 |
| macro_f1 | 0.9534 |
| weighted_f1 | 0.9579 |
| ai_precision | 0.9430 |
| ai_recall | 0.9348 |
| ai_f1 | 0.9389 |
| non_ai_precision | 0.9658 |
| non_ai_recall | 0.9702 |
| non_ai_f1 | 0.9680 |

### Validation Leaderboard Top Models

| model_name | vectorizer | accuracy | macro_f1 | weighted_f1 | ai_precision | ai_recall | ai_f1 | non_ai_precision | non_ai_recall | non_ai_f1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| logreg_word12_C10.0 | word_1_2 | 0.9580 | 0.9539 | 0.9581 | 0.9283 | 0.9524 | 0.9402 | 0.9744 | 0.9609 | 0.9676 |
| sgd_logloss_word13_alpha1e-05 | word_1_3 | 0.9520 | 0.9473 | 0.9521 | 0.9198 | 0.9437 | 0.9316 | 0.9697 | 0.9563 | 0.9630 |
| logreg_word12_C1.0 | word_1_2 | 0.9520 | 0.9472 | 0.9520 | 0.9234 | 0.9394 | 0.9313 | 0.9675 | 0.9586 | 0.9630 |
| linearsvc_word13_C10.0 | word_1_3 | 0.9505 | 0.9457 | 0.9506 | 0.9160 | 0.9437 | 0.9296 | 0.9696 | 0.9540 | 0.9618 |
| logreg_word12_C3.0 | word_1_2 | 0.9505 | 0.9456 | 0.9506 | 0.9195 | 0.9394 | 0.9293 | 0.9674 | 0.9563 | 0.9618 |
| linearsvc_charwb35_C1.0 | char_wb_3_5 | 0.9505 | 0.9454 | 0.9505 | 0.9267 | 0.9307 | 0.9287 | 0.9631 | 0.9609 | 0.9620 |
| linearsvc_word13_C3.0 | word_1_3 | 0.9489 | 0.9441 | 0.9491 | 0.9121 | 0.9437 | 0.9277 | 0.9696 | 0.9517 | 0.9606 |
| sgd_logloss_word13_alpha0.0001 | word_1_3 | 0.9489 | 0.9441 | 0.9491 | 0.9121 | 0.9437 | 0.9277 | 0.9696 | 0.9517 | 0.9606 |
| linearsvc_charwb35_C3.0 | char_wb_3_5 | 0.9489 | 0.9435 | 0.9489 | 0.9301 | 0.9221 | 0.9261 | 0.9588 | 0.9632 | 0.9610 |
| linearsvc_word13_C1.0 | word_1_3 | 0.9474 | 0.9424 | 0.9476 | 0.9118 | 0.9394 | 0.9254 | 0.9673 | 0.9517 | 0.9594 |

## Older XGBoost Metadata Ablation: macro-F1 objective

Created at: `2026-09-25T11:59:57.924582+00:00`

| Ablation | Columns | Threshold | Val Macro F1 | Val AI Precision | Test Accuracy | Test Macro F1 | Test AI Precision | Test AI Recall | Test NON_AI Recall | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A2_title_abstract_keywords | title, abstract, keywords | 0.3500 | 0.7104 |  | 0.7320 | 0.6601 | 0.8843 | 0.7583 | 0.6355 | [[298, 95], [39, 68]] |
| A1_title_abstract | title, abstract | 0.4000 | 0.7089 |  | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 | [[278, 115], [29, 78]] |
| A4_all_current_fields | title, abstract, keywords, topics, concepts, primary_topic, primary_subfield, primary_field, primary_domain | 0.3800 | 0.6684 |  | 0.7640 | 0.6340 | 0.8395 | 0.8651 | 0.3925 | [[340, 53], [65, 42]] |
| A3_title_abstract_keywords_primary_topic | title, abstract, keywords, primary_topic | 0.3100 | 0.7003 |  | 0.7400 | 0.6261 | 0.8433 | 0.8219 | 0.4393 | [[323, 70], [60, 47]] |

## Older XGBoost Metadata Ablation: AI-precision objective

Created at: `2026-09-28T09:03:07.022064+00:00`

| Ablation | Columns | Threshold | Val Macro F1 | Val AI Precision | Test Accuracy | Test Macro F1 | Test AI Precision | Test AI Recall | Test NON_AI Recall | Confusion Matrix AI/NON_AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A2_title_abstract_keywords | title, abstract, keywords | 0.3500 | 0.7104 | 0.9015 | 0.7320 | 0.6601 | 0.8843 | 0.7583 | 0.6355 | [[298, 95], [39, 68]] |
| A1_title_abstract | title, abstract | 0.4000 | 0.7089 | 0.9256 | 0.7120 | 0.6571 | 0.9055 | 0.7074 | 0.7290 | [[278, 115], [29, 78]] |
| A4_all_current_fields | title, abstract, keywords, topics, concepts, primary_topic, primary_subfield, primary_field, primary_domain | 0.8100 | 0.5858 | 0.9121 | 0.6220 | 0.5852 | 0.8984 | 0.5852 | 0.7570 | [[230, 163], [26, 81]] |
| A3_title_abstract_keywords_primary_topic | title, abstract, keywords, primary_topic | 0.8600 | 0.5593 | 0.9589 | 0.5660 | 0.5549 | 0.9731 | 0.4606 | 0.9533 | [[181, 212], [5, 102]] |

## Clean Holdout Model Comparison

| model_family | best_cv_macro_f1 | human_test_accuracy | human_test_macro_f1 | human_test_weighted_f1 | ai_precision | ai_recall | ai_f1 | non_ai_precision | non_ai_recall | non_ai_f1 | best_params | model_path | predictions_path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xgboost | 0.9130 | 0.7220 | 0.6414 | 0.7353 | 0.8567 | 0.7706 | 0.8114 | 0.4106 | 0.5536 | 0.4715 | {"clf__learning_rate": 0.1, "clf__max_depth": 3, "clf__n_estimators": 200} | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/xgboost.joblib | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/xgboost_human_test_predictions.csv |
| linear_svm | 0.9156 | 0.7500 | 0.6346 | 0.7479 | 0.8346 | 0.8454 | 0.8399 | 0.4393 | 0.4196 | 0.4292 | {"clf__C": 1.0} | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/linear_svm.joblib | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/linear_svm_human_test_predictions.csv |
| logistic_regression | 0.9127 | 0.7440 | 0.6221 | 0.7406 | 0.8283 | 0.8454 | 0.8367 | 0.4231 | 0.3929 | 0.4074 | {"clf__C": 10.0} | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/logistic_regression.joblib | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/logistic_regression_human_test_predictions.csv |
| ridge_classifier | 0.9118 | 0.7380 | 0.6119 | 0.7340 | 0.8237 | 0.8428 | 0.8331 | 0.4078 | 0.3750 | 0.3907 | {"clf__alpha": 1.0} | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/ridge_classifier.joblib | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/ridge_classifier_human_test_predictions.csv |
| sgd_classifier | 0.9138 | 0.7420 | 0.6071 | 0.7342 | 0.8198 | 0.8557 | 0.8373 | 0.4105 | 0.3482 | 0.3768 | {"clf__alpha": 0.0001} | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/sgd_classifier.joblib | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/sgd_classifier_human_test_predictions.csv |
| multinomial_nb | 0.8635 | 0.7040 | 0.5659 | 0.7011 | 0.8046 | 0.8170 | 0.8107 | 0.3302 | 0.3125 | 0.3211 | {"clf__alpha": 0.5} | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/multinomial_nb.joblib | /home/anusankrishnathas/Desktop/researchlanka-ai/researchlanka-ai/backend/data/models/ai_relevance/clean_human_holdout/model_comparison/multinomial_nb_human_test_predictions.csv |

## Clean Holdout Tuned Standard Model Comparison

| model_family | best_cv_macro_f1 | human_test_accuracy | human_test_macro_f1 | human_test_weighted_f1 | ai_precision | ai_recall | ai_f1 | non_ai_precision | non_ai_recall | non_ai_f1 | best_params | model_path | predictions_path | best_threshold | threshold_tuned_macro_f1 | threshold_tuned_accuracy | threshold_tuned_ai_precision | threshold_tuned_non_ai_recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xgboost | 0.9130 | 0.7220 | 0.6414 | 0.7353 | 0.8567 | 0.7706 | 0.8114 | 0.4106 | 0.5536 | 0.4715 | {"clf__learning_rate": 0.1, "clf__max_depth": 3, "clf__n_estimators": 200} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/xgboost.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/xgboost_human_test_predictions.csv | 0.4100 | 0.6576 | 0.7560 | 0.8500 | 0.4911 |
| linear_svm | 0.9156 | 0.7500 | 0.6346 | 0.7479 | 0.8346 | 0.8454 | 0.8399 | 0.4393 | 0.4196 | 0.4292 | {"clf__C": 1.0} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/linear_svm.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/linear_svm_human_test_predictions.csv | 0.5000 | 0.6346 | 0.7500 | 0.8346 | 0.4196 |
| logistic_regression | 0.9127 | 0.7440 | 0.6221 | 0.7406 | 0.8283 | 0.8454 | 0.8367 | 0.4231 | 0.3929 | 0.4074 | {"clf__C": 10.0} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/logistic_regression.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/logistic_regression_human_test_predictions.csv | 0.6100 | 0.6364 | 0.7140 | 0.8571 | 0.5625 |
| ridge_classifier | 0.9118 | 0.7380 | 0.6119 | 0.7340 | 0.8237 | 0.8428 | 0.8331 | 0.4078 | 0.3750 | 0.3907 | {"clf__alpha": 1.0} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/ridge_classifier.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/ridge_classifier_human_test_predictions.csv | 0.4900 | 0.6233 | 0.7580 | 0.8248 | 0.3571 |
| sgd_classifier | 0.9138 | 0.7420 | 0.6071 | 0.7342 | 0.8198 | 0.8557 | 0.8373 | 0.4105 | 0.3482 | 0.3768 | {"clf__alpha": 0.0001} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/sgd_classifier.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/sgd_classifier_human_test_predictions.csv | 0.5200 | 0.6324 | 0.7420 | 0.8364 | 0.4375 |
| multinomial_nb | 0.8635 | 0.7040 | 0.5659 | 0.7011 | 0.8046 | 0.8170 | 0.8107 | 0.3302 | 0.3125 | 0.3211 | {"clf__alpha": 0.5} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/multinomial_nb.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_standard/multinomial_nb_human_test_predictions.csv | 0.4200 | 0.5781 | 0.7320 | 0.8068 | 0.2857 |

## Clean Holdout Tuned Wide Sklearn Model Comparison

| model_family | best_cv_macro_f1 | human_test_accuracy | human_test_macro_f1 | human_test_weighted_f1 | ai_precision | ai_recall | ai_f1 | non_ai_precision | non_ai_recall | non_ai_f1 | best_params | model_path | predictions_path | best_threshold | threshold_tuned_macro_f1 | threshold_tuned_accuracy | threshold_tuned_ai_precision | threshold_tuned_non_ai_recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| linear_svm | 0.9173 | 0.7700 | 0.6570 | 0.7657 | 0.8421 | 0.8660 | 0.8539 | 0.4851 | 0.4375 | 0.4601 | {"clf__C": 3.0, "tfidf__max_df": 0.9, "tfidf__min_df": 1, "tfidf__ngram_range": [1, 2], "tfidf__sublinear_tf": true} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/linear_svm.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/linear_svm_human_test_predictions.csv | 0.5000 | 0.6570 | 0.7700 | 0.8421 | 0.4375 |
| logistic_regression | 0.9142 | 0.7640 | 0.6444 | 0.7582 | 0.8358 | 0.8660 | 0.8506 | 0.4694 | 0.4107 | 0.4381 | {"clf__C": 10.0, "tfidf__max_df": 0.95, "tfidf__min_df": 2, "tfidf__ngram_range": [1, 2], "tfidf__sublinear_tf": true} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/logistic_regression.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/logistic_regression_human_test_predictions.csv | 0.5300 | 0.6548 | 0.7600 | 0.8454 | 0.4643 |
| sgd_classifier | 0.9169 | 0.7620 | 0.6349 | 0.7538 | 0.8305 | 0.8711 | 0.8503 | 0.4624 | 0.3839 | 0.4195 | {"clf__alpha": 0.0003, "tfidf__max_df": 0.95, "tfidf__min_df": 2, "tfidf__ngram_range": [1, 3], "tfidf__sublinear_tf": true} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/sgd_classifier.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/sgd_classifier_human_test_predictions.csv | 0.5200 | 0.6486 | 0.7580 | 0.8414 | 0.4464 |
| ridge_classifier | 0.9127 | 0.7440 | 0.6246 | 0.7415 | 0.8299 | 0.8428 | 0.8363 | 0.4245 | 0.4018 | 0.4128 | {"clf__alpha": 0.3, "tfidf__max_df": 0.9, "tfidf__min_df": 1, "tfidf__ngram_range": [1, 3], "tfidf__sublinear_tf": true} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/ridge_classifier.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/ridge_classifier_human_test_predictions.csv | 0.5000 | 0.6246 | 0.7440 | 0.8299 | 0.4018 |
| multinomial_nb | 0.8635 | 0.7040 | 0.5659 | 0.7011 | 0.8046 | 0.8170 | 0.8107 | 0.3302 | 0.3125 | 0.3211 | {"clf__alpha": 0.5, "tfidf__max_df": 0.9, "tfidf__min_df": 2, "tfidf__ngram_range": [1, 3], "tfidf__sublinear_tf": true} | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/multinomial_nb.joblib | backend/data/models/ai_relevance/clean_human_holdout/model_comparison_tuned_wide_sklearn/multinomial_nb_human_test_predictions.csv | 0.4200 | 0.5781 | 0.7320 | 0.8068 | 0.2857 |

## Source Artifacts

- `backend/configurations/ai_relevance_model_manifest.json`
- `backend/data/models/ai_relevance/metadata_ablation_precision_092/metadata_ablation_summary.json`
- `backend/data/models/ai_relevance/metadata_ablation_precision_092/metadata_ablation_comparison.csv`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/validated_human_selection_xgboost_fast/validated_selection_summary.json`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/validated_human_selection_xgboost_fast/validation_selection_leaderboard.csv`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/validated_human_selection/validated_selection_summary.json`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/validated_human_selection/validation_selection_leaderboard.csv`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/clean_human_holdout/clean_human_holdout_summary.json`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/updated_with_reviews/updated_model_comparison_summary.json`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/ai_relevance_linear_svm_metrics.txt`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/model_selection/best_model_summary.json`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/metadata_ablation/metadata_ablation_summary.json`
- `backend/data/old_datasets_2026-09-30/backend/data/models/ai_relevance/old_artifacts_2026-09-30/metadata_ablation_precision/metadata_ablation_summary.json`
