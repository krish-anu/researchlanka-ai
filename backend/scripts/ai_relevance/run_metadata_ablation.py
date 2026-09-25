#!/usr/bin/env python3
"""Run A1-A4 metadata ablation for AI relevance text features."""

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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.text_cleaning import CUSTOM_STOP_WORDS, clean_text_series  # noqa: E402


DEFAULT_SELECTION_DIR = PROJECT_ROOT / "data/models/ai_relevance/validated_human_selection_xgboost_fast"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/models/ai_relevance/metadata_ablation"
LABELS = ("AI", "NON_AI")
ABLATIONS: dict[str, tuple[str, ...]] = {
    "A1_title_abstract": ("title", "abstract"),
    "A2_title_abstract_keywords": ("title", "abstract", "keywords"),
    "A3_title_abstract_keywords_primary_topic": (
        "title",
        "abstract",
        "keywords",
        "primary_topic",
    ),
    "A4_all_current_fields": (
        "title",
        "abstract",
        "keywords",
        "topics",
        "concepts",
        "primary_topic",
        "primary_subfield",
        "primary_field",
        "primary_domain",
    ),
}


@dataclass(frozen=True)
class Config:
    selection_dir: Path = DEFAULT_SELECTION_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    human_weight: float = 3.0
    random_state: int = 42


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def prefixed_text(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    parts = []
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].fillna("").astype(str)
        parts.append(column.upper() + ": " + values)
    if not parts:
        return pd.Series("", index=frame.index)
    text = pd.concat(parts, axis=1).agg(" ".join, axis=1)
    text = text.str.replace(r"\s+", " ", regex=True).str.strip()
    return clean_text_series(text)


def sample_weights(frame: pd.DataFrame, human_weight: float) -> pd.Series:
    return frame["label_source"].astype(str).str.contains("human").map(
        {True: human_weight, False: 1.0}
    )


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


def xgboost_classifier(random_state: int) -> Any:
    from xgboost import XGBClassifier

    return XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
        n_jobs=-1,
        tree_method="hist",
        max_depth=3,
        learning_rate=0.1,
        n_estimators=200,
        subsample=1.0,
        colsample_bytree=1.0,
    )


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


def best_threshold(y_true: pd.Series, scores: Iterable[float]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for value in range(5, 96):
        threshold = round(value / 100, 2)
        metrics = evaluate(y_true, threshold_predictions(scores, threshold))
        if best is None or metrics["macro_f1"] > best["metrics"]["macro_f1"]:
            best = {"threshold": threshold, "metrics": metrics}
    assert best is not None
    return best


def run(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(
        config.selection_dir / "selection_training_dataset.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    validation = pd.read_csv(
        config.selection_dir / "human_validation_set.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    test = pd.read_csv(
        config.selection_dir / "frozen_human_test_set.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    rows: list[dict[str, Any]] = []
    for name, columns in ABLATIONS.items():
        train_text = prefixed_text(train, columns)
        validation_text = prefixed_text(validation, columns)
        test_text = prefixed_text(test, columns)
        model = Pipeline(
            [("tfidf", vectorizer()), ("clf", xgboost_classifier(config.random_state))]
        )
        y_train = train["label"].map({"NON_AI": 0, "AI": 1})
        model.fit(
            train_text,
            y_train,
            clf__sample_weight=sample_weights(train, config.human_weight),
        )
        validation_scores = [float(row[1]) for row in model.predict_proba(validation_text)]
        threshold_result = best_threshold(validation["label"], validation_scores)
        test_scores = [float(row[1]) for row in model.predict_proba(test_text)]
        test_pred = threshold_predictions(test_scores, threshold_result["threshold"])
        test_metrics = evaluate(test["label"], test_pred)
        model_path = config.output_dir / f"{name}.joblib"
        joblib.dump(model, model_path)
        predictions = test[["record_key", "label", "label_source", "title", "doi"]].copy()
        predictions["prediction"] = test_pred
        predictions["ai_score"] = [f"{score:.6f}" for score in test_scores]
        predictions["threshold"] = f"{threshold_result['threshold']:.2f}"
        predictions["correct"] = predictions["label"].eq(predictions["prediction"])
        predictions_path = config.output_dir / f"{name}_frozen_test_predictions.csv"
        predictions.to_csv(predictions_path, index=False)
        report = test_metrics["classification_report"]
        rows.append(
            {
                "ablation": name,
                "columns": list(columns),
                "selected_threshold": threshold_result["threshold"],
                "validation_macro_f1": threshold_result["metrics"]["macro_f1"],
                "test_accuracy": test_metrics["accuracy"],
                "test_macro_f1": test_metrics["macro_f1"],
                "test_ai_precision": report["AI"]["precision"],
                "test_ai_recall": report["AI"]["recall"],
                "test_non_ai_recall": report["NON_AI"]["recall"],
                "test_confusion_matrix": test_metrics["confusion_matrix"],
                "model_path": str(model_path),
                "predictions_path": str(predictions_path),
            }
        )

    ranked = sorted(rows, key=lambda row: row["test_macro_f1"], reverse=True)
    comparison_path = config.output_dir / "metadata_ablation_comparison.csv"
    pd.DataFrame(ranked).to_csv(comparison_path, index=False)
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
        "best_ablation": ranked[0]["ablation"],
        "comparison_csv": str(comparison_path),
        "rows": ranked,
    }
    (config.output_dir / "metadata_ablation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (config.output_dir / "metadata_ablation_metrics.txt").write_text(
        render_text(summary), encoding="utf-8"
    )
    return summary


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "AI relevance metadata ablation",
        "",
        f"best_ablation: {summary['best_ablation']}",
        "",
    ]
    for row in summary["rows"]:
        lines.append(
            f"{row['ablation']}: macro_f1={row['test_macro_f1']:.4f}, "
            f"accuracy={row['test_accuracy']:.4f}, "
            f"AI_precision={row['test_ai_precision']:.4f}, "
            f"NON_AI_recall={row['test_non_ai_recall']:.4f}, "
            f"threshold={row['selected_threshold']}"
        )
    lines.append("")
    lines.append(f"comparison_csv: {summary['comparison_csv']}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-dir", type=Path, default=DEFAULT_SELECTION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--human-weight", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run(
        Config(
            selection_dir=args.selection_dir,
            output_dir=args.output_dir,
            human_weight=args.human_weight,
        )
    )
    print(render_text(summary), end="")


if __name__ == "__main__":
    main()
