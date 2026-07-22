"""Small configurable transformations for mapped source fields."""

from __future__ import annotations

import re
from typing import Any

from research_analytics.cleaning import normalize_doi

YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")


def apply_transformations(
    record: dict[str, Any],
    transformations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply simple field transformations declared in configuration."""

    if not transformations:
        return record

    transformed = dict(record)
    for field_name, rule in transformations.items():
        if field_name not in transformed:
            continue
        transformed[field_name] = transform_value(transformed[field_name], rule)
    return transformed


def transform_value(value: Any, rule: dict[str, Any]) -> Any:
    rule_type = rule.get("type")

    if rule_type == "extract_year":
        if value is None:
            return None
        match = YEAR_RE.search(str(value))
        return int(match.group(1)) if match else None

    if rule_type == "split":
        if value is None or isinstance(value, list):
            return value or []
        separator = rule.get("separator", ";")
        return [part.strip() for part in str(value).split(separator) if part.strip()]

    if rule_type == "normalize_doi":
        return normalize_doi(value)

    if rule_type == "strip":
        return str(value).strip() if value is not None else None

    return value
