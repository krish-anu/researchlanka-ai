"""Tests for multi-value column normalization."""

import pandas as pd
import pytest

from src.pipeline.build_multivalue_normalized_dataset import (
    MULTI_VALUE_COLUMNS,
    build_multivalue_normalized_dataset,
    normalize_multivalue_cell,
    normalize_multivalue_columns,
    split_multivalue_cell,
)


def test_split_multivalue_cell_strips_empty_items():
    assert split_multivalue_cell(" A ; ; B;  C ") == ["A", "B", "C"]
    assert split_multivalue_cell("") == []
    assert split_multivalue_cell(pd.NA) == []


def test_normalize_multivalue_cell_deduplicates_and_applies_column_rules():
    assert normalize_multivalue_cell("keywords", " AI ; ai ; Machine Learning ") == "ai; machine learning"
    assert normalize_multivalue_cell("countries", "lk; LK; us") == "LK; US"
    assert normalize_multivalue_cell("authors", "A. Author; a. author; B. Author") == "A. Author; B. Author"


def test_normalize_multivalue_columns_requires_configured_columns():
    df = pd.DataFrame({"authors": ["A; B"]})

    with pytest.raises(ValueError, match="keywords"):
        normalize_multivalue_columns(df)


def test_build_multivalue_normalized_dataset_writes_output_items_and_summary(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "common_publications_final_2016_2026_multivalue_normalized.csv"
    items_csv = tmp_path / "publication_multivalue_items_2016_2026.csv"
    summary_csv = tmp_path / "common_publications_final_2016_2026_multivalue_normalized_summary.csv"

    row = {column: pd.NA for column in MULTI_VALUE_COLUMNS}
    row.update(
        {
            "source_record_id": "record-1",
            "doi": "10.1000/test",
            "authors": "A. Author; a. author; B. Author",
            "keywords": "AI; ai; ML",
            "countries": "lk; us",
            "source_dataset": "OpenAlex; Crossref",
        }
    )
    pd.DataFrame([row]).to_csv(input_csv, index=False)

    normalized, item_rows = build_multivalue_normalized_dataset(
        input_csv,
        output_csv,
        items_csv,
        summary_csv,
    )
    saved = pd.read_csv(output_csv, dtype="object")
    items = pd.read_csv(items_csv, dtype="object")
    details_csv = tmp_path / "common_publications_final_2016_2026_multivalue_normalized_details.csv"

    assert normalized.loc[0, "authors"] == "A. Author; B. Author"
    assert saved.loc[0, "keywords"] == "ai; ml"
    assert item_rows == len(items)
    assert set(items["column"]) >= {"authors", "keywords", "countries", "source_dataset"}
    assert output_csv.exists()
    assert items_csv.exists()
    assert summary_csv.exists()
    assert details_csv.exists()
