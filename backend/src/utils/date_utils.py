"""
Publication date extractor.

Schema columns involved:
    publication_date    - Best available publication date.
    published_date       - Published date, mainly from Crossref.
    created_date          - Record creation date, mainly from Crossref.
    publication_year      - Publication year.

These are NOT collapsed into one column, because they carry genuinely
different meanings (created vs published vs "best available") and your
schema keeps them distinct on purpose. What this extractor does instead is
resolve ONE best-guess "publication_date_clean" for filtering/sorting/
matching, using a fixed priority order, while still returning the original
fields for anyone who needs the raw distinction.

Priority for publication_date_clean:
    1. publication_date   (already the "best available" field per schema)
    2. published_date
    3. created_date
    4. publication_year   (expanded to Jan 1 of that year, flagged as such)
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from utils.column_resolve import clean_str

__all__ = [
    "extract_publication_date",
    "extract_publication_date_by_doi",
    "extract_publication_date_batch",
]

DATE_PRIORITY = ["publication_date"]

def _parse_date(value: Any) -> pd.Timestamp:
    """Parse whatever date format is present; returns pd.NaT on failure."""
    text = clean_str(value)
    if text is None:
        return pd.NaT
    return pd.to_datetime(text, errors="coerce")


def _parse_year(value: Any) -> int | None:
    """Extract a plausible 4-digit year from an int, float, or string."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        year = int(float(value))
        return year if 1000 <= year <= 2100 else None
    except (TypeError, ValueError):
        return None


def extract_publication_date(record: Mapping[str, Any]) -> dict:
    """
    Core single-record extractor.

    Args:
        record: one row of data (dict or pandas Series).

    Returns:
        {
            "publication_date_clean": pd.Timestamp | pd.NaT,
            "publication_date_source": str,   # which field it was resolved from
            "publication_year_clean": int | None,
            # pass-through of the original distinct fields, unchanged:
            "publication_date": str | None,
            "publication_year": int | None,
        }
    """
    resolved_date = pd.NaT
    resolved_source = "unresolved"

    for col in DATE_PRIORITY:
        parsed = _parse_date(record.get(col))
        if pd.notna(parsed):
            resolved_date = parsed
            resolved_source = col
            break

    if pd.isna(resolved_date):
        year = _parse_year(record.get("publication_year"))
        if year is not None:
            resolved_date = pd.Timestamp(year=year, month=1, day=1)
            resolved_source = "publication_year_fallback"

    return {
        "publication_date_clean": resolved_date,
        "publication_date_source": resolved_source,
        "publication_year_clean": int(resolved_date.year)
        if pd.notna(resolved_date)
        else None,
        "publication_date": clean_str(record.get("publication_date")),
        "publication_year": _parse_year(record.get("publication_year")),
    }


def extract_publication_date_by_doi(
    df: pd.DataFrame, doi: str, doi_col: str = "doi"
) -> dict | None:
    """Extract publication date info for a single record identified by DOI."""
    matches = df[df[doi_col] == doi]
    if matches.empty:
        return None
    return extract_publication_date(matches.iloc[0])


def extract_publication_date_batch(
    df: pd.DataFrame, batch_size: int | None = None
) -> pd.DataFrame:
    """
    Apply extract_publication_date across an entire DataFrame, optionally
    in chunks.
    """
    cols = [
        "publication_date_clean",
        "publication_date_source",
        "publication_year_clean",
        "publication_date",
        "published_date",
        "created_date",
        "publication_year",
    ]

    if batch_size is None:
        records = df.apply(extract_publication_date, axis=1, result_type="expand")
        records.index = df.index
        return records

    chunks = []
    for start in range(0, len(df), batch_size):
        chunk = df.iloc[start : start + batch_size]
        result = chunk.apply(extract_publication_date, axis=1, result_type="expand")
        result.index = chunk.index
        chunks.append(result)
    return pd.concat(chunks) if chunks else pd.DataFrame(columns=cols)
