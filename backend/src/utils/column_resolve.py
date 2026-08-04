"""
Shared helper for resolving one canonical value out of several redundant /
overlapping schema columns (e.g. journal vs container_title vs source_name).

Every extractor in this package follows the same pattern:
    1. Define a priority-ordered list of source columns for a concept.
    2. Take the first non-empty value found, in that order.
    3. Record which column it came from (useful for auditing/debugging).

This file holds that shared logic once so every extractor stays consistent
and short.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd


def is_present(value: Any) -> bool:
    """True if value counts as 'populated' (not None/NaN/empty string/empty list)."""
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def first_present(record: Mapping, columns: Sequence[str]) -> tuple[Any, str | None]:
    """
    Return (value, column_name) for the first column in `columns` (priority
    order) that has a populated value in `record`. Returns (None, None) if
    none are populated.
    """
    for col in columns:
        val = record.get(col)
        if is_present(val):
            return val, col
    return None, None


def clean_str(value: Any) -> str | None:
    """Coerce to a stripped string, or None if empty/missing."""
    if not is_present(value):
        return None
    return str(value).strip()
