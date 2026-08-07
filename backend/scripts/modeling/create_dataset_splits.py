#!/usr/bin/env python3
"""Create train, validation, and test CSVs for publication classifier datasets.

Run from the backend folder:

    python scripts/modeling/create_dataset_splits.py

Reusable split logic lives in ``src.modeling.dataset_splits``.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.dataset_splits import (  # noqa: E402
    DEFAULT_INPUT,
    DEFAULT_LABEL_COLUMN,
    DEFAULT_MIN_CLASS_COUNT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RANDOM_STATE,
    DEFAULT_TEST_RATIO,
    DEFAULT_TEXT_COLUMNS,
    DEFAULT_TRAIN_RATIO,
    DEFAULT_VALIDATION_RATIO,
    DatasetSplitConfig,
    DatasetSplitResult,
    add_source_row,
    combined_text,
    create_dataset_splits,
    label_counts_by_split,
    load_split_frame,
    main,
    parse_text_columns,
    result_summary,
    split_counts,
    split_frame,
    summary_rows,
    validate_config,
    with_split_column,
)

__all__ = [
    "DEFAULT_INPUT",
    "DEFAULT_LABEL_COLUMN",
    "DEFAULT_MIN_CLASS_COUNT",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_RANDOM_STATE",
    "DEFAULT_TEST_RATIO",
    "DEFAULT_TEXT_COLUMNS",
    "DEFAULT_TRAIN_RATIO",
    "DEFAULT_VALIDATION_RATIO",
    "DatasetSplitConfig",
    "DatasetSplitResult",
    "add_source_row",
    "combined_text",
    "create_dataset_splits",
    "label_counts_by_split",
    "load_split_frame",
    "main",
    "parse_text_columns",
    "result_summary",
    "split_counts",
    "split_frame",
    "summary_rows",
    "validate_config",
    "with_split_column",
]


if __name__ == "__main__":
    main()
