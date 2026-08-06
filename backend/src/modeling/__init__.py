"""Reusable model-training utilities for publication analytics."""

from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = [
    "DEFAULT_INPUT",
    "DEFAULT_LABEL_COLUMN",
    "DEFAULT_MODEL_DIR",
    "DEFAULT_TEXT_COLUMNS",
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
    "parse_class_weight",
    "parse_document_frequency",
    "parse_text_columns",
    "render_metrics",
    "result_summary",
    "slugify",
    "train_logistic_regression_classifier",
    "train_text_classifier",
    "write_label_counts",
    "write_manifest",
    "write_predictions",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = import_module("src.modeling.training")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
