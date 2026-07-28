"""Tests for source-level publication count comparison."""

import pandas as pd
import pytest

from src.quality.compare_publication_counts import (
    compare_publication_counts,
    default_input_paths,
    estimate_unique_publications,
    write_publication_count_report,
)


def test_compare_publication_counts_uses_doi_when_coverage_is_high(tmp_path):
    openalex_csv = tmp_path / "openalex_sri_lanka_works.csv"
    openalex_csv.write_text(
        "openalex_id,doi,title,publication_year\n"
        "W1,10.1000/A,Shared DOI,2024\n"
        "W2,https://doi.org/10.1000/a,Shared DOI duplicate,2024\n"
        "W3,,No DOI Paper,2024\n"
        "W4,10.1000/B,Unique DOI,2025\n",
        encoding="utf-8",
    )

    report = compare_publication_counts({"openalex": openalex_csv})

    row = report.iloc[0]
    assert row["source_dataset"] == "openalex"
    assert row["total_records"] == 4
    assert row["total_columns"] == 4
    assert row["doi_non_missing"] == 3
    assert row["doi_coverage_pct"] == 75.0
    assert row["unique_doi_count"] == 2
    assert row["duplicate_doi_values"] == 1
    assert row["duplicate_doi_records"] == 2
    assert row["estimated_unique_publications"] == 3
    assert row["estimation_method"] == "unique_doi + no_doi_records"


def test_compare_publication_counts_uses_titles_when_doi_coverage_is_low(tmp_path):
    repository_csv = tmp_path / "repositories_combined.csv"
    repository_csv.write_text(
        "source_record_id,doi,title,publication_year\n"
        "r1,,Same Local Title,2024\n"
        "r2,,same local title,2024\n"
        "r3,10.1000/local,DOI Paper,2024\n"
        "r4,,Another Local Title,2025\n",
        encoding="utf-8",
    )

    report = compare_publication_counts({"repositories_combined": repository_csv})

    row = report.iloc[0]
    assert row["total_records"] == 4
    assert row["doi_non_missing"] == 1
    assert row["doi_coverage_pct"] == 25.0
    assert row["title_non_missing"] == 4
    assert row["unique_title_count"] == 3
    assert row["duplicate_title_values"] == 1
    assert row["duplicate_title_records"] == 2
    assert row["estimated_unique_publications"] == 3
    assert row["estimation_method"] == "unique_normalized_titles"


def test_write_publication_count_report(tmp_path):
    report = pd.DataFrame(
        [
            {
                "source_dataset": "crossref",
                "total_records": 2,
                "estimated_unique_publications": 2,
            }
        ]
    )
    output_csv = tmp_path / "nested" / "publication_counts_by_source.csv"

    written = write_publication_count_report(report, output_csv)

    assert written == output_csv
    saved = pd.read_csv(output_csv)
    assert saved.loc[0, "source_dataset"] == "crossref"
    assert saved.loc[0, "total_records"] == 2


def test_default_input_paths_requires_expected_files(tmp_path):
    with pytest.raises(FileNotFoundError) as exc_info:
        default_input_paths(tmp_path)

    assert "openalex_sri_lanka_works.csv" in str(exc_info.value)


def test_estimate_unique_publications_handles_empty_source():
    estimated, method = estimate_unique_publications(
        total_records=0,
        doi_stats={
            "non_missing": 0,
            "unique_count": 0,
            "duplicate_values": 0,
            "duplicate_records": 0,
        },
        title_stats={
            "non_missing": 0,
            "unique_count": 0,
            "duplicate_values": 0,
            "duplicate_records": 0,
        },
    )

    assert estimated == 0
    assert method == "no_records"
