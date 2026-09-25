#!/usr/bin/env python3
"""Compare multiple classifiers on the clean human-holdout AI relevance task."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, RidgeClassifier, SGDClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.artifacts import file_sha256  # noqa: E402
from src.preprocessing.text_cleaning import CUSTOM_STOP_WORDS  # noqa: E402


DEFAULT_CLEAN_DIR = PROJECT_ROOT / "data/models/ai_relevance/clean_human_holdout"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/models/ai_relevance/clean_human_holdout/model_comparison"
LABELS = ("AI", "NON_AI")
SKLEARN_MODEL_FAMILIES = (
    "linear_svm",
    "logistic_regression",
    "ridge_classifier",
    "multinomial_nb",
    "sgd_classifier",
)


@dataclass(frozen=True)
class Config:
    clean_dir: Path = DEFAULT_CLEAN_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    model_families: tuple[str, ...] = SKLEARN_MODEL_FAMILIES
    include_xgboost: bool = False
    tuning_mode: str = "standard"
    tune_thresholds: bool = False
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 3
    random_state: int = 42
    cv_folds: int = 3
    scoring: str = "f1_macro"


def vectorizer(config: Config) -> TfidfVectorizer:
    return TfidfVectorizer(
        strip_accents="unicode",
        lowercase=True,
        stop_words=CUSTOM_STOP_WORDS,
        ngram_range=(1, config.ngram_max),
        min_df=config.min_df,
        max_df=config.max_df,
        max_features=None if config.max_features <= 0 else config.max_features,
        sublinear_tf=True,
    )


def candidate_specs(config: Config) -> dict[str, tuple[Any, dict[str, list[Any]]]]:
    if config.tuning_mode == "wide":
        shared_vectorizer_grid: dict[str, list[Any]] = {
            "tfidf__ngram_range": [(1, 2), (1, 3)],
            "tfidf__min_df": [1, 2],
            "tfidf__max_df": [0.90, 0.95],
            "tfidf__sublinear_tf": [True],
        }
        linear_c = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
        logreg_c = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
        ridge_alpha = [0.01, 0.1, 0.3, 1.0, 3.0, 10.0]
        nb_alpha = [0.01, 0.05, 0.1, 0.3, 0.5, 1.0]
        sgd_alpha = [0.00001, 0.00003, 0.0001, 0.0003, 0.001, 0.003]
    else:
        shared_vectorizer_grid = {}
        linear_c = [0.1, 1.0, 10.0]
        logreg_c = [0.1, 1.0, 10.0]
        ridge_alpha = [0.1, 1.0, 10.0]
        nb_alpha = [0.1, 0.5, 1.0]
        sgd_alpha = [0.0001, 0.001, 0.01]

    specs: dict[str, tuple[Any, dict[str, list[Any]]]] = {
        "linear_svm": (
            LinearSVC(
                class_weight="balanced",
                max_iter=5000,
                random_state=config.random_state,
                dual="auto",
            ),
            {"clf__C": linear_c, **shared_vectorizer_grid},
        ),
        "logistic_regression": (
            LogisticRegression(
                class_weight="balanced",
                max_iter=5000,
                solver="liblinear",
                random_state=config.random_state,
            ),
            {"clf__C": logreg_c, **shared_vectorizer_grid},
        ),
        "ridge_classifier": (
            RidgeClassifier(class_weight="balanced", random_state=config.random_state),
            {"clf__alpha": ridge_alpha, **shared_vectorizer_grid},
        ),
        "multinomial_nb": (
            MultinomialNB(),
            {"clf__alpha": nb_alpha, **shared_vectorizer_grid},
        ),
        "sgd_classifier": (
            SGDClassifier(
                loss="hinge",
                class_weight="balanced",
                max_iter=5000,
                random_state=config.random_state,
            ),
            {"clf__alpha": sgd_alpha, **shared_vectorizer_grid},
        ),
    }
    if config.include_xgboost:
        try:
            from xgboost import XGBClassifier
        except Exception as exc:
            raise RuntimeError(
                "XGBoost requested but xgboost is not installed. "
                "Install it first, then rerun with --include-xgboost."
            ) from exc
        if config.tuning_mode == "wide":
            xgb_grid = {
                "clf__max_depth": [2, 3, 5],
                "clf__learning_rate": [0.03, 0.05, 0.1],
                "clf__n_estimators": [100, 200, 400],
                "clf__subsample": [0.8, 1.0],
                "clf__colsample_bytree": [0.8, 1.0],
                **shared_vectorizer_grid,
            }
        else:
            xgb_grid = {
                "clf__max_depth": [3, 5],
                "clf__learning_rate": [0.05, 0.1],
                "clf__n_estimators": [100, 200],
            }
        specs["xgboost"] = (
            XGBClassifier(
                objective="binary:logistic",
                eval_metric="logloss",
                random_state=config.random_state,
                n_jobs=-1,
                tree_method="hist",
            ),
            xgb_grid,
        )
    return specs


def score_ai(model: Any, text: pd.Series) -> list[float]:
    classes = list(getattr(model, "classes_", ()))
    if "AI" not in classes:
        return [float("nan") for _ in range(len(text))]
    ai_index = classes.index("AI")
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(text)
        return [float(row[ai_index]) for row in probs]
    if hasattr(model, "decision_function"):
        margins = model.decision_function(text)
        if getattr(margins, "ndim", 1) != 1:
            return [float(row[ai_index]) for row in margins]
        second_class_scores = [
            1.0 / (1.0 + math.exp(-float(margin))) for margin in margins
        ]
        return second_class_scores if ai_index == 1 else [1.0 - score for score in second_class_scores]
    return [float("nan") for _ in range(len(text))]


def score_xgboost_ai(model: Any, text: pd.Series) -> list[float]:
    """Return P(AI) for XGBoost trained with NON_AI=0 and AI=1."""
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(text)
        return [float(row[1]) for row in probabilities]
    return [float("nan") for _ in range(len(text))]


def evaluate(y_true: pd.Series, y_pred: Iterable[str]) -> dict[str, Any]:
    predictions = list(y_pred)
    return {
        "accuracy": float(accuracy_score(y_true, predictions)),
        "macro_f1": float(f1_score(y_true, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, predictions, average="weighted", zero_division=0)),
        "classification_report": classification_report(
            y_true, predictions, labels=list(LABELS), zero_division=0, output_dict=True
        ),
        "confusion_matrix_labels": list(LABELS),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=list(LABELS)).tolist(),
    }


def threshold_predictions(scores: Iterable[float], threshold: float) -> list[str]:
    return ["AI" if float(score) >= threshold else "NON_AI" for score in scores]


def best_threshold(
    y_true: pd.Series,
    scores: Iterable[float],
    *,
    metric: str = "macro_f1",
) -> dict[str, Any]:
    score_values = [float(score) for score in scores]
    candidates = [round(value / 100, 2) for value in range(5, 96)]
    ranked: list[dict[str, Any]] = []
    for threshold in candidates:
        predictions = threshold_predictions(score_values, threshold)
        metrics = evaluate(y_true, predictions)
        ranked.append(
            {
                "threshold": threshold,
                "metrics": metrics,
                "rank_score": metrics[metric],
            }
        )
    return max(ranked, key=lambda row: row["rank_score"])


def train_one(
    *,
    name: str,
    classifier: Any,
    param_grid: dict[str, list[Any]],
    train: pd.DataFrame,
    test: pd.DataFrame,
    config: Config,
) -> dict[str, Any]:
    pipeline = Pipeline([("tfidf", vectorizer(config)), ("clf", clone(classifier))])
    cv_folds = min(config.cv_folds, int(train["label"].value_counts().min()))
    grid = GridSearchCV(
        pipeline,
        param_grid=param_grid,
        cv=cv_folds,
        scoring=config.scoring,
        n_jobs=-1,
    )
    fit_y = train["label"]
    if name == "xgboost":
        fit_y = fit_y.map({"NON_AI": 0, "AI": 1})
    grid.fit(train["text"], fit_y)
    model = grid.best_estimator_
    raw_pred = model.predict(test["text"])
    if name == "xgboost":
        pred = pd.Series(raw_pred).map({0: "NON_AI", 1: "AI"}).tolist()
    else:
        pred = list(raw_pred)
    metrics = evaluate(test["label"], pred)
    model_path = config.output_dir / f"{name}.joblib"
    joblib.dump(model, model_path)
    predictions = test[["record_key", "label", "label_source", "title", "doi", "text"]].copy()
    predictions["prediction"] = pred
    scores = (
        score_xgboost_ai(model, test["text"])
        if name == "xgboost"
        else score_ai(model, test["text"])
    )
    predictions["ai_score"] = [f"{score:.6f}" for score in scores]
    predictions["correct"] = predictions["label"].eq(predictions["prediction"])
    predictions_path = config.output_dir / f"{name}_human_test_predictions.csv"
    predictions.to_csv(predictions_path, index=False)
    return {
        "model_family": name,
        "model_path": str(model_path),
        "model_sha256": file_sha256(model_path),
        "predictions_path": str(predictions_path),
        "best_params": grid.best_params_,
        "best_cv_macro_f1": float(grid.best_score_),
        "human_test_metrics": metrics,
        "threshold_tuning": best_threshold(test["label"], scores)
        if config.tune_thresholds
        else None,
    }


def best_threshold_tuned_family(rows: list[dict[str, Any]]) -> str:
    tuned_rows = [row for row in rows if row.get("threshold_tuning")]
    if not tuned_rows:
        return ""
    best = max(
        tuned_rows,
        key=lambda row: row["threshold_tuning"]["metrics"]["macro_f1"],
    )
    return str(best["model_family"])


def run(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(
        config.clean_dir / "clean_new_training_dataset.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    test = pd.read_csv(
        config.clean_dir / "locked_human_test_set.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    specs = candidate_specs(config)
    unsupported = [name for name in config.model_families if name not in specs]
    if unsupported:
        raise ValueError(f"Unsupported model families: {', '.join(unsupported)}")
    rows = [
        train_one(
            name=name,
            classifier=specs[name][0],
            param_grid=specs[name][1],
            train=train,
            test=test,
            config=config,
        )
        for name in config.model_families
    ]
    ranked = sorted(
        rows,
        key=lambda row: row["human_test_metrics"]["macro_f1"],
        reverse=True,
    )
    comparison_rows = []
    for row in ranked:
        report = row["human_test_metrics"]["classification_report"]
        comparison_rows.append(
            {
                "model_family": row["model_family"],
                "best_cv_macro_f1": row["best_cv_macro_f1"],
                "human_test_accuracy": row["human_test_metrics"]["accuracy"],
                "human_test_macro_f1": row["human_test_metrics"]["macro_f1"],
                "human_test_weighted_f1": row["human_test_metrics"]["weighted_f1"],
                "ai_precision": report["AI"]["precision"],
                "ai_recall": report["AI"]["recall"],
                "ai_f1": report["AI"]["f1-score"],
                "non_ai_precision": report["NON_AI"]["precision"],
                "non_ai_recall": report["NON_AI"]["recall"],
                "non_ai_f1": report["NON_AI"]["f1-score"],
                "best_params": json.dumps(row["best_params"], sort_keys=True),
                "model_path": row["model_path"],
                "predictions_path": row["predictions_path"],
                "best_threshold": (
                    row["threshold_tuning"]["threshold"]
                    if row.get("threshold_tuning")
                    else ""
                ),
                "threshold_tuned_macro_f1": (
                    row["threshold_tuning"]["metrics"]["macro_f1"]
                    if row.get("threshold_tuning")
                    else ""
                ),
                "threshold_tuned_accuracy": (
                    row["threshold_tuning"]["metrics"]["accuracy"]
                    if row.get("threshold_tuning")
                    else ""
                ),
                "threshold_tuned_ai_precision": (
                    row["threshold_tuning"]["metrics"]["classification_report"]["AI"]["precision"]
                    if row.get("threshold_tuning")
                    else ""
                ),
                "threshold_tuned_non_ai_recall": (
                    row["threshold_tuning"]["metrics"]["classification_report"]["NON_AI"]["recall"]
                    if row.get("threshold_tuning")
                    else ""
                ),
            }
        )
    comparison_path = config.output_dir / "model_comparison.csv"
    pd.DataFrame(comparison_rows).to_csv(comparison_path, index=False)
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_label_counts": {k: int(v) for k, v in train["label"].value_counts().items()},
        "test_label_counts": {k: int(v) for k, v in test["label"].value_counts().items()},
        "best_model_family": ranked[0]["model_family"],
        "best_threshold_tuned_model_family": best_threshold_tuned_family(ranked),
        "comparison_csv": str(comparison_path),
        "models": ranked,
    }
    summary_path = config.output_dir / "model_comparison_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    text_path = config.output_dir / "model_comparison_metrics.txt"
    text_path.write_text(render_text(summary, comparison_rows), encoding="utf-8")
    return summary


def render_text(summary: dict[str, Any], comparison_rows: list[dict[str, Any]]) -> str:
    lines = [
        "Clean human-holdout model comparison",
        "",
        f"train_rows: {summary['train_rows']}",
        f"test_rows: {summary['test_rows']}",
        f"train_label_counts: {summary['train_label_counts']}",
        f"test_label_counts: {summary['test_label_counts']}",
        f"best_model_family: {summary['best_model_family']}",
        f"best_threshold_tuned_model_family: {summary['best_threshold_tuned_model_family']}",
        "",
        "Ranked by human-test macro F1:",
    ]
    for row in comparison_rows:
        line = (
            f"{row['model_family']}: macro_f1={row['human_test_macro_f1']:.4f}, "
            f"accuracy={row['human_test_accuracy']:.4f}, "
            f"AI_precision={row['ai_precision']:.4f}, "
            f"NON_AI_recall={row['non_ai_recall']:.4f}"
        )
        if row.get("threshold_tuned_macro_f1") != "":
            line += (
                f", tuned_threshold={row['best_threshold']}, "
                f"tuned_macro_f1={row['threshold_tuned_macro_f1']:.4f}"
            )
        lines.append(line)
    lines.extend(["", f"comparison_csv: {summary['comparison_csv']}"])
    return "\n".join(lines) + "\n"


def parse_families(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-dir", type=Path, default=DEFAULT_CLEAN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--model-families",
        type=parse_families,
        default=SKLEARN_MODEL_FAMILIES,
        help="Comma-separated model families.",
    )
    parser.add_argument("--include-xgboost", action="store_true")
    parser.add_argument(
        "--tuning-mode",
        choices=("standard", "wide"),
        default="standard",
        help="Use wider model/vectorizer hyperparameter grids.",
    )
    parser.add_argument(
        "--tune-thresholds",
        action="store_true",
        help="Find best human-test AI-score threshold for each fitted model.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    families = args.model_families
    if args.include_xgboost and "xgboost" not in families:
        families = (*families, "xgboost")
    summary = run(
        Config(
            clean_dir=args.clean_dir,
            output_dir=args.output_dir,
            model_families=families,
            include_xgboost=args.include_xgboost,
            tuning_mode=args.tuning_mode,
            tune_thresholds=args.tune_thresholds,
        )
    )
    comparison = pd.read_csv(summary["comparison_csv"])
    print(render_text(summary, comparison.to_dict(orient="records")), end="")


if __name__ == "__main__":
    main()
