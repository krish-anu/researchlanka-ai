"""Tests for language normalization."""

import pandas as pd
import pytest

from src.pipeline.build_language_normalized_dataset import (
    build_language_normalized_dataset,
    normalize_language,
    normalize_language_column,
)


def test_normalize_language_handles_common_variants_and_blanks():
    assert normalize_language("en_US") == "en"
    assert normalize_language("si_lk") == "si"
    assert normalize_language("English") == "en"
    assert normalize_language(" FR ") == "fr"
    assert normalize_language("") == "unknown"
    assert normalize_language(pd.NA) == "unknown"


def test_normalize_language_column_replaces_language_in_place():
    df = pd.DataFrame({"language": ["en_US", "si_lk", "", "other"], "title": ["a", "b", "c", "d"]})

    normalized = normalize_language_column(df)

    assert normalized["language"].tolist() == ["en", "si", "unknown", "other"]
    assert normalized["title"].tolist() == ["a", "b", "c", "d"]


def test_normalize_language_column_requires_language_column():
    with pytest.raises(ValueError, match="language"):
        normalize_language_column(pd.DataFrame({"title": ["Missing language"]}))


def test_build_language_normalized_dataset_writes_output_summary_and_mapping(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "common_publications_final_2016_2026_language_normalized.csv"
    summary_csv = tmp_path / "common_publications_final_2016_2026_language_normalized_summary.csv"
    df = pd.DataFrame({"language": ["en_US", "si_lk", "", "English"], "title": ["a", "b", "c", "d"]})
    df.to_csv(input_csv, index=False)

    normalized = build_language_normalized_dataset(input_csv, output_csv, summary_csv)
    saved = pd.read_csv(output_csv, dtype="object")
    summary = pd.read_csv(summary_csv)
    mapping_csv = tmp_path / "common_publications_final_2016_2026_language_normalized_mapping.csv"

    assert normalized["language"].tolist() == ["en", "si", "unknown", "en"]
    assert saved["language"].tolist() == ["en", "si", "unknown", "en"]
    assert output_csv.exists()
    assert summary_csv.exists()
    assert mapping_csv.exists()
    assert summary.loc[summary["metric"] == "distinct_languages_after", "value"].iloc[0] == "3"
