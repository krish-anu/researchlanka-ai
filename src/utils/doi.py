"""DOI normalization helpers shared by collection and comparison scripts."""

from __future__ import annotations

import math
import re
from typing import Any


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
