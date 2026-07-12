"""Tests for CSV conversion functionality."""

import json

import pytest
import pandas as pd

from scripts.jsonl_to_csv import convert_to_csv


def test_convert_to_csv_basic(tmp_path):
    """Test basic JSONL to CSV conversion."""
    # Create test JSONL file
    jsonl_file = tmp_path / "test.jsonl"
    records = [
        {"DOI": "10.1111/test", "title": "Paper 1", "year": 2024},
        {"DOI": "10.2222/test", "title": "Paper 2", "year": 2023},
        {"DOI": "10.3333/test", "title": "Paper 3", "year": 2022},
    ]

    with jsonl_file.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    # Convert
    csv_file = tmp_path / "output.csv"
    total = convert_to_csv(jsonl_file, csv_file)

    # Verify
    assert total == 3
    assert csv_file.exists()

    df = pd.read_csv(csv_file)
    assert len(df) == 3
    assert list(df.columns) == ["DOI", "title", "year"]
    assert df.iloc[0]["DOI"] == "10.1111/test"


def test_convert_to_csv_chunked(tmp_path):
    """Test JSONL to CSV with chunking."""
    # Create test JSONL file with many records
    jsonl_file = tmp_path / "test.jsonl"
    records = [{"id": i, "value": f"record_{i}"} for i in range(25)]

    with jsonl_file.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    # Convert with small chunk size
    csv_file = tmp_path / "output.csv"
    total = convert_to_csv(jsonl_file, csv_file, chunksize=5)

    assert total == 25

    df = pd.read_csv(csv_file)
    assert len(df) == 25


def test_convert_to_csv_file_not_found(tmp_path):
    """Test error when input file doesn't exist."""
    nonexistent = tmp_path / "nonexistent.jsonl"
    output = tmp_path / "output.csv"

    with pytest.raises(FileNotFoundError):
        convert_to_csv(nonexistent, output)


def test_convert_to_csv_overwrites_existing(tmp_path):
    """Test that conversion overwrites existing CSV."""
    jsonl_file = tmp_path / "test.jsonl"
    csv_file = tmp_path / "output.csv"

    # Create existing CSV
    csv_file.write_text("old,data\n1,2\n")

    # Create new JSONL
    records = [
        {"a": 1, "b": 2},
        {"a": 3, "b": 4},
    ]
    with jsonl_file.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    # Convert
    convert_to_csv(jsonl_file, csv_file)

    # Verify old data is gone
    df = pd.read_csv(csv_file)
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_convert_to_csv_empty_jsonl(tmp_path):
    """Test conversion of empty JSONL file."""
    jsonl_file = tmp_path / "empty.jsonl"
    jsonl_file.write_text("")

    csv_file = tmp_path / "output.csv"
    total = convert_to_csv(jsonl_file, csv_file)

    assert total == 0


def test_convert_to_csv_preserves_types(tmp_path):
    """Test that CSV preserves data types."""
    jsonl_file = tmp_path / "test.jsonl"
    records = [
        {"id": 1, "title": "Test", "value": 123.45, "active": True},
        {"id": 2, "title": "Another", "value": 678.90, "active": False},
    ]

    with jsonl_file.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    csv_file = tmp_path / "output.csv"
    convert_to_csv(jsonl_file, csv_file)

    df = pd.read_csv(csv_file)
    assert df["id"].dtype in [int, "int64"]
    assert df["value"].dtype in [float, "float64"]
