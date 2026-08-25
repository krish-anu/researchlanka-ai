#!/usr/bin/env python3
"""Predict primary_field and primary_subfield for unlabeled publications.

Loads the hierarchical Linear SVM models and writes:
  predicted_field
  predicted_subfield

By default only rows missing field and/or subfield labels are scored.

Usage (from backend/):

    python scripts/modeling/predict_field_subfield.py \\
        --input data/processed/common/common_publications_final.csv \\
        --output data/processed/common/common_publications_final_with_predictions.csv \\
        --only-unlabeled

    # Score every row with text:
    python scripts/modeling/predict_field_subfield.py --all-rows
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.hierarchical_linear_svm import (
    DEFAULT_FIELD_COLUMN,
    DEFAULT_INPUT,
    DEFAULT_OUTPUT,
    DEFAULT_SUBFIELD_COLUMN,
    DEFAULT_TEXT_COLUMNS,
    PRED_FIELD_COLUMN,
    PRED_SUBFIELD_COLUMN,
    default_field_model_output,
    default_subfield_model_output,
    parse_text_columns,
    run_field_subfield_prediction,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Predict field + subfield for publications missing labels "
            f"(writes {PRED_FIELD_COLUMN}, {PRED_SUBFIELD_COLUMN})."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--field-model",
        type=Path,
        default=None,
        help="Path to field-level joblib (default: data/models/linear_svm_hierarchical_field.joblib)",
    )
    parser.add_argument(
        "--subfield-model",
        type=Path,
        default=None,
        help="Path to subfield models dict joblib",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
    )
    parser.add_argument("--field-column", default=DEFAULT_FIELD_COLUMN)
    parser.add_argument("--subfield-column", default=DEFAULT_SUBFIELD_COLUMN)
    parser.add_argument(
        "--all-rows",
        action="store_true",
        help="Predict for every row with text (default: unlabeled only)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    only_unlabeled = not args.all_rows

    field_model = args.field_model or default_field_model_output()
    subfield_model = args.subfield_model or default_subfield_model_output()

    if not field_model.exists():
        raise SystemExit(
            f"Field model not found: {field_model}\n"
            "Train first: python scripts/modeling/train_linear_svm_hierarchical.py"
        )
    if not subfield_model.exists():
        raise SystemExit(
            f"Subfield model not found: {subfield_model}\n"
            "Train first: python scripts/modeling/train_linear_svm_hierarchical.py"
        )

    result = run_field_subfield_prediction(
        input_path=args.input,
        output_path=args.output,
        field_model_path=field_model,
        subfield_model_path=subfield_model,
        text_columns=args.text_columns,
        only_unlabeled=only_unlabeled,
        field_column=args.field_column,
        subfield_column=args.subfield_column,
    )

    n_field = int(result[PRED_FIELD_COLUMN].notna().sum())
    n_sub = int(result[PRED_SUBFIELD_COLUMN].notna().sum())
    print(f"Wrote: {args.output}")
    print(f"Rows with {PRED_FIELD_COLUMN}: {n_field:,}")
    print(f"Rows with {PRED_SUBFIELD_COLUMN}: {n_sub:,}")
    print(f"Mode: {'unlabeled only' if only_unlabeled else 'all rows with text'}")


if __name__ == "__main__":
    main()
