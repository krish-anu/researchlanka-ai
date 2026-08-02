"""Load publication record files into PostgreSQL."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Iterator
from itertools import islice
from pathlib import Path
from typing import Any

from src.database.connection import get_connection
from src.database.loader import load_final_publications


SUPPORTED_FORMATS = ("auto", "csv", "json", "jsonl")
DEFAULT_BATCH_SIZE = 1_000


def iter_record_file(path: Path, *, file_format: str = "auto") -> Iterator[dict[str, Any]]:
    """Yield publication records from a CSV, JSON array, or JSON Lines file."""

    selected_format = detect_format(path, file_format)
    if selected_format == "csv":
        yield from iter_csv_records(path)
        return
    if selected_format == "json":
        yield from iter_json_records(path)
        return
    if selected_format == "jsonl":
        yield from iter_jsonl_records(path)
        return
    raise ValueError(f"Unsupported input format: {file_format}")


def detect_format(path: Path, requested_format: str = "auto") -> str:
    """Return a supported file format from a user request and filename."""

    normalized = requested_format.casefold()
    if normalized != "auto":
        if normalized not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported input format: {requested_format}")
        return normalized

    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    raise ValueError(
        "Could not infer input format. Use --format csv, --format json, or --format jsonl."
    )


def iter_csv_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return
        for row in reader:
            yield {key: value for key, value in row.items() if key is not None}


def iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        for index, item in enumerate(payload, start=1):
            yield ensure_record(item, record_label=f"record {index}")
        return

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        for index, item in enumerate(payload["records"], start=1):
            yield ensure_record(item, record_label=f"records[{index - 1}]")
        return

    raise ValueError("JSON input must be a list of records or an object with a records list.")


def iter_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            yield ensure_record(json.loads(text), record_label=f"line {line_number}")


def ensure_record(value: Any, *, record_label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected {record_label} to be a JSON object.")
    return value


def chunked(records: Iterable[dict[str, Any]], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    """Yield records in fixed-size batches."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    iterator = iter(records)
    while True:
        batch = list(islice(iterator, batch_size))
        if not batch:
            return
        yield batch


def load_record_file(
    path: Path,
    *,
    file_format: str = "auto",
    database_url: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ensure_schema: bool = True,
    limit: int | None = None,
) -> int:
    """Load a record file into PostgreSQL in batches and return loaded row count."""

    records: Iterable[dict[str, Any]] = iter_record_file(path, file_format=file_format)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater.")
        records = islice(records, limit)

    connection = get_connection(database_url)
    try:
        total = 0
        for batch_number, batch in enumerate(chunked(records, batch_size), start=1):
            loaded = load_final_publications(
                batch,
                connection=connection,
                ensure_schema=ensure_schema and batch_number == 1,
            )
            connection.commit()
            total += loaded
        return total
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load CSV, JSON, or JSONL publication records into PostgreSQL.",
    )
    parser.add_argument("path", type=Path, help="Input CSV, JSON, or JSONL file.")
    parser.add_argument(
        "--format",
        choices=SUPPORTED_FORMATS,
        default="auto",
        help="Input file format. Defaults to inferring from the filename.",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL. Defaults to DATABASE_URL from .env or the project default.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of records to upsert per transaction. Defaults to {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Load only the first N records, useful for smoke tests.",
    )
    parser.add_argument(
        "--no-ensure-schema",
        action="store_true",
        help="Skip applying pending database migrations before loading.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        loaded = load_record_file(
            args.path,
            file_format=args.format,
            database_url=args.database_url,
            batch_size=args.batch_size,
            ensure_schema=not args.no_ensure_schema,
            limit=args.limit,
        )
    except Exception as exc:
        raise SystemExit(f"Failed to load records: {exc}") from exc

    print(f"Loaded {loaded} records into PostgreSQL.")


if __name__ == "__main__":
    main(sys.argv[1:])
