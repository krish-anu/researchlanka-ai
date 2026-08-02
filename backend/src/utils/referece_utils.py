"""
Reference / citation extractor.

Schema columns involved (TWO redundant groups — each collapsed to ONE
canonical column):

    Group A — how many references THIS work cites:
        reference_count           - Number of references cited by the publication.
        referenced_works_count    - OpenAlex referenced works count.
        -> canonical: "reference_count_clean"

   Group B — how many times THIS work has been cited BY others:

    citation_count
    -> canonical: citation_count_clean

   
Both count groups follow the same rule: prefer the first populated value in
priority order, canonical name first. This means when a row already carries
a value in the canonical column, that value wins outright; the fallback
column is only consulted if the canonical one is empty.
"""

from __future__ import annotations


from typing import Any, Mapping

import pandas as pd

from utils.column_resolve import first_present, is_present

__all__ = [
    "extract_references",
    "extract_references_by_doi",
    "extract_references_batch",
]


REFERENCE_COUNT_PRIORITY = ["reference_count"]

CITATION_COUNT_PRIORITY = ["citation_count"]


def _parse_int(value: Any) -> int | None:
    if not is_present(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def extract_references(record: Mapping[str, Any]) -> dict:
    """
    Core single-record extractor.

    Args:
        record: one row of data (dict or pandas Series).

    Returns:
    {
        "reference_count_clean": int | None,
        "reference_count_source": str | None,
        "citation_count_clean": int | None,
        "citation_count_source": str | None,
    }
    """
    ref_count_val, ref_count_src = first_present(record, REFERENCE_COUNT_PRIORITY)
    citation_val, citation_by_src = first_present(record, CITATION_COUNT_PRIORITY)

    ref_count_clean = _parse_int(ref_count_val)

    return {
        "reference_count_clean": ref_count_clean,
        "reference_count_source": ref_count_src,
        "citation_count_clean": _parse_int(citation_val),
        "citation_count_source": citation_by_src,
        
        
    }


def extract_references_by_doi(
    df: pd.DataFrame, doi: str, doi_col: str = "doi"
) -> dict | None:
    """Extract reference/citation info for a single record identified by DOI."""
    matches = df[df[doi_col] == doi]
    if matches.empty:
        return None
    return extract_references(matches.iloc[0])


def extract_references_batch(
    df: pd.DataFrame, batch_size: int | None = None
) -> pd.DataFrame:
    """
    Apply extract_references across an entire DataFrame, optionally in chunks.
    """
    cols = [
        "reference_count_clean",
        "reference_count_source",
        "citation_count_clean",
        "citation_count_source",
    ]

    if batch_size is None:
        records = df.apply(extract_references, axis=1, result_type="expand")
        records.index = df.index
        return records

    chunks = []
    for start in range(0, len(df), batch_size):
        chunk = df.iloc[start : start + batch_size]
        result = chunk.apply(extract_references, axis=1, result_type="expand")
        result.index = chunk.index
        chunks.append(result)
    return pd.concat(chunks) if chunks else pd.DataFrame(columns=cols)
