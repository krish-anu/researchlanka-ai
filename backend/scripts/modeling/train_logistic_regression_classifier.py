#!/usr/bin/env python3
"""Train a Logistic Regression classifier for publication metadata text.

Run from the backend folder:

    python scripts/modeling/train_logistic_regression_classifier.py

By default this trains a classifier that predicts ``primary_domain`` from the
publication title, abstract, and keywords in ``common_publications_final.csv``.
Reusable training logic lives in ``src.modeling.training``.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.training import (  # noqa: E402
    DEFAULT_INPUT,
    DEFAULT_LABEL_COLUMN,
    DEFAULT_MODEL_DIR,
    DEFAULT_TEXT_COLUMNS,
    SavedArtifact,
    SavedModelArtifacts,
    TextTrainingConfig,
    TrainingResult,
    build_pipeline,
    combined_text,
    default_label_counts_output,
    default_manifest_output,
    default_metrics_output,
    default_model_output,
    default_predictions_output,
    load_training_frame,
    main,
    parse_class_weight,
    parse_document_frequency,
    parse_text_columns,
    file_sha256,
    render_metrics,
    result_summary,
    save_model_artifacts,
    slugify,
    train_logistic_regression_classifier,
    train_text_classifier,
    write_label_counts,
    write_manifest,
    write_predictions,
)

__all__ = [
    "DEFAULT_INPUT",
    "DEFAULT_LABEL_COLUMN",
    "DEFAULT_MODEL_DIR",
    "DEFAULT_TEXT_COLUMNS",
    "SavedArtifact",
    "SavedModelArtifacts",
    "TextTrainingConfig",
    "TrainingResult",
    "build_pipeline",
    "combined_text",
    "default_label_counts_output",
    "default_manifest_output",
    "default_metrics_output",
    "default_model_output",
    "default_predictions_output",
    "load_training_frame",
    "main",
    "parse_class_weight",
    "parse_document_frequency",
    "parse_text_columns",
    "file_sha256",
    "render_metrics",
    "result_summary",
    "save_model_artifacts",
    "slugify",
    "train_logistic_regression_classifier",
    "train_text_classifier",
    "write_label_counts",
    "write_manifest",
    "write_predictions",
]


if __name__ == "__main__":
    main()
