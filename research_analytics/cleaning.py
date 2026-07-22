"""Configurable cleaning utilities for publication records."""

from __future__ import annotations

import math
import re
from typing import Any

from research_analytics.config import CleaningConfig

DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
TITLE_SPACE_RE = re.compile(r"\s+")


def clean_record(record: dict[str, Any], config: CleaningConfig) -> dict[str, Any]:
    """Apply enabled cleaning rules and return a new record."""

    cleaned = dict(record)
    rules_applied: list[str] = []

    if config.normalize_doi:
        cleaned["doi"] = normalize_doi(cleaned.get("doi"))
        rules_applied.append("normalize_doi")

    if config.normalize_title:
        title = normalize_text(cleaned.get("title"))
        cleaned["title"] = title
        cleaned["normalized_title"] = normalize_title_key(title)
        rules_applied.append("normalize_title")

    if config.normalize_author_names:
        cleaned["authors"] = normalize_list_like(cleaned.get("authors"))
        rules_applied.append("normalize_author_names")

    if config.normalize_institutions:
        cleaned["institutions"] = normalize_list_like(cleaned.get("institutions"))
        rules_applied.append("normalize_institutions")

    provenance = dict(cleaned.get("_provenance") or {})
    provenance["cleaning_rules_applied"] = rules_applied
    cleaned["_provenance"] = provenance
    return cleaned


def normalize_doi(value: Any) -> str | None:
    """Normalize DOI strings without assuming that every record has a DOI."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    doi = str(value).strip()
    if not doi:
        return None
    doi = DOI_PREFIX_RE.sub("", doi).strip()
    return doi.lower() or None


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = TITLE_SPACE_RE.sub(" ", str(value)).strip()
    return text or None


def normalize_title_key(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() or None


def normalize_list_like(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]
