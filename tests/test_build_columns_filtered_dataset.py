"""Tests for creating the columns-filtered publication dataset."""

import pandas as pd
import pytest

from src.pipeline.build_columns_filtered_dataset import (
    build_columns_filtered_dataset,
    filter_to_finalized_columns,
)
from src.pipeline.build_final_common_dataset import FINAL_MAIN_COLUMNS


def test_filter_to_finalized_columns_keeps_only_final_columns_in_order():
    df = pd.DataFrame([{column: column for column in FINAL_MAIN_COLUMNS}])
    df["temporary_analysis_column"] = "drop me"

    filtered = filter_to_finalized_columns(df)

    assert list(filtered.columns) == FINAL_MAIN_COLUMNS
    assert "temporary_analysis_column" not in filtered.columns


def test_filter_to_finalized_columns_requires_finalized_schema():
    df = pd.DataFrame([{column: column for column in FINAL_MAIN_COLUMNS if column != "doi"}])

    with pytest.raises(ValueError, match="doi"):
        filter_to_finalized_columns(df)


def test_build_columns_filtered_dataset_writes_output_and_summary(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "common_publications_columns_filtered.csv"
    summary_csv = tmp_path / "common_publications_columns_filtered_summary.csv"

    df = pd.DataFrame([{column: column for column in FINAL_MAIN_COLUMNS}])
    df["temporary_analysis_column"] = "drop me"
    df.to_csv(input_csv, index=False)

    filtered = build_columns_filtered_dataset(input_csv, output_csv, summary_csv)
    saved = pd.read_csv(output_csv, dtype="object")
    summary = pd.read_csv(summary_csv)

    assert list(filtered.columns) == FINAL_MAIN_COLUMNS
    assert list(saved.columns) == FINAL_MAIN_COLUMNS
    assert output_csv.exists()
    assert summary_csv.exists()
    assert summary.loc[summary["metric"] == "output_columns", "value"].iloc[0] == str(
        len(FINAL_MAIN_COLUMNS)
    )
