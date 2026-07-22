"""Adapters for user-uploaded local datasets."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pandas as pd

from research_analytics.adapters.base import SourceAdapter
from research_analytics.schema import map_to_standard_schema
from research_analytics.transformations import apply_transformations


class LocalFileAdapter(SourceAdapter):
    """Base adapter for local files with configurable column mapping."""

    def __init__(
        self,
        path: str | Path,
        *,
        column_mapping: dict[str, str] | None = None,
        source_name: str = "user_dataset",
        required_fields: tuple[str, ...] = ("title",),
        require_any_fields: tuple[str, ...] = ("doi", "authors", "publication_year", "source_record_id"),
        transformations: dict[str, dict[str, Any]] | None = None,
        adapter_version: str = "1.0",
        mapping_version: str = "1.0",
        encoding: str = "utf-8",
    ) -> None:
        self.path = Path(path)
        self.column_mapping = column_mapping or {}
        self.source_name = source_name
        self.required_fields = required_fields
        self.require_any_fields = require_any_fields
        self.transformations = transformations or {}
        self.adapter_version = adapter_version
        self.mapping_version = mapping_version
        self.encoding = encoding

    def connect(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Source file does not exist: {self.path}")
        if not self.path.is_file():
            raise ValueError(f"Source path is not a file: {self.path}")

    def transform(self, record: dict) -> dict:
        mapped = map_to_standard_schema(
            record,
            self.column_mapping,
            source_name=self.source_name,
            raw_filename=str(self.path),
            adapter_version=self.adapter_version,
            mapping_version=self.mapping_version,
        )
        return apply_transformations(mapped, self.transformations)

    def validate(self, record: dict) -> list[str]:
        errors = []
        for field in self.required_fields:
            if _is_blank(record.get(field)):
                errors.append(f"Missing required field: {field}")
        if self.require_any_fields and not any(
            not _is_blank(record.get(field)) for field in self.require_any_fields
        ):
            errors.append(
                "At least one identifying field is required: "
                + ", ".join(self.require_any_fields)
            )
        return errors


class CSVAdapter(LocalFileAdapter):
    """Collect records from a CSV file."""

    def __init__(
        self,
        path: str | Path,
        *,
        delimiter: str = ",",
        **kwargs: Any,
    ) -> None:
        super().__init__(path, **kwargs)
        self.delimiter = delimiter

    def collect(self) -> Iterator[dict]:
        with self.path.open(newline="", encoding=self.encoding) as csv_file:
            yield from csv.DictReader(csv_file, delimiter=self.delimiter)


class JSONAdapter(LocalFileAdapter):
    """Collect records from a JSON array, JSON object, JSONL, or NDJSON file."""

    def collect(self) -> Iterator[dict]:
        if self.path.suffix.lower() in {".jsonl", ".ndjson"}:
            with self.path.open(encoding=self.encoding) as jsonl_file:
                for line in jsonl_file:
                    if line.strip():
                        yield json.loads(line)
            return

        loaded = json.loads(self.path.read_text(encoding=self.encoding))
        if isinstance(loaded, list):
            yield from loaded
            return
        if isinstance(loaded, dict):
            records = loaded.get("records") or loaded.get("publications") or loaded.get("data")
            if isinstance(records, list):
                yield from records
                return
            yield loaded
            return
        raise ValueError(f"Unsupported JSON shape in {self.path}")


class ExcelAdapter(LocalFileAdapter):
    """Collect records from an Excel workbook."""

    def __init__(
        self,
        path: str | Path,
        *,
        sheet_name: str | int | None = None,
        header_row: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(path, **kwargs)
        self.sheet_name = sheet_name
        self.header_row = header_row

    def collect(self) -> Iterator[dict]:
        dataframe = pd.read_excel(
            self.path,
            sheet_name=0 if self.sheet_name is None else self.sheet_name,
            header=self.header_row,
        )
        for record in dataframe.to_dict(orient="records"):
            yield record


class XMLAdapter(LocalFileAdapter):
    """Collect records from XML using a configurable record tag/path."""

    def __init__(
        self,
        path: str | Path,
        *,
        record_path: str = "record",
        **kwargs: Any,
    ) -> None:
        super().__init__(path, **kwargs)
        self.record_path = record_path

    def collect(self) -> Iterator[dict]:
        root = ElementTree.parse(self.path).getroot()
        for element in root.findall(f".//{self.record_path}"):
            yield {child.tag: (child.text or "").strip() for child in element}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False
