"""Tests for compare_dois functionality."""

import pytest
from pathlib import Path
from src.quality.compare_dois import load_dois


def test_load_dois_valid_csv(tmp_path):
    """Test loading DOIs from valid CSV."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("doi,title\n10.1234/test,Paper 1\n10.5678/test,Paper 2\n")

    df = load_dois(csv_file, "doi")

    assert len(df) == 2
    assert "doi_clean" in df.columns
    assert df["doi_clean"].iloc[0] == "10.1234/test"


def test_load_dois_with_urls(tmp_path):
    """Test loading DOIs that are URLs."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "DOI,title\n"
        "https://doi.org/10.1234/test,Paper 1\n"
        "https://doi.org/10.5678/test,Paper 2\n"
    )

    df = load_dois(csv_file, "DOI")

    assert len(df) == 2
    assert df["doi_clean"].iloc[0] == "10.1234/test"
    assert df["doi_clean"].iloc[1] == "10.5678/test"


def test_load_dois_filters_empty(tmp_path):
    """Test that empty/NaN DOIs are filtered out."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "doi,title\n"
        "10.1234/test,Paper 1\n"
        ",Paper 2\n"  # Empty DOI
        "10.5678/test,Paper 3\n"
    )

    df = load_dois(csv_file, "doi")

    assert len(df) == 2  # Only 2 valid DOIs
    assert all(df["doi_clean"].notna())


def test_load_dois_filters_invalid_values(tmp_path):
    """Test that malformed DOI values are filtered out."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "doi,title\n"
        "10.1234/test,Paper 1\n"
        "not-a-doi,Paper 2\n"
        "10.1/too-short,Paper 3\n"
    )

    df = load_dois(csv_file, "doi")

    assert len(df) == 1
    assert df["doi_clean"].iloc[0] == "10.1234/test"


def test_load_dois_file_not_found():
    """Test error when CSV file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        load_dois(Path("nonexistent.csv"), "doi")


def test_load_dois_column_not_found(tmp_path):
    """Test error when column doesn't exist."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("doi,title\n10.1234/test,Paper 1\n")

    with pytest.raises(ValueError) as exc_info:
        load_dois(csv_file, "missing_column")

    assert "missing_column" in str(exc_info.value)
    assert "Available:" in str(exc_info.value)


def test_load_dois_with_duplicates(tmp_path):
    """Test loading DOIs with duplicates."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "doi,title\n10.1234/test,Paper 1\n10.1234/test,Paper 2\n10.5678/test,Paper 3\n"
    )

    df = load_dois(csv_file, "doi")

    # All duplicates are preserved (not deduplicated here)
    assert len(df) == 3


def test_load_dois_case_normalization(tmp_path):
    """Test that DOIs are normalized to lowercase."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("doi,title\n10.1234/TEST,Paper 1\n10.5678/Example,Paper 2\n")

    df = load_dois(csv_file, "doi")

    assert df["doi_clean"].iloc[0] == "10.1234/test"
    assert df["doi_clean"].iloc[1] == "10.5678/example"


def test_load_dois_mixed_formats(tmp_path):
    """Test loading DOIs in mixed formats."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "doi,title\n"
        "10.1234/test,Paper 1\n"
        "https://doi.org/10.5678/test,Paper 2\n"
        "DOI: 10.9999/test,Paper 3\n"
    )

    df = load_dois(csv_file, "doi")

    assert len(df) == 3
    assert df["doi_clean"].iloc[0] == "10.1234/test"
    assert df["doi_clean"].iloc[1] == "10.5678/test"
    assert df["doi_clean"].iloc[2] == "10.9999/test"
