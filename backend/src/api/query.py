"""Query-string parsing and validation."""

from __future__ import annotations

from typing import Any

from src.api.constants import LIST_FILTERS
from src.api.errors import APIError


def parse_filters(query: dict[str, list[str]]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key in LIST_FILTERS:
        values = query.get(key)
        if not values:
            continue
        if key in {"type", "institution", "country", "field", "subfield", "topic", "journal", "source_dataset", "quality_flag"}:
            filters[key] = [item for value in values for item in split_values(value)]
        elif key in {"is_oa", "has_doi", "has_abstract"}:
            filters[key] = parse_bool(values[-1])
        elif key in {"year_min", "year_max"}:
            filters[key] = parse_int(values[-1], key)
        else:
            filters[key] = values[-1].strip()

    year_min = filters.get("year_min")
    year_max = filters.get("year_max")
    if year_min is not None and year_max is not None and year_min > year_max:
        raise APIError(
            "invalid_filter",
            "year_min must be less than or equal to year_max.",
            details={"field": "year_min"},
        )
    return filters


def first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[-1]


def parse_positive_int(query: dict[str, list[str]], key: str, *, default: int) -> int:
    value = first(query, key)
    if value is None or value == "":
        return default
    parsed = parse_int(value, key)
    if parsed < 1:
        raise APIError("invalid_filter", f"{key} must be at least 1.", details={"field": key})
    return parsed


def parse_int(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise APIError("invalid_filter", f"{field} must be an integer.", details={"field": field}) from exc


def parse_bool(value: str | None, *, default: bool | None = None) -> bool | None:
    if value is None or value == "":
        return default
    text = value.casefold()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0"}:
        return False
    raise APIError("invalid_filter", f"Invalid boolean value: {value}.")


def split_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
