"""Sentence-transformer AI relevance experiment on frozen human holdout data."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.modeling.artifacts import file_sha256
from src.modeling.linear_svm_training import combined_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION_DIR = (
    PROJECT_ROOT / "data/models/ai_relevance/validated_human_selection_xgboost_fast"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data/models/ai_relevance/sentence_transformer_experiment"
)
TEXT_COLUMNS = ("title", "abstract", "keywords")
LABELS = ("AI", "NON_AI")


class TextEncoder(Protocol):
    def encode(self, texts: list[str], **kwargs: Any) -> Any:
        """Return one dense embedding per input text."""


@dataclass(frozen=True)
class SentenceTransformerExperimentConfig:
    selection_dir: Path = DEFAULT_SELECTION_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    sentence_transformer_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    classifiers: tuple[str, ...] = ("logistic_regression",)
    batch_size: int = 64
    random_state: int = 42
    human_weight: float = 3.0
    text_columns: tuple[str, ...] = TEXT_COLUMNS


def label_to_binary(labels: pd.Series) -> np.ndarray:
    return labels.map({"NON_AI": 0, "AI": 1}).to_numpy(dtype=int)


def binary_to_label(values: Any) -> list[str]:
    return ["AI" if int(value) == 1 else "NON_AI" for value in values]


def prefixed_text(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    prepared = frame.copy()
    for column in columns:
        if column not in prepared.columns:
            prepared[column] = ""
    pieces = [
        column.upper() + ": " + prepared[column].fillna("").astype(str)
        for column in columns
    ]
    text = pd.concat(pieces, axis=1).agg(" ".join, axis=1)
    return text.str.replace(r"\s+", " ", regex=True).str.strip()


def load_experiment_frames(
    selection_dir: Path,
    *,
    text_columns: tuple[str, ...] = TEXT_COLUMNS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(
        selection_dir / "selection_training_dataset.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    validation = pd.read_csv(
        selection_dir / "human_validation_set.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    test = pd.read_csv(
        selection_dir / "frozen_human_test_set.csv",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    for frame in (train, validation, test):
        if "text" not in frame.columns:
            frame["text"] = prefixed_text(frame, text_columns)
        else:
            blank = frame["text"].fillna("").astype(str).str.strip().eq("")
            if blank.any():
                frame.loc[blank, "text"] = combined_text(
                    frame.loc[blank].fillna(""),
                    text_columns,
                )
        frame.drop(frame[~frame["label"].isin(LABELS)].index, inplace=True)
        blank_text = frame["text"].fillna("").astype(str).str.strip().eq("")
        frame.drop(frame[blank_text].index, inplace=True)
        frame.reset_index(drop=True, inplace=True)
    return train, validation, test


def load_sentence_transformer(model_name: str) -> TextEncoder:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError(
            "sentence-transformers is required for this experiment. "
            "Install it in the backend environment, then rerun the script."
        ) from exc
    return SentenceTransformer(model_name)


def encode_frame(
    encoder: TextEncoder,
    frame: pd.DataFrame,
    *,
    batch_size: int,
) -> np.ndarray:
    embeddings = encoder.encode(
        frame["text"].astype(str).tolist(),
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(embeddings, dtype=np.float32)


def sample_weights(frame: pd.DataFrame, human_weight: float) -> np.ndarray:
    if "label_source" not in frame.columns:
        return np.ones(len(frame), dtype=float)
    return (
        frame["label_source"]
        .astype(str)
        .str.contains("human", case=False, na=False)
        .map({True: human_weight, False: 1.0})
        .to_numpy(dtype=float)
    )


def classifier_spec(name: str, random_state: int) -> Any:
    if name == "logistic_regression":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=5000,
                        solver="lbfgs",
                        random_state=random_state,
                    ),
                ),
            ]
        )
    if name == "xgboost":
        try:
            from xgboost import XGBClassifier
        except Exception as exc:
            raise RuntimeError(
                "XGBoost requested but xgboost is not installed."
            ) from exc
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
    raise ValueError(f"Unsupported embedding classifier: {name}")


def evaluate_predictions(
    *,
    labels: pd.Series,
    predictions: list[str],
    scores: list[float],
) -> dict[str, Any]:
    binary_labels = label_to_binary(labels)
    false_positive = int(
        sum(
            true == "NON_AI" and pred == "AI"
            for true, pred in zip(labels, predictions, strict=True)
        )
    )
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(labels, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(labels, predictions, average="weighted", zero_division=0)
        ),
        "brier_score": float(brier_score_loss(binary_labels, scores)),
        "false_positives": false_positive,
        "classification_report": classification_report(
            labels,
            predictions,
            labels=list(LABELS),
            zero_division=0,
            output_dict=True,
        ),
        "confusion_matrix_labels": list(LABELS),
        "confusion_matrix": confusion_matrix(
            labels,
            predictions,
            labels=list(LABELS),
        ).tolist(),
    }


def fit_classifier(
    *,
    name: str,
    x_train: np.ndarray,
    train: pd.DataFrame,
    config: SentenceTransformerExperimentConfig,
) -> Any:
    model = classifier_spec(name, config.random_state)
    y_train = label_to_binary(train["label"])
    weights = sample_weights(train, config.human_weight)
    if isinstance(model, Pipeline):
        model.fit(x_train, y_train, clf__sample_weight=weights)
    else:
        model.fit(x_train, y_train, sample_weight=weights)
    return model


def predict_scores(model: Any, embeddings: np.ndarray) -> list[float]:
    probabilities = model.predict_proba(embeddings)
    return [float(row[1]) for row in probabilities]


def train_and_evaluate_classifier(
    *,
    name: str,
    embeddings: dict[str, np.ndarray],
    frames: dict[str, pd.DataFrame],
    config: SentenceTransformerExperimentConfig,
) -> dict[str, Any]:
    model = fit_classifier(
        name=name,
        x_train=embeddings["train"],
        train=frames["train"],
        config=config,
    )
    validation_scores = predict_scores(model, embeddings["validation"])
    validation_predictions = binary_to_label(model.predict(embeddings["validation"]))
    validation_metrics = evaluate_predictions(
        labels=frames["validation"]["label"],
        predictions=validation_predictions,
        scores=validation_scores,
    )
    test_scores = predict_scores(model, embeddings["test"])
    test_predictions = binary_to_label(model.predict(embeddings["test"]))
    test_metrics = evaluate_predictions(
        labels=frames["test"]["label"],
        predictions=test_predictions,
        scores=test_scores,
    )

    model_path = config.output_dir / f"sentence_transformer_{name}.joblib"
    joblib.dump(
        {
            "sentence_transformer_model": config.sentence_transformer_model,
            "classifier_name": name,
            "classifier": model,
            "text_columns": config.text_columns,
        },
        model_path,
    )
    predictions = frames["test"][
        [
            column
            for column in ("record_key", "label", "label_source", "title", "doi", "text")
            if column in frames["test"].columns
        ]
    ].copy()
    predictions["prediction"] = test_predictions
    predictions["ai_score"] = [f"{score:.6f}" for score in test_scores]
    predictions["correct"] = predictions["label"].eq(predictions["prediction"])
    predictions_path = (
        config.output_dir / f"sentence_transformer_{name}_frozen_test_predictions.csv"
    )
    predictions.to_csv(predictions_path, index=False)
    false_positive_path = config.output_dir / f"sentence_transformer_{name}_false_positives.csv"
    predictions[
        predictions["label"].eq("NON_AI") & predictions["prediction"].eq("AI")
    ].to_csv(false_positive_path, index=False)
    return {
        "model_family": f"sentence_transformer_{name}",
        "model_path": str(model_path),
        "model_sha256": file_sha256(model_path),
        "predictions_path": str(predictions_path),
        "false_positives_path": str(false_positive_path),
        "validation_metrics": validation_metrics,
        "frozen_test_metrics": test_metrics,
    }


def run_sentence_transformer_experiment(
    config: SentenceTransformerExperimentConfig = SentenceTransformerExperimentConfig(),
    *,
    encoder: TextEncoder | None = None,
) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    train, validation, test = load_experiment_frames(
        config.selection_dir,
        text_columns=config.text_columns,
    )
    actual_encoder = encoder or load_sentence_transformer(
        config.sentence_transformer_model
    )
    frames = {"train": train, "validation": validation, "test": test}
    embeddings = {
        name: encode_frame(actual_encoder, frame, batch_size=config.batch_size)
        for name, frame in frames.items()
    }
    rows = [
        train_and_evaluate_classifier(
            name=name,
            embeddings=embeddings,
            frames=frames,
            config=config,
        )
        for name in config.classifiers
    ]
    ranked = sorted(
        rows,
        key=lambda row: row["frozen_test_metrics"]["macro_f1"],
        reverse=True,
    )
    comparison_rows: list[dict[str, Any]] = []
    for row in ranked:
        report = row["frozen_test_metrics"]["classification_report"]
        comparison_rows.append(
            {
                "model_family": row["model_family"],
                "frozen_test_accuracy": row["frozen_test_metrics"]["accuracy"],
                "frozen_test_macro_f1": row["frozen_test_metrics"]["macro_f1"],
                "ai_precision": report["AI"]["precision"],
                "ai_recall": report["AI"]["recall"],
                "non_ai_recall": report["NON_AI"]["recall"],
                "brier_score": row["frozen_test_metrics"]["brier_score"],
                "false_positives": row["frozen_test_metrics"]["false_positives"],
                "validation_macro_f1": row["validation_metrics"]["macro_f1"],
                "model_path": row["model_path"],
                "predictions_path": row["predictions_path"],
                "false_positives_path": row["false_positives_path"],
            }
        )
    comparison_path = config.output_dir / "sentence_transformer_comparison.csv"
    pd.DataFrame(comparison_rows).to_csv(comparison_path, index=False)
    summary = {
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_type": "sentence_transformer_embeddings",
        "promotion_policy": (
            "Research experiment only. Promote only after frozen human set improves "
            "AI precision, AI recall, NON_AI recall, macro F1, false positives, and Brier score."
        ),
        "config": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
        "rows": {
            "train": int(len(train)),
            "validation": int(len(validation)),
            "frozen_test": int(len(test)),
        },
        "label_counts": {
            name: {
                key: int(value)
                for key, value in frame["label"].value_counts().items()
            }
            for name, frame in frames.items()
        },
        "best_model_family": ranked[0]["model_family"],
        "comparison_csv": str(comparison_path),
        "models": ranked,
    }
    summary_path = config.output_dir / "sentence_transformer_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    text_path = config.output_dir / "sentence_transformer_metrics.txt"
    text_path.write_text(
        render_sentence_transformer_report(summary, comparison_rows),
        encoding="utf-8",
    )
    return summary


def render_sentence_transformer_report(
    summary: dict[str, Any],
    comparison_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "Sentence-transformer AI relevance experiment",
        "",
        f"sentence_transformer_model: {summary['config']['sentence_transformer_model']}",
        f"train_rows: {summary['rows']['train']}",
        f"validation_rows: {summary['rows']['validation']}",
        f"frozen_test_rows: {summary['rows']['frozen_test']}",
        f"best_model_family: {summary['best_model_family']}",
        "",
        "Frozen human test metrics:",
    ]
    for row in comparison_rows:
        lines.append(
            f"{row['model_family']}: macro_f1={row['frozen_test_macro_f1']:.4f}, "
            f"AI_precision={row['ai_precision']:.4f}, "
            f"AI_recall={row['ai_recall']:.4f}, "
            f"NON_AI_recall={row['non_ai_recall']:.4f}, "
            f"Brier={row['brier_score']:.4f}, "
            f"false_positives={row['false_positives']}"
        )
    lines.extend(["", f"comparison_csv: {summary['comparison_csv']}"])
    return "\n".join(lines) + "\n"
