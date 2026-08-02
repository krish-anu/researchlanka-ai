"""Tests for publication-year filtering."""

import pandas as pd
import pytest

from src.pipeline.build_year_filtered_dataset import (
    build_year_filtered_dataset,
    filter_by_publication_year,
    year_filter_counts,
)


def test_filter_by_publication_year_keeps_inclusive_range_only():
    df = pd.DataFrame(
        {
            "publication_year": ["2015", "2016", "2020", "2026", "2027", "", "unknown"],
            "title": ["before", "start", "middle", "end", "after", "blank", "invalid"],
        }
    )

    filtered = filter_by_publication_year(df, start_year=2016, end_year=2026)

    assert filtered["title"].tolist() == ["start", "middle", "end"]


def test_year_filter_counts_reports_dropped_groups():
    df = pd.DataFrame({"publication_year": ["2015", "2016", "2026", "2027", "", "unknown"]})

    counts = year_filter_counts(df, start_year=2016, end_year=2026)

    assert counts == {
        "input_rows": 6,
        "kept_rows": 2,
        "dropped_before_start_year": 1,
        "dropped_after_end_year": 1,
        "dropped_missing_or_invalid_year": 2,
    }


def test_filter_by_publication_year_rejects_invalid_range():
    df = pd.DataFrame({"publication_year": ["2020"]})

    with pytest.raises(ValueError, match="start_year"):
        filter_by_publication_year(df, start_year=2026, end_year=2016)


def test_build_year_filtered_dataset_writes_output_and_summary(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "common_publications_final_2016_2026.csv"
    summary_csv = tmp_path / "common_publications_final_2016_2026_summary.csv"
    df = pd.DataFrame(
        {
            "publication_year": ["2014", "2016", "2026", "2099"],
            "title": ["before", "start", "end", "after"],
        }
    )
    df.to_csv(input_csv, index=False)

    filtered = build_year_filtered_dataset(input_csv, output_csv, summary_csv)
    saved = pd.read_csv(output_csv, dtype="object")
    summary = pd.read_csv(summary_csv)

    assert filtered["title"].tolist() == ["start", "end"]
    assert saved["title"].tolist() == ["start", "end"]
    assert output_csv.exists()
    assert summary_csv.exists()
    assert summary.loc[summary["metric"] == "kept_rows", "value"].iloc[0] == "2"
