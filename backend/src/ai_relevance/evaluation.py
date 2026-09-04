"""Gemini-vs-human evaluation for AI relevance labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from src.ai_relevance.config import DEFAULT_EVALUATION_DIR
from src.modeling.artifacts import write_csv_artifact, write_json_artifact
from src.utils.io_utils import load_dataset


@dataclass(frozen=True)
class GeminiHumanEvaluationConfig:
    input_path: Path
    output_dir: Path = DEFAULT_EVALUATION_DIR
    run_name: str = "gemini_ai_relevance"
    exclude_human_review: bool = True


def evaluate_gemini_against_human(
    config: GeminiHumanEvaluationConfig,
) -> dict[str, Any]:
    """Evaluate Gemini labels against completed human labels."""

    frame = load_dataset(config.input_path)
    for column in ("human_label", "ai_llm_label"):
        if column not in frame.columns:
            raise ValueError(f"{config.input_path} has no '{column}' column")

    scored = frame[
        frame["human_label"].isin(["AI", "NON_AI", "REVIEW"])
        & frame["ai_llm_label"].isin(["AI", "NON_AI", "REVIEW"])
    ].copy()
    if config.exclude_human_review:
        scored = scored[scored["human_label"] != "REVIEW"].copy()
    if scored.empty:
        raise ValueError("No completed human-labelled rows are available to evaluate")

    labels = ["AI", "NON_AI"] if config.exclude_human_review else ["AI", "NON_AI", "REVIEW"]
    y_true = scored["human_label"].astype(str)
    y_pred = scored["ai_llm_label"].astype(str)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        zero_division=0,
    )
    macro = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        average="macro",
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=labels)

    per_label = {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(labels)
    }
    metrics = {
        "run_name": config.run_name,
        "rows": int(len(scored)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "ai_precision": per_label["AI"]["precision"],
        "ai_recall": per_label["AI"]["recall"],
        "ai_f1": per_label["AI"]["f1"],
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "review_handling": (
            "human REVIEW records excluded"
            if config.exclude_human_review
            else "human REVIEW records included as a third class"
        ),
        "per_label": per_label,
    }

    config.output_dir.mkdir(parents=True, exist_ok=True)
    write_json_artifact(config.output_dir / f"{config.run_name}_metrics.json", metrics)
    matrix_rows = []
    for index, label in enumerate(labels):
        row = {"true_label": label}
        row.update({predicted: int(matrix[index][j]) for j, predicted in enumerate(labels)})
        matrix_rows.append(row)
    write_csv_artifact(
        config.output_dir / f"{config.run_name}_confusion_matrix.csv",
        fieldnames=["true_label", *labels],
        rows=matrix_rows,
    )

    false_positives = scored[(scored["human_label"] == "NON_AI") & (scored["ai_llm_label"] == "AI")]
    false_negatives = scored[(scored["human_label"] == "AI") & (scored["ai_llm_label"] == "NON_AI")]
    false_positives.to_csv(config.output_dir / f"{config.run_name}_false_positives.csv", index=False)
    false_negatives.to_csv(config.output_dir / f"{config.run_name}_false_negatives.csv", index=False)
    return metrics
