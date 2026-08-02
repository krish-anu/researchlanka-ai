"""
Publisher extractor.

Schema columns involved:
    publisher            - Publishing organization.
    publisher_location    - Publisher location.

These two are not redundant with each other (name vs location), so no
collapsing is needed here — this module simply cleans and validates them,
and exposes both a single-record and a batch interface so it can be reused
anywhere: row-by-row during ingestion, DOI lookups, or bulk DataFrame passes.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from utils.column_resolve import clean_str

__all__ = [
    "extract_publisher",
    "extract_publisher_by_doi",
    "extract_publisher_batch",
]


def extract_publisher(record: Mapping[str, Any]) -> dict:
    """
    Core single-record extractor. Works on a dict, a pandas Series (df.loc[i]),
    or anything Mapping-like with .get().

    Args:
        record: one row of data with (at least) 'publisher' and
                'publisher_location' keys.

    Returns:
        {
            "publisher": str | None,
            "publisher_location": str | None,
        }
    """
    return {
        "publisher": clean_str(record.get("publisher")),
    }


def extract_publisher_by_doi(
    df: pd.DataFrame, doi: str, doi_col: str = "doi"
) -> dict | None:
    """
    Convenience lookup: extract publisher info for a single record identified
    by DOI. Returns None if the DOI isn't found in df.

    Useful for on-demand / interactive lookups without having to run a full
    batch pass first.
    """
    matches = df[df[doi_col] == doi]
    if matches.empty:
        return None
    return extract_publisher(matches.iloc[0])


def extract_publisher_batch(
    df: pd.DataFrame, batch_size: int | None = None
) -> pd.DataFrame:
    """
    Apply extract_publisher across an entire DataFrame, optionally in chunks.

    Args:
        df: input DataFrame containing 'publisher' / 'publisher_location'.
        batch_size: if given, processes df in chunks of this many rows
                    (identical output to a single pass; useful for very large
                    datasets to keep memory/progress reporting manageable).

    Returns:
        DataFrame indexed like df with columns: publisher, publisher_location.
    """
    if batch_size is None:
        records = df.apply(extract_publisher, axis=1, result_type="expand")
        records.index = df.index
        return records

    chunks = []
    for start in range(0, len(df), batch_size):
        chunk = df.iloc[start : start + batch_size]
        result = chunk.apply(extract_publisher, axis=1, result_type="expand")
        result.index = chunk.index
        chunks.append(result)
    return (
        pd.concat(chunks)
        if chunks
        else pd.DataFrame(columns=["publisher", "publisher_location"])
    )
