"""DOI normalization helpers shared by collection and comparison scripts."""

from __future__ import annotations

import math
import re
from typing import Any

DOI_VALUE_RE = re.compile(r"^10\.\d{4,9}/[^\s\"'<>]+$", re.IGNORECASE)


def normalize_doi(doi: Any) -> str | None:
    """Normalize DOI strings for stable matching and flat exports."""
    if doi is None:
        return None
    if isinstance(doi, float) and math.isnan(doi):
        return None

    normalized = str(doi).strip().lower()
    if not normalized or normalized == "nan":
        return None

    normalized = re.sub(
        r"^(https?://)?(dx\.)?doi\.org/",
        "",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.I)
    normalized = normalized.replace(" ", "")
    normalized = normalized.rstrip(".,;:)]}")

    return normalized.strip() or None


def is_valid_doi(doi: Any) -> bool:
    """Return whether a value is a syntactically valid normalized DOI."""
    normalized = normalize_doi(doi)
    return bool(normalized and DOI_VALUE_RE.fullmatch(normalized))
