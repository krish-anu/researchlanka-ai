#!/usr/bin/env python3
"""Select an AI relevance model with human validation, then test once.

This script is the stricter successor to the exploratory clean-holdout runs.

It uses:
- frozen test: clean_human_holdout/locked_human_test_set.csv
- human pool remainder: clean_human_holdout/human_training_remainder.csv
- machine labels: original 5k + finished Gemini 1000

The frozen human test is never used for model selection, threshold tuning, or
sample-weight tuning. Validation is split from the remaining human-labelled
rows and used for all selection.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, RidgeClassifier, SGDClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.artifacts import file_sha256  # noqa: E402
from src.modeling.linear_svm_training import combined_text  # noqa: E402
from src.preprocessing.text_cleaning import CUSTOM_STOP_WORDS  # noqa: E402


LABELS = ("AI", "NON_AI")
TEXT_COLUMNS = (
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
)
DEFAULT_CLEAN_DIR = PROJECT_ROOT / "data/models/ai_relevance/clean_human_holdout"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/models/ai_relevance/validated_human_selection"
DEFAULT_ORIGINAL_LABELS = (
    PROJECT_ROOT / "data/processed/ai/ai_llm_5000_predictions_openrouter_gemini_3_8_flash.csv"
)
DEFAULT_GEMINI_1000 = PROJECT_ROOT / "data/Finished/gemini_review_1000_openrouter_predictions.csv"


@dataclass(frozen=True)
class Config:
    clean_dir: Path = DEFAULT_CLEAN_DIR
    original_labels: Path = DEFAULT_ORIGINAL_LABELS
    gemini_1000: Path = DEFAULT_GEMINI_1000
    output_dir: Path = DEFAULT_OUTPUT_DIR
    validation_size: float = 0.30
    random_state: int = 42
    human_weights: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0)
    model_families: tuple[str, ...] = (
        "linear_svm",
        "logistic_regression",
        "ridge_classifier",
        "sgd_classifier",
        "multinomial_nb",
    )
    cv_folds: int = 3
    scoring: str = "f1_macro"
    include_xgboost: bool = False
    fast_xgboost: bool = False


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalize_label(value: Any) -> str:
    label = clean(value).upper().replace("-", "_").replace(" ", "_")
    return label if label in LABELS else ""


def norm_title(value: Any) -> str:
    return " ".join(clean(value).casefold().split())


def row_keys(record: pd.Series) -> set[str]:
    keys: set[str] = set()
    for column, prefix in (
        ("publication_id", "publication_id"),
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("source_record_id", "source_record_id"),
    ):
        value = clean(record.get(column, ""))
        if value:
            keys.add(f"{prefix}:{value.casefold()}")
    title = norm_title(record.get("title", ""))
    year = clean(record.get("publication_year", "")) or clean(record.get("publication_date", ""))[:4]
    if title:
        keys.add(f"title_year:{title}:{year}")
    record_key = clean(record.get("record_key", ""))
    if record_key:
        keys.add(record_key.casefold())
    return keys


def keyset(frame: pd.DataFrame) -> set[str]:
    keys: set[str] = set()
    for _, record in frame.iterrows():
        keys.update(row_keys(record))
    return keys


def canonical_key(record: pd.Series) -> str:
    keys = sorted(row_keys(record))
    return keys[0] if keys else ""


def prepare_text(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in TEXT_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    if "text" not in out.columns:
        out["text"] = combined_text(out.fillna(""), TEXT_COLUMNS)
    out["record_key"] = [canonical_key(record) for _, record in out.iterrows()]
    return out[out["text"].astype(str).str.strip() != ""].copy()


def remove_overlaps(frame: pd.DataFrame, forbidden: set[str]) -> pd.DataFrame:
    keep = [not bool(row_keys(record) & forbidden) for _, record in frame.iterrows()]
    return frame[keep].copy().reset_index(drop=True)


def load_llm_labels(path: Path, source: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["ai_llm_label"].map(normalize_label)
    frame = frame[
        (frame["ai_llm_status"].astype(str).str.strip() == "success")
        & frame["label"].isin(LABELS)
    ].copy()
    frame["label_source"] = source
    return prepare_text(frame)


def vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        strip_accents="unicode",
        lowercase=True,
        stop_words=CUSTOM_STOP_WORDS,
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.90,
        max_features=50_000,
        sublinear_tf=True,
    )


def candidate_specs(config: Config) -> dict[str, tuple[Any, dict[str, list[Any]]]]:
    specs: dict[str, tuple[Any, dict[str, list[Any]]]] = {
        "linear_svm": (
            LinearSVC(max_iter=5000, random_state=config.random_state, dual="auto"),
            {
                "clf__C": [0.3, 1.0, 3.0, 10.0],
                "clf__class_weight": ["balanced", None],
            },
        ),
        "logistic_regression": (
            LogisticRegression(max_iter=5000, solver="liblinear", random_state=config.random_state),
            {
                "clf__C": [0.3, 1.0, 3.0, 10.0],
                "clf__class_weight": ["balanced", None],
            },
        ),
        "ridge_classifier": (
            RidgeClassifier(random_state=config.random_state),
            {
                "clf__alpha": [0.1, 0.3, 1.0, 3.0],
                "clf__class_weight": ["balanced", None],
            },
        ),
        "sgd_classifier": (
            SGDClassifier(loss="hinge", max_iter=5000, random_state=config.random_state),
            {
                "clf__alpha": [0.00003, 0.0001, 0.0003, 0.001],
                "clf__class_weight": ["balanced", None],
            },
        ),
        "multinomial_nb": (
            MultinomialNB(),
            {"clf__alpha": [0.05, 0.1, 0.3, 0.5, 1.0]},
        ),
    }
    if config.include_xgboost:
        try:
            from xgboost import XGBClassifier
        except Exception as exc:
            raise RuntimeError("XGBoost requested but xgboost is not installed.") from exc
        xgb_grid = (
            {
                "clf__max_depth": [3],
                "clf__learning_rate": [0.1],
                "clf__n_estimators": [200],
                "clf__subsample": [1.0],
                "clf__colsample_bytree": [1.0],
            }
            if config.fast_xgboost
            else {
                "clf__max_depth": [2, 3],
                "clf__learning_rate": [0.05, 0.1],
                "clf__n_estimators": [100, 200],
                "clf__subsample": [0.8, 1.0],
                "clf__colsample_bytree": [0.8, 1.0],
            }
        )
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
    return {name: specs[name] for name in config.model_families if name in specs}


def sample_weights(frame: pd.DataFrame, human_weight: float) -> pd.Series:
    return frame["label_source"].astype(str).str.contains("human").map(
        {True: human_weight, False: 1.0}
    )


def fit_model(
    *,
    name: str,
    classifier: Any,
    param_grid: dict[str, list[Any]],
    train: pd.DataFrame,
    human_weight: float,
    config: Config,
) -> Pipeline:
    model = Pipeline([("tfidf", vectorizer()), ("clf", clone(classifier))])
    y = train["label"]
    if name == "xgboost":
        y = y.map({"NON_AI": 0, "AI": 1})
    cv_folds = min(config.cv_folds, int(train["label"].value_counts().min()))
    grid = GridSearchCV(
        model,
        param_grid=param_grid,
        cv=cv_folds,
        scoring=config.scoring,
        n_jobs=-1,
    )
    weights = sample_weights(train, human_weight)
    grid.fit(train["text"], y, clf__sample_weight=weights)
    return grid.best_estimator_


def raw_predict(name: str, model: Pipeline, text: pd.Series) -> list[str]:
    raw = model.predict(text)
    if name == "xgboost":
        return pd.Series(raw).map({0: "NON_AI", 1: "AI"}).tolist()
    return list(raw)


def ai_scores(name: str, model: Pipeline, text: pd.Series) -> list[float]:
    if name == "xgboost":
        probabilities = model.predict_proba(text)
        return [float(row[1]) for row in probabilities]
    classes = list(getattr(model, "classes_", ()))
    if "AI" not in classes:
        return [float("nan") for _ in range(len(text))]
    ai_index = classes.index("AI")
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(text)
        return [float(row[ai_index]) for row in probabilities]
    margins = model.decision_function(text)
    if getattr(margins, "ndim", 1) != 1:
        return [float(row[ai_index]) for row in margins]
    second = [1.0 / (1.0 + math.exp(-float(margin))) for margin in margins]
    return second if ai_index == 1 else [1.0 - score for score in second]


def threshold_predictions(scores: Iterable[float], threshold: float) -> list[str]:
    return ["AI" if float(score) >= threshold else "NON_AI" for score in scores]


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


def best_threshold(y_true: pd.Series, scores: Iterable[float]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for value in range(5, 96):
        threshold = round(value / 100, 2)
        metrics = evaluate(y_true, threshold_predictions(scores, threshold))
        row = {"threshold": threshold, "metrics": metrics}
        if best is None or metrics["macro_f1"] > best["metrics"]["macro_f1"]:
            best = row
    assert best is not None
    return best


def split_human_remainder(config: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    test = pd.read_csv(
        config.clean_dir / "locked_human_test_set.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    remainder = pd.read_csv(
        config.clean_dir / "human_training_remainder.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    for frame in (test, remainder):
        if "human_final_label" in frame.columns:
            frame["label"] = frame["human_final_label"].map(normalize_label)
        if "human_review_status" in frame.columns:
            frame.drop(
                frame[frame["human_review_status"].eq("AMBIGUOUS_REVIEW")].index,
                inplace=True,
            )
        frame.drop(frame[~frame["label"].isin(LABELS)].index, inplace=True)
    train_human, validation = train_test_split(
        prepare_text(remainder),
        test_size=config.validation_size,
        random_state=config.random_state,
        stratify=remainder["label"],
    )
    return prepare_text(test), train_human.reset_index(drop=True), validation.reset_index(drop=True)


def run(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    human_test, human_train, human_validation = split_human_remainder(config)
    forbidden = keyset(pd.concat([human_test, human_validation], ignore_index=True, sort=False))
    original = remove_overlaps(load_llm_labels(config.original_labels, "original_llm_5k"), forbidden)
    gemini = remove_overlaps(load_llm_labels(config.gemini_1000, "gemini_finished_1000"), forbidden)
    train = pd.concat([original, gemini, human_train], ignore_index=True, sort=False)
    train = train.drop_duplicates("record_key", keep="first") if "record_key" in train.columns else train
    train = prepare_text(train)

    human_test.to_csv(config.output_dir / "frozen_human_test_set.csv", index=False)
    human_validation.to_csv(config.output_dir / "human_validation_set.csv", index=False)
    human_train.to_csv(config.output_dir / "human_train_set.csv", index=False)
    train.to_csv(config.output_dir / "selection_training_dataset.csv", index=False)

    specs = candidate_specs(config)
    rows: list[dict[str, Any]] = []
    for name, (classifier, param_grid) in specs.items():
        for human_weight in config.human_weights:
            model = fit_model(
                name=name,
                classifier=classifier,
                param_grid=param_grid,
                train=train,
                human_weight=human_weight,
                config=config,
            )
            validation_scores = ai_scores(name, model, human_validation["text"])
            threshold_result = best_threshold(human_validation["label"], validation_scores)
            validation_pred = threshold_predictions(
                validation_scores, threshold_result["threshold"]
            )
            validation_metrics = evaluate(human_validation["label"], validation_pred)
            rows.append(
                {
                    "model_family": name,
                    "human_weight": human_weight,
                    "threshold": threshold_result["threshold"],
                    "validation_metrics": validation_metrics,
                    "model": model,
                }
            )

    selected = max(rows, key=lambda row: row["validation_metrics"]["macro_f1"])
    selected_model = selected["model"]
    selected_name = str(selected["model_family"])
    selected_threshold = float(selected["threshold"])

    test_scores = ai_scores(selected_name, selected_model, human_test["text"])
    test_pred = threshold_predictions(test_scores, selected_threshold)
    test_metrics = evaluate(human_test["label"], test_pred)

    model_path = config.output_dir / "selected_model.joblib"
    joblib.dump(selected_model, model_path)
    test_predictions = human_test[
        ["record_key", "label", "label_source", "title", "doi", "text"]
    ].copy()
    test_predictions["prediction"] = test_pred
    test_predictions["ai_score"] = [f"{score:.6f}" for score in test_scores]
    test_predictions["threshold"] = f"{selected_threshold:.2f}"
    test_predictions["correct"] = test_predictions["label"].eq(test_predictions["prediction"])
    test_predictions_path = config.output_dir / "selected_model_frozen_test_predictions.csv"
    test_predictions.to_csv(test_predictions_path, index=False)

    leaderboard = []
    for row in sorted(
        rows,
        key=lambda item: item["validation_metrics"]["macro_f1"],
        reverse=True,
    ):
        report = row["validation_metrics"]["classification_report"]
        leaderboard.append(
            {
                "model_family": row["model_family"],
                "human_weight": row["human_weight"],
                "threshold": row["threshold"],
                "validation_accuracy": row["validation_metrics"]["accuracy"],
                "validation_macro_f1": row["validation_metrics"]["macro_f1"],
                "validation_ai_precision": report["AI"]["precision"],
                "validation_ai_recall": report["AI"]["recall"],
                "validation_non_ai_recall": report["NON_AI"]["recall"],
            }
        )
    leaderboard_path = config.output_dir / "validation_selection_leaderboard.csv"
    pd.DataFrame(leaderboard).to_csv(leaderboard_path, index=False)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
        "rows": {
            "training": int(len(train)),
            "human_train": int(len(human_train)),
            "human_validation": int(len(human_validation)),
            "frozen_human_test": int(len(human_test)),
        },
        "label_counts": {
            "training": {k: int(v) for k, v in train["label"].value_counts().items()},
            "human_validation": {k: int(v) for k, v in human_validation["label"].value_counts().items()},
            "frozen_human_test": {k: int(v) for k, v in human_test["label"].value_counts().items()},
        },
        "selected": {
            "model_family": selected_name,
            "human_weight": selected["human_weight"],
            "threshold": selected_threshold,
            "validation_metrics": selected["validation_metrics"],
            "frozen_test_metrics": test_metrics,
            "model_path": str(model_path),
            "model_sha256": file_sha256(model_path),
            "test_predictions": str(test_predictions_path),
        },
        "artifacts": {
            "leaderboard": str(leaderboard_path),
            "human_train": str(config.output_dir / "human_train_set.csv"),
            "human_validation": str(config.output_dir / "human_validation_set.csv"),
            "frozen_human_test": str(config.output_dir / "frozen_human_test_set.csv"),
            "training_dataset": str(config.output_dir / "selection_training_dataset.csv"),
        },
    }
    summary_path = config.output_dir / "validated_selection_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metrics_path = config.output_dir / "validated_selection_metrics.txt"
    metrics_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def render_text(summary: dict[str, Any]) -> str:
    selected = summary["selected"]
    validation = selected["validation_metrics"]
    test = selected["frozen_test_metrics"]
    return "\n".join(
        [
            "Validated human-selection AI relevance model",
            "",
            f"training_rows: {summary['rows']['training']}",
            f"human_train_rows: {summary['rows']['human_train']}",
            f"human_validation_rows: {summary['rows']['human_validation']}",
            f"frozen_human_test_rows: {summary['rows']['frozen_human_test']}",
            "",
            f"selected_model_family: {selected['model_family']}",
            f"selected_human_weight: {selected['human_weight']}",
            f"selected_threshold: {selected['threshold']}",
            "",
            f"validation_accuracy: {validation['accuracy']:.4f}",
            f"validation_macro_f1: {validation['macro_f1']:.4f}",
            f"frozen_test_accuracy: {test['accuracy']:.4f}",
            f"frozen_test_macro_f1: {test['macro_f1']:.4f}",
            f"frozen_test_confusion_matrix_AI_NON_AI: {test['confusion_matrix']}",
            "",
            f"model_path: {selected['model_path']}",
            f"leaderboard: {summary['artifacts']['leaderboard']}",
        ]
    ) + "\n"


def parse_weights(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())


def parse_families(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-dir", type=Path, default=DEFAULT_CLEAN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--validation-size", type=float, default=0.30)
    parser.add_argument("--human-weights", type=parse_weights, default=(1.0, 2.0, 3.0, 5.0))
    parser.add_argument(
        "--model-families",
        type=parse_families,
        default=(
            "linear_svm",
            "logistic_regression",
            "ridge_classifier",
            "sgd_classifier",
            "multinomial_nb",
        ),
    )
    parser.add_argument("--include-xgboost", action="store_true")
    parser.add_argument("--fast-xgboost", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run(
        Config(
            clean_dir=args.clean_dir,
            output_dir=args.output_dir,
            validation_size=args.validation_size,
            human_weights=args.human_weights,
            model_families=args.model_families,
            include_xgboost=args.include_xgboost,
            fast_xgboost=args.fast_xgboost,
        )
    )
    print(render_text(summary), end="")


if __name__ == "__main__":
    main()
