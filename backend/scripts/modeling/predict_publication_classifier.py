#!/usr/bin/env python3
"""Run inference with a saved publication text classifier.

Run from the backend folder:

    python scripts/modeling/predict_publication_classifier.py

Reusable inference logic lives in ``src.modeling.inference``.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.inference import (  # noqa: E402
    DEFAULT_METADATA_COLUMNS,
    InferenceResult,
    ModelInferenceConfig,
    default_inference_manifest_output,
    default_inference_output,
    expected_model_sha256,
    load_inference_frame,
    load_verified_model,
    main,
    parse_columns,
    result_summary,
    run_model_inference,
    verify_model_checksum,
)

__all__ = [
    "DEFAULT_METADATA_COLUMNS",
    "InferenceResult",
    "ModelInferenceConfig",
    "default_inference_manifest_output",
    "default_inference_output",
    "expected_model_sha256",
    "load_inference_frame",
    "load_verified_model",
    "main",
    "parse_columns",
    "result_summary",
    "run_model_inference",
    "verify_model_checksum",
]


if __name__ == "__main__":
    main()
