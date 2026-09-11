"""Tests for low-memory repository append into the final dataset."""

import csv

from src.pipeline.add_repository_records_to_final import append_repository_records_to_final


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_append_repository_records_to_final_streams_review_rows(tmp_path):
    final_csv = tmp_path / "final.csv"
    deduplicated_csv = tmp_path / "deduplicated.csv"
    summary_csv = tmp_path / "summary.csv"
    fieldnames = [
        "source_dataset",
        "source_record_id",
        "doi",
        "title",
        "ownership_decision",
        "ownership_class",
        "citation_count",
        "funder_identifier",
    ]

    write_csv(
        final_csv,
        fieldnames,
        [
            {
                "source_dataset": "openalex",
                "source_record_id": "oa-1",
                "doi": "10.1000/owned",
                "title": "Owned",
                "ownership_decision": "INCLUDE",
                "ownership_class": "SL_DOMESTIC",
            }
        ],
    )
    write_csv(
        deduplicated_csv,
        fieldnames + ["cited_by_count", "funder_id"],
        [
            {
                "source_dataset": "repositories_combined",
                "source_record_id": "repo-1",
                "doi": "",
                "title": "Repository only",
                "ownership_decision": "REVIEW",
                "ownership_class": "REPOSITORY_ONLY_EVIDENCE",
                "cited_by_count": "3",
                "funder_id": "10.13039/test",
            },
            {
                "source_dataset": "repositories_combined",
                "source_record_id": "repo-2",
                "doi": "10.1000/owned",
                "title": "Duplicate DOI",
                "ownership_decision": "REVIEW",
                "ownership_class": "REPOSITORY_ONLY_EVIDENCE",
            },
            {
                "source_dataset": "sljol",
                "source_record_id": "sljol-1",
                "doi": "",
                "title": "Venue only",
                "ownership_decision": "REVIEW",
                "ownership_class": "SLJOL_VENUE_ONLY_EVIDENCE",
            },
        ],
    )

    summary = append_repository_records_to_final(
        deduplicated_csv=deduplicated_csv,
        final_csv=final_csv,
        summary_csv=summary_csv,
    )

    rows = read_csv(final_csv)
    assert [row["title"] for row in rows] == ["Owned", "Repository only"]
    assert rows[1]["citation_count"] == "3"
    assert rows[1]["funder_identifier"] == "10.13039/test"
    assert summary["repository_rows_appended"] == 1
    assert summary["repository_duplicate_rows_skipped"] == 1
    assert summary_csv.exists()
