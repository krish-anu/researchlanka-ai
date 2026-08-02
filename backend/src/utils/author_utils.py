"""
Author extractor.

Schema columns involved (redundant group — collapsed to ONE canonical value):
    authors          - Author list as supplied or normalized by the source.
    author_names     - Author names normalized into a shared text field.
    -> canonical: "author_names_clean"  (per schema description, author_names
       IS the intended shared/normalized field, so it takes priority; authors
       is used only when author_names is empty)

Non-redundant author metadata (author_count, author_affiliations,
author_orcids, sri_lankan_authors) is passed through unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from utils.column_resolve import clean_str, first_present, is_present

__all__ = [
    "extract_authors",
    "extract_authors_by_doi",
    "extract_authors_batch",
    "split_author_names",
]

AUTHOR_NAME_PRIORITY = ["authors"]


def split_author_names(value: Any) -> list[str]:
    """
    Split a delimited author field into individual name strings. Tries
    semicolon/pipe/newline first (unambiguous), falls back to comma only
    when there are enough commas to suggest a simple list rather than
    "Last, First" formatting.
    """
    if not is_present(value):
        return []
    text = str(value).strip()
    for delim in [";", "|", "\n"]:
        if delim in text:
            return [a.strip() for a in text.split(delim) if a.strip()]
    if text.count(",") >= 3:
        return [a.strip() for a in text.split(",") if a.strip()]
    return [text]


def extract_authors(record: Mapping[str, Any]) -> dict:
    """
    Core single-record extractor.

    Args:
        record: one row of data (dict or pandas Series).

    Returns:
        {
            "author_names_clean": str | None,   # canonical, collapsed field
            "author_names_source": str | None,  # which column it came from
            "author_list": list[str],            # split into individual names
            "author_count_clean": int | None,    # from author_count, or
                                                    # len(author_list) if missing
            "author_affiliations": str | None,
            "author_orcids": str | None,
            "sri_lankan_authors": str | None,
        }
    """
    raw_value, source_col = first_present(record, AUTHOR_NAME_PRIORITY)
    author_list = split_author_names(raw_value)

    author_count = record.get("author_count")
    author_count_clean = None
    if is_present(author_count):
        try:
            author_count_clean = int(float(author_count))
        except (TypeError, ValueError):
            author_count_clean = None
    if author_count_clean is None and author_list:
        author_count_clean = len(author_list)

    return {
        "author_names_clean": clean_str(raw_value),
        "author_names_source": source_col,
        "author_list": author_list,
        "author_count_clean": author_count_clean,
        "author_affiliations": clean_str(record.get("author_affiliations")),
        "author_orcids": clean_str(record.get("author_orcids")),
        "sri_lankan_authors": clean_str(record.get("sri_lankan_authors")),
    }


def extract_authors_by_doi(
    df: pd.DataFrame, doi: str, doi_col: str = "doi"
) -> dict | None:
    """Extract author info for a single record identified by DOI."""
    matches = df[df[doi_col] == doi]
    if matches.empty:
        return None
    return extract_authors(matches.iloc[0])


def extract_authors_batch(
    df: pd.DataFrame, batch_size: int | None = None
) -> pd.DataFrame:
    """Apply extract_authors across an entire DataFrame, optionally in chunks."""
    cols = [
        "author_names_clean",
        "author_names_source",
        "author_list",
        "author_count_clean",
        "author_affiliations",
        "author_orcids",
        "sri_lankan_authors",
    ]

    if batch_size is None:
        records = df.apply(extract_authors, axis=1, result_type="expand")
        records.index = df.index
        return records

    chunks = []
    for start in range(0, len(df), batch_size):
        chunk = df.iloc[start : start + batch_size]
        result = chunk.apply(extract_authors, axis=1, result_type="expand")
        result.index = chunk.index
        chunks.append(result)
    return pd.concat(chunks) if chunks else pd.DataFrame(columns=cols)
