"""Append repository-provenance rows to the final common dataset with low memory use."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEDUPLICATED_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_deduplicated.csv"
)
DEFAULT_FINAL_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_repository_append_summary.csv"
)


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def is_blank(value: Any) -> bool:
    return value is None or str(value).strip().casefold() in {
        "",
        "nan",
        "none",
        "null",
        "na",
        "n/a",
        "[]",
        "{}",
    }


def source_parts(value: Any) -> set[str]:
    return {part.strip() for part in str(value or "").split(";") if part.strip()}


def is_repository_review_row(row: dict[str, Any]) -> bool:
    return (
        "repositories_combined" in source_parts(row.get("source_dataset"))
        and str(row.get("ownership_decision", "")).strip().upper() == "REVIEW"
        and str(row.get("ownership_class", "")).strip().upper() == "REPOSITORY_ONLY_EVIDENCE"
    )


def publication_key(row: dict[str, Any]) -> str:
    doi = str(row.get("doi") or "").strip().casefold()
    if doi:
        return f"doi:{doi}"

    source_dataset = str(row.get("source_dataset") or "").strip()
    source_record_id = str(row.get("source_record_id") or "").strip()
    if source_dataset and source_record_id:
        return f"source_record:{source_dataset}|{source_record_id}"

    title = str(row.get("title") or "").strip().casefold()
    year = str(row.get("publication_year") or "").strip()
    authors = str(row.get("authors") or row.get("author_names") or "").strip().casefold()
    return f"title_year_author:{title}|{year}|{authors}"


def final_row(row: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    output = {field: row.get(field, "") for field in fieldnames}
    if "citation_count" in output and is_blank(output["citation_count"]):
        output["citation_count"] = row.get("cited_by_count", "")
    if "funder_identifier" in output and is_blank(output["funder_identifier"]):
        output["funder_identifier"] = row.get("funder_id", "")
    return output


def append_repository_records_to_final(
    *,
    deduplicated_csv: Path,
    final_csv: Path,
    output_csv: Path | None = None,
    summary_csv: Path = DEFAULT_SUMMARY_CSV,
) -> dict[str, int | str]:
    raise_csv_field_limit()
    target_csv = output_csv or final_csv
    temp_csv = target_csv.with_suffix(f"{target_csv.suffix}.tmp")
    seen_keys: set[str] = set()
    existing_rows = 0
    scanned_rows = 0
    appended_rows = 0
    skipped_duplicate_rows = 0

    with final_csv.open("r", encoding="utf-8", newline="") as final_file:
        reader = csv.DictReader(final_file)
        if reader.fieldnames is None:
            raise ValueError(f"Final CSV has no header: {final_csv}")
        fieldnames = list(reader.fieldnames)

        temp_csv.parent.mkdir(parents=True, exist_ok=True)
        with temp_csv.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in reader:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
                seen_keys.add(publication_key(row))
                existing_rows += 1

            with deduplicated_csv.open("r", encoding="utf-8", newline="") as dedup_file:
                dedup_reader = csv.DictReader(dedup_file)
                for row in dedup_reader:
                    scanned_rows += 1
                    if not is_repository_review_row(row):
                        continue

                    key = publication_key(row)
                    if key in seen_keys:
                        skipped_duplicate_rows += 1
                        continue

                    writer.writerow(final_row(row, fieldnames))
                    seen_keys.add(key)
                    appended_rows += 1

    temp_csv.replace(target_csv)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv.open("w", encoding="utf-8", newline="") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=["metric", "value"])
        writer.writeheader()
        for metric, value in {
            "deduplicated_csv": str(deduplicated_csv),
            "input_final_csv": str(final_csv),
            "output_csv": str(target_csv),
            "existing_final_rows": existing_rows,
            "deduplicated_rows_scanned": scanned_rows,
            "repository_rows_appended": appended_rows,
            "repository_duplicate_rows_skipped": skipped_duplicate_rows,
            "output_rows": existing_rows + appended_rows,
        }.items():
            writer.writerow({"metric": metric, "value": value})

    return {
        "existing_final_rows": existing_rows,
        "deduplicated_rows_scanned": scanned_rows,
        "repository_rows_appended": appended_rows,
        "repository_duplicate_rows_skipped": skipped_duplicate_rows,
        "output_rows": existing_rows + appended_rows,
        "output_csv": str(target_csv),
        "summary_csv": str(summary_csv),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Low-memory append of repository review rows into the final common CSV."
    )
    parser.add_argument("--deduplicated-csv", type=Path, default=DEFAULT_DEDUPLICATED_CSV)
    parser.add_argument("--final-csv", type=Path, default=DEFAULT_FINAL_CSV)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = append_repository_records_to_final(
        deduplicated_csv=args.deduplicated_csv,
        final_csv=args.final_csv,
        output_csv=args.output_csv,
        summary_csv=args.summary_csv,
    )
    print("Done.")
    print(f"  Existing final rows: {summary['existing_final_rows']:,}")
    print(f"  Repository rows appended: {summary['repository_rows_appended']:,}")
    print(f"  Output rows: {summary['output_rows']:,}")
    print(f"  Output CSV: {summary['output_csv']}")
    print(f"  Summary: {summary['summary_csv']}")


if __name__ == "__main__":
    main()
