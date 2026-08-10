# Model Evaluation and the Naive Bayes Baseline

One evaluation pipeline, shared by every model family, and a Multinomial Naive
Bayes baseline to measure against.

Code: [`src/modeling/evaluation.py`](../src/modeling/evaluation.py) (evaluation),
[`src/modeling/training.py`](../src/modeling/training.py) (training, both families).
Tests: [`tests/test_model_evaluation.py`](../tests/test_model_evaluation.py).

---

## 1. Why a shared pipeline

A baseline is only meaningful if the thing it is compared against was measured
the same way. Every training run — Logistic Regression or Naive Bayes — routes
its held-out predictions through `evaluate_predictions`, so the numbers, the
confusion matrix and the per-class results come out of one implementation and
the artifacts line up column for column.

The pipeline starts from either end:

- **a predictions CSV** a training run already wrote, or
- **a saved model plus a dataset** to score.

Both paths produce identical artifacts.

## 2. The Naive Bayes baseline

```bash
make train-nb PYTHON=python
# or
python -m src.modeling.training --model-family multinomial_nb
```

TF-IDF features into `MultinomialNB`. It is fast, has two knobs, and its errors
are easy to read off the confusion matrix, so a more expensive model has to
justify itself against these numbers.

| Setting | Applies to | Meaning |
|---|---|---|
| `--alpha` | NB | Additive smoothing. Default 1.0. |
| `--no-fit-prior` | NB | Uniform class prior instead of a learned one — the closest this family has to balanced class weighting. |
| `--class-weight` | Logistic Regression | Ignored by NB, and cleared from the config so it cannot appear in a manifest for a run that never used it. |
| `--max-iter` | Logistic Regression | NB is closed-form; there is nothing to iterate. |

TF-IDF keeps `sublinear_tf=True`, which stays non-negative — a requirement of
`MultinomialNB`. Both families therefore share the exact same feature stage, so
a difference in the results is a difference in the classifier.

Artifacts are named after the family, so runs never overwrite each other:
`multinomial_nb_primary_domain.joblib`, `logistic_regression_primary_domain.joblib`,
and so on.

## 3. Artifacts

Every training run writes, in `data/models/`:

| Artifact | Contents |
|---|---|
| `<family>_<label>.joblib` | The fitted pipeline. |
| `<family>_<label>_metrics.txt` | Headline metrics, the hyperparameters that applied, the class distribution, and the rendered evaluation. |
| `<family>_<label>_labels.csv` | Class distribution. |
| `<family>_<label>_predictions.csv` | Held-out predictions — the input to any later evaluation. |
| `<family>_<label>_confusion_matrix.csv` | See below. |
| `<family>_<label>_per_class.csv` | See below. |
| `<family>_<label>_manifest.json` | Config, results and a SHA-256 for every artifact above. |

### Confusion matrix

Wide form: one row per true label, one column per predicted label, plus that
row's support and accuracy.

```
true_label,support,correct,accuracy,computer science,agriculture,medicine
computer science,21,18,0.8571,18,1,2
agriculture,20,20,1.0,0,20,0
medicine,19,16,0.8421,2,1,16
```

Columns follow class frequency, so the classes that carry the corpus come first.
A class the model never predicts still gets a row and a column rather than
disappearing from the matrix.

### Per-class results

```
label,support,predicted,correct,precision,recall,f1,most_confused_with,most_confused_count
computer science,21,20,18,0.9,0.8571,0.878,medicine,2
agriculture,20,22,20,0.9091,1.0,0.9524,,0
medicine,19,18,16,0.8889,0.8421,0.8649,computer science,2
```

`most_confused_with` is what turns a low F1 into something actionable: it names
the class the label leaks into. `predicted` against `support` shows whether the
model over- or under-predicts a class.

## 4. Evaluating and comparing runs

```bash
make evaluate-models PYTHON=python

python -m src.modeling.evaluation \
  --predictions-csv data/models/multinomial_nb_primary_domain_predictions.csv \
  --predictions-csv data/models/logistic_regression_primary_domain_predictions.csv

python -m src.modeling.evaluation --model data/models/multinomial_nb_primary_domain.joblib \
  --input-csv data/processed/common/common_publications_final.csv
```

Each run gets `<run>_confusion_matrix.csv`, `<run>_per_class.csv` and
`<run>_evaluation.json`. Two or more runs also get `model_comparison.csv`, one
row each:

| Column | Meaning |
|---|---|
| `accuracy`, `weighted_f1` | Corpus-level performance, dominated by the large classes. |
| `balanced_accuracy`, `macro_precision`, `macro_recall`, `macro_f1` | Every class weighted equally — where an imbalanced corpus shows the truth. |
| `worst_class`, `worst_class_f1` | The class to look at first. |

Read the macro numbers next to the plain ones. On this corpus the class
distribution is heavily skewed, so accuracy alone rewards a model for learning
the majority class and little else.

## 5. Notes and limits

- The class order passed by training comes from the training label counts, so a
  class dropped by `--min-class-count` is absent from both the model and its
  matrix.
- `evaluate_model_file` scores whatever rows it is given. Pointing it at the
  training input scores rows the model has already seen; that measures fit, not
  generalization. Use the held-out predictions artifact for the real number.
- The evaluation is single-split. Cross-validated variance is not reported.

See also [PIPELINE_RUNBOOK.md](PIPELINE_RUNBOOK.md) for where these steps sit in
the pipeline.
