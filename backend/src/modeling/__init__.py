"""Reusable model-training utilities for publication analytics."""

from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = [
    "DEFAULT_INPUT",
    "DEFAULT_LABEL_COLUMN",
    "DEFAULT_METADATA_COLUMNS",
    "DEFAULT_MODEL_DIR",
    "DEFAULT_TEXT_COLUMNS",
    "InferenceResult",
    "ModelInferenceConfig",
    "TextTrainingConfig",
    "TrainingResult",
    "SavedArtifact",
    "SavedModelArtifacts",
    "build_pipeline",
    "combined_text",
    "default_label_counts_output",
    "default_inference_manifest_output",
    "default_inference_output",
    "default_manifest_output",
    "default_metrics_output",
    "default_model_output",
    "default_predictions_output",
    "expected_model_sha256",
    "load_training_frame",
    "load_verified_model",
    "parse_class_weight",
    "parse_columns",
    "parse_document_frequency",
    "parse_text_columns",
    "file_sha256",
    "render_metrics",
    "result_summary",
    "run_model_inference",
    "save_model_artifacts",
    "slugify",
    "train_logistic_regression_classifier",
    "train_text_classifier",
    "verify_model_checksum",
    "write_label_counts",
    "write_manifest",
    "write_predictions",
]


_NAME_TO_MODULE = {
    "DEFAULT_METADATA_COLUMNS": "src.modeling.inference",
    "InferenceResult": "src.modeling.inference",
    "ModelInferenceConfig": "src.modeling.inference",
    "default_inference_manifest_output": "src.modeling.inference",
    "default_inference_output": "src.modeling.inference",
    "expected_model_sha256": "src.modeling.inference",
    "load_verified_model": "src.modeling.inference",
    "parse_columns": "src.modeling.inference",
    "run_model_inference": "src.modeling.inference",
    "verify_model_checksum": "src.modeling.inference",
    "SavedArtifact": "src.modeling.artifacts",
    "SavedModelArtifacts": "src.modeling.artifacts",
    "file_sha256": "src.modeling.artifacts",
    "save_model_artifacts": "src.modeling.artifacts",
}


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = import_module(_NAME_TO_MODULE.get(name, "src.modeling.training"))
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
