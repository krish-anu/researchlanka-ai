"""Tests for local publication file adapters."""

import csv

from research_analytics.adapters.local_file import CSVAdapter


def test_csv_adapter_accepts_fields_larger_than_default_csv_limit(tmp_path) -> None:
    input_csv = tmp_path / "large_field.csv"
    large_abstract = "A" * 200_000
    with input_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "abstract"])
        writer.writeheader()
        writer.writerow({"title": "Large metadata record", "abstract": large_abstract})

    records = list(CSVAdapter(input_csv).collect())

    assert len(records) == 1
    assert records[0]["title"] == "Large metadata record"
    assert records[0]["abstract"] == large_abstract
