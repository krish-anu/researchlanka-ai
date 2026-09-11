#!/usr/bin/env python3
"""Linear SVM hyperparameter comparison runner.

Sweeps:

    ngram_max:     1, 2, 3
    C:             0.1, 1, 10
    class_weight:  balanced, None

Selection metric: macro F1, since the publication taxonomy is class
imbalanced and macro F1 weights rare classes fairly.

Run via: scripts/modeling/compare_linear_svc_configs.py
"""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.linear_svc_evaluation import save_experiment_result
from src.modeling.hierarchical_linear_svm import combined_text

# ============================================================================
# CONFIG
# ============================================================================

INPUT_FILE = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "data" / "models" / "linear_svm" / "experiments"

TEXT_COLUMNS = ["title", "abstract", "topics", "keywords", "concepts"]
LABEL_COLUMN = "primary_field"

TEST_SIZE = 0.15
RANDOM_STATE = 42

NGRAM_VALUES = [1, 2, 3]
C_VALUES = [0.1, 1, 10]
CLASS_WEIGHTS = ["balanced", None]


# ============================================================================
# MODEL BUILDER
# ============================================================================


def build_model(
    *, ngram_max: int, c_value: float, class_weight: str | None
) -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    stop_words=None,
                    ngram_range=(1, ngram_max),
                    min_df=2,
                    max_df=0.95,
                    sublinear_tf=True,
                    max_features=50_000,
                ),
            ),
            (
                "svm",
                LinearSVC(
                    C=c_value,
                    class_weight=class_weight,
                    max_iter=5000,
                    random_state=RANDOM_STATE,
                    dual="auto",
                ),
            ),
        ]
    )


# ============================================================================
# DATA LOADING
# ============================================================================


def load_data() -> pd.DataFrame:
    frame = pd.read_csv(INPUT_FILE)
    frame = frame[frame[LABEL_COLUMN].notna()].copy()
    frame["text"] = combined_text(frame, TEXT_COLUMNS)
    frame = frame[frame["text"] != ""]
    return frame


# ============================================================================
# EXPERIMENT RUNNER
# ============================================================================


def run_experiments() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    frame = load_data()

    X_train, X_test, y_train, y_test = train_test_split(
        frame["text"],
        frame[LABEL_COLUMN],
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=frame[LABEL_COLUMN],
    )

    combinations = list(product(NGRAM_VALUES, C_VALUES, CLASS_WEIGHTS))
    results_path = OUTPUT_DIR / "linear_svm_experiment_results.csv"

    # Fresh run: start the results file clean rather than appending to a
    # stale one from a previous sweep.
    if results_path.exists():
        results_path.unlink()

    results = []
    for index, (ngram_max, c_value, class_weight) in enumerate(combinations, start=1):
        print(
            f"[{index}/{len(combinations)}] ngram={ngram_max}, C={c_value}, weight={class_weight}"
        )

        model = build_model(
            ngram_max=ngram_max, c_value=c_value, class_weight=class_weight
        )
        model.fit(X_train, y_train)
        predictions = model.predict(X_test)

        result = {
            "ngram_max": ngram_max,
            "C": c_value,
            "class_weight": str(class_weight),
            "accuracy": accuracy_score(y_test, predictions),
            "macro_f1": f1_score(y_test, predictions, average="macro", zero_division=0),
            "weighted_f1": f1_score(
                y_test, predictions, average="weighted", zero_division=0
            ),
        }
        results.append(result)
        save_experiment_result(result, output_path=results_path)

    results_df = pd.DataFrame(results).sort_values("macro_f1", ascending=False)
    best = results_df.iloc[0].to_dict()

    best_file = OUTPUT_DIR / "best_linear_svm_config.json"
    with open(best_file, "w", encoding="utf-8") as handle:
        json.dump(best, handle, indent=4)

    print("\nBest configuration:")
    print(best)
    print(f"\nSaved:\n{results_path}\n{best_file}")


if __name__ == "__main__":
    run_experiments()
