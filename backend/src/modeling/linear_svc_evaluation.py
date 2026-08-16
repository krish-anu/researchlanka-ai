"""Evaluation utilities for Linear SVM publication classifiers.

Covers per-model evaluation (classification report, confusion matrix,
metrics.json), a hierarchical (domain + subfield) summary, and lightweight
experiment tracking for hyperparameter comparisons.

Outputs per model:
    <name>_classification_report.txt
    <name>_classification_report.csv
    <name>_confusion_matrix.csv
    <name>_metrics.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "models" / "linear_svm"


# ============================================================================
# BASIC METRICS
# ============================================================================


def calculate_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(y_true, y_pred, average="weighted", zero_division=0)
        ),
    }


# ============================================================================
# CLASSIFICATION REPORT / CONFUSION MATRIX
# ============================================================================


def save_classification_report(
    y_true, y_pred, txt_path: Path, csv_path: Path
) -> pd.DataFrame:
    """Write both a human-readable .txt report and a structured .csv report."""
    report_text = classification_report(y_true, y_pred, zero_division=0)
    report_dict = classification_report(
        y_true, y_pred, output_dict=True, zero_division=0
    )
    report_df = pd.DataFrame(report_dict).transpose()

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(report_text, encoding="utf-8")
    report_df.to_csv(csv_path)

    return report_df


def save_confusion_matrix(y_true, y_pred, output_path: Path) -> pd.DataFrame:
    labels = sorted(set(y_true))
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    matrix_df = pd.DataFrame(matrix, index=labels, columns=labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_df.to_csv(output_path)

    return matrix_df


# ============================================================================
# MODEL EVALUATION
# ============================================================================


def evaluate_classifier(
    model,
    X_test,
    y_test,
    model_name: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict:
    """Evaluate one fitted classifier and write its report artifacts.

    Used for the domain classifier and each domain-specific subfield
    classifier alike; `model_name` should be unique per model (e.g.
    "domain" or "subfield_physics").
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = model_name.lower().replace(" ", "_")

    predictions = model.predict(X_test)
    metrics = calculate_metrics(y_test, predictions)

    txt_file = output_dir / f"{prefix}_classification_report.txt"
    csv_file = output_dir / f"{prefix}_classification_report.csv"
    cm_file = output_dir / f"{prefix}_confusion_matrix.csv"
    json_file = output_dir / f"{prefix}_metrics.json"

    save_classification_report(y_test, predictions, txt_file, csv_file)
    save_confusion_matrix(y_test, predictions, cm_file)

    result = {
        "model_name": model_name,
        "created_at": datetime.now(UTC).isoformat(),
        "samples": len(y_test),
        "classes": len(set(y_test)),
        **metrics,
        "artifacts": {
            "report_txt": str(txt_file),
            "report_csv": str(csv_file),
            "confusion_matrix": str(cm_file),
            "metrics_json": str(json_file),
        },
    }

    with open(json_file, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=4)

    return result


# ============================================================================
# HIERARCHICAL EVALUATION SUMMARY
# ============================================================================


def save_hierarchical_summary(
    domain_metrics: dict,
    subfield_metrics: dict,
    output_path: Path = DEFAULT_OUTPUT_DIR / "hierarchical_summary.json",
) -> Path:
    """Combine a domain model's metrics with one or more subfield models' metrics."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "domain_model": domain_metrics,
        "subfield_models": subfield_metrics,
        "created_at": datetime.now(UTC).isoformat(),
    }

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=4)

    return output_path


# ============================================================================
# EXPERIMENT TRACKING
# ============================================================================


def save_experiment_result(
    result: dict,
    output_path: Path = DEFAULT_OUTPUT_DIR / "ngram_experiment_results.csv",
) -> Path:
    """Append one hyperparameter-sweep result row to a running CSV log."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        existing = pd.read_csv(output_path)
        combined = pd.concat([existing, pd.DataFrame([result])], ignore_index=True)
    else:
        combined = pd.DataFrame([result])

    combined.to_csv(output_path, index=False)
    return output_path


def save_training_summary(
    summary: dict,
    output_path: Path = DEFAULT_OUTPUT_DIR / "training_summary.json",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=4, default=str)

    return output_path
