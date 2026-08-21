#!/usr/bin/env python3
"""Compare supported publication classification model families.

Reusable comparison logic lives in ``src.modeling.classification_comparison``.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.classification_comparison import (  # noqa: E402
    ClassificationComparisonConfig,
    ClassificationComparisonResult,
    compare_classification_models,
    main,
    parse_c_values,
    parse_model_families,
    result_summary,
)

__all__ = [
    "ClassificationComparisonConfig",
    "ClassificationComparisonResult",
    "compare_classification_models",
    "main",
    "parse_c_values",
    "parse_model_families",
    "result_summary",
]


if __name__ == "__main__":
    main()
