"""
Journal / venue extractor.

Schema columns involved (redundant group — collapsed to ONE canonical value):
    journal            - Journal name.
    container_title    - Journal, conference, book, or container title.
    source_name        - OpenAlex source name or journal/source title.

    -> canonical output column: "journal_clean"

These three columns represent the same underlying concept (what venue the
work was published in) but are populated inconsistently depending on
source_dataset: Crossref tends to populate container_title, OpenAlex
populates source_name, repositories/sljol often populate journal directly.
Rather than carrying three overlapping columns downstream, this extractor
resolves ONE canonical value per record using a fixed priority order, and
records which column it came from for auditability.

Non-redundant venue metadata (issn, issn_l, volume, issue, source_type) is
passed through unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from utils.column_resolve import clean_str, first_present

__all__ = [
    "extract_journal",
    "extract_journal_by_doi",
    "extract_journal_batch",
]

# Priority order for resolving the canonical journal name. Adjust here if a
# new source's population pattern warrants re-ordering — this is the single
# place that controls it.
JOURNAL_NAME_PRIORITY = ["journal"]


def extract_journal(record: Mapping[str, Any]) -> dict:
    """
    Core single-record extractor.

    Args:
        record: one row of data (dict or pandas Series).

    Returns:
        {
            "journal_clean": str | None,        # canonical, collapsed value
            "journal_name_source": str | None,  # which column it came from
            "issn": str | None,
            "issn_l": str | None,
            "volume": str | None,
            "issue": str | None,
            "source_type": str | None,
        }
    """
    raw_value, source_col = first_present(record, JOURNAL_NAME_PRIORITY)
    return {
        "journal_clean": clean_str(raw_value),
        "journal_name_source": source_col,
        "issn": clean_str(record.get("issn")),
        "issn_l": clean_str(record.get("issn_l")),
        "volume": clean_str(record.get("volume")),
        "issue": clean_str(record.get("issue")),
        "source_type": clean_str(record.get("source_type")),
    }


def extract_journal_by_doi(
    df: pd.DataFrame, doi: str, doi_col: str = "doi"
) -> dict | None:
    """Extract journal info for a single record identified by DOI."""
    matches = df[df[doi_col] == doi]
    if matches.empty:
        return None
    return extract_journal(matches.iloc[0])


def extract_journal_batch(
    df: pd.DataFrame, batch_size: int | None = None
) -> pd.DataFrame:
    """
    Apply extract_journal across an entire DataFrame, optionally in chunks.

    Returns:
        DataFrame indexed like df with columns: journal_clean,
        journal_name_source, issn, issn_l, volume, issue, source_type.
    """
    cols = [
        "journal_clean",
        "journal_name_source",
        "issn",
        "issn_l",
        "volume",
        "issue",
        "source_type",
    ]

    if batch_size is None:
        records = df.apply(extract_journal, axis=1, result_type="expand")
        records.index = df.index
        return records

    chunks = []
    for start in range(0, len(df), batch_size):
        chunk = df.iloc[start : start + batch_size]
        result = chunk.apply(extract_journal, axis=1, result_type="expand")
        result.index = chunk.index
        chunks.append(result)
    return pd.concat(chunks) if chunks else pd.DataFrame(columns=cols)
