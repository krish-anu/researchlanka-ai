"""
Title extractor.

Schema columns involved:
    title             - Publication title.

Not collapsed into one raw column (title/subtitle/original_title carry
genuinely different meanings and your schema keeps them distinct), but this
extractor resolves a "display title" (title + subtitle combined when both
exist) and a normalized form suitable for filtering, grouping, and fuzzy
matching elsewhere in the pipeline.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

import pandas as pd

from utils.column_resolve import clean_str, is_present

__all__ = [
    "extract_title",
    "extract_title_by_doi",
    "extract_title_batch",
    "normalize_title_text",
]

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_title_text(text: Any) -> str:
    """
    Lowercase, strip accents/punctuation, collapse whitespace. Used for
    matching/filtering (e.g. fuzzy dedup, exact-match grouping), NOT for
    display — use 'title_display' for that.
    """
    if not is_present(text):
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = _PUNCT_RE.sub(" ", value)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return value


def extract_title(record: Mapping[str, Any]) -> dict:
    """
    Core single-record extractor.

    Args:
        record: one row of data (dict or pandas Series).

    Returns:
        {
            "title": str | None,                # pass-through
            "title_display": str | None,         # "Title: Subtitle" when both exist
            "title_normalized": str,             # lowercased, no punctuation — for matching
        }
    """
    title = clean_str(record.get("title"))
    subtitle = clean_str(record.get("subtitle"))
    original_title = clean_str(record.get("original_title"))

    if title and subtitle:
        title_display = f"{title}: {subtitle}"
    else:
        title_display = title or original_title

    title_normalized = normalize_title_text(title_display) if title_display else ""

    return {
        "title": title,
        "title_display": title_display,
        "title_normalized": title_normalized,
    } 


def extract_title_by_doi(
    df: pd.DataFrame, doi: str, doi_col: str = "doi"
) -> dict | None:
    """Extract title info for a single record identified by DOI."""
    matches = df[df[doi_col] == doi]
    if matches.empty:
        return None
    return extract_title(matches.iloc[0])


def extract_title_batch(
    df: pd.DataFrame, batch_size: int | None = None
) -> pd.DataFrame:
    """Apply extract_title across an entire DataFrame, optionally in chunks."""
    cols = ["title", "title_display", "title_normalized"]

    if batch_size is None:
        records = df.apply(extract_title, axis=1, result_type="expand")
        records.index = df.index
        return records

    chunks = []
    for start in range(0, len(df), batch_size):
        chunk = df.iloc[start : start + batch_size]
        result = chunk.apply(extract_title, axis=1, result_type="expand")
        result.index = chunk.index
        chunks.append(result)
    return pd.concat(chunks) if chunks else pd.DataFrame(columns=cols)
