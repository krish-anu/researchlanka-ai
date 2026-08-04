"""Export serialization helpers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from src.api.constants import PUBLICATION_SUMMARY_FIELDS
from src.api.serializers import normalize_value


def publication_rows_to_jsonl(rows: list[dict[str, Any]]) -> bytes:
    payload = "".join(json.dumps(normalize_value(row), ensure_ascii=False) + "\n" for row in rows)
    return payload.encode("utf-8")


def publication_rows_to_csv(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PUBLICATION_SUMMARY_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: "; ".join(str(item) for item in value)
                if isinstance(value, list)
                else value
                for key, value in row.items()
            }
        )
    return buffer.getvalue().encode("utf-8")


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    fieldnames = sorted({field for row in rows for field in row}) or ["value"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(normalize_value(value), ensure_ascii=False)
                if isinstance(value, (dict, list))
                else normalize_value(value)
                for key, value in row.items()
            }
        )
    return buffer.getvalue().encode("utf-8")
