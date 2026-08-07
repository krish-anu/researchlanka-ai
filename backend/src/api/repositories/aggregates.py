"""Small aggregate helpers used by repository analytics."""

from __future__ import annotations

from typing import Any


def normalized_key(value: Any) -> str:
    text = str(value).strip().casefold()
    parts = []
    previous_dash = False
    for char in text:
        if char.isalnum():
            parts.append(char)
            previous_dash = False
        elif not previous_dash:
            parts.append("-")
            previous_dash = True
    return "".join(parts).strip("-")


def aggregate_profile(key: str, rows: list[dict[str, Any]], *, kind: str) -> dict[str, Any]:
    citations = [row.get("citation_count") or 0 for row in rows]
    years = [row.get("publication_year") for row in rows if row.get("publication_year") is not None]
    return {
        "key": normalized_key(key),
        "label": key,
        "type": kind,
        "publication_count": len(rows),
        "citation_total": sum(citations),
        "average_citations": round(sum(citations) / len(citations), 2) if citations else 0,
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "disambiguation_level": "name" if kind == "researcher" else "registry_or_name",
    }


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def percentage(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0
