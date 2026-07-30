"""Small configurable transformations for mapped source fields."""

from __future__ import annotations

from typing import Any

from research_analytics.cleaning import (
    normalize_doi,
    normalize_publication_date,
    normalize_publication_year,
)

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
        return normalize_publication_year(value)

    if rule_type == "split":
        if value is None or isinstance(value, list):
            return value or []
        separator = rule.get("separator", ";")
        return [part.strip() for part in str(value).split(separator) if part.strip()]

    if rule_type == "normalize_doi":
        return normalize_doi(value)

    if rule_type in {"normalize_date", "normalize_publication_date"}:
        return normalize_publication_date(value)

    if rule_type in {"normalize_year", "normalize_publication_year"}:
        return normalize_publication_year(value)

    if rule_type == "strip":
        return str(value).strip() if value is not None else None

    return value
