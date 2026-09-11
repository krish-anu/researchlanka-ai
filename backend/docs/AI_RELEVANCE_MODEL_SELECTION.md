# AI Relevance Model Selection

The AI relevance model-selection run was executed from
`notebooks/kaggle_ai_relevance_svm_training.ipynb` using the locked
train/validation/test split generated from the 5k Gemini/OpenRouter-labelled
records.

## Split

- Train rows: 3,105
- Validation rows: 666
- Test rows: 666

Rows labelled `REVIEW` or failed by the LLM were not used for supervised
binary model training.

## Selected Model

- Model: `logreg_word12_C10.0`
- Vectorizer: word TF-IDF, n-grams 1-2
- Selection metric: validation macro F1
- Review threshold for rest-corpus predictions: 0.60

## Validation Result

- Accuracy: 0.95796
- Macro F1: 0.95388
- AI precision: 0.92827
- AI recall: 0.95238
- AI F1: 0.94017

## Test Result

- Accuracy: 0.95796
- Macro F1: 0.95341
- AI precision: 0.94298
- AI recall: 0.93478
- AI F1: 0.93886
- NON_AI precision: 0.96575
- NON_AI recall: 0.97018
- NON_AI F1: 0.96796

## Rest-Corpus Prediction

The final model was refit on train + validation rows, then applied to the
unlabelled/rest corpus after excluding the 5k labelled candidate rows.

- Full corpus rows: 41,063
- Excluded labelled rows: 5,000
- Predicted rest rows: 36,063
- Final AI: 2,210
- Final NON_AI: 33,432
- Final REVIEW: 421

`REVIEW` is assigned after prediction when model confidence is below 0.60.
The raw binary model label is preserved separately in the prediction CSV.

## Local Artifact Paths

Generated artifacts are intentionally stored under ignored data/model folders:

- `backend/data/models/ai_relevance/model_selection/best_ai_relevance_model.joblib`
- `backend/data/models/ai_relevance/model_selection/best_model_summary.json`
- `backend/data/models/ai_relevance/model_selection/model_validation_leaderboard.csv`
- `backend/data/models/ai_relevance/model_selection/best_model_test_confusion_matrix.csv`
- `backend/data/models/ai_relevance/model_selection/best_model_test_predictions.csv`
- `backend/data/processed/ai/ai_relevance_best_model_rest_predictions.csv`
- `backend/data/processed/ai/ai_relevance_best_model_rest_prediction_summary.json`
