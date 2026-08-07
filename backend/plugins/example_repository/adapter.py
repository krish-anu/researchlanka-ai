"""Example plugin adapter for a complex custom source."""

from __future__ import annotations

from typing import Iterable

from research_analytics.adapters.base import SourceAdapter
from research_analytics.adapters.registry import register_source
from research_analytics.schema import map_to_standard_schema


@register_source("example_repository")
class ExampleRepositoryAdapter(SourceAdapter):
    """Template adapter showing how users can plug in a custom source."""

    def __init__(self, records: list[dict] | None = None, **_: object) -> None:
        self.records = records or []

    def connect(self) -> None:
        return None

    def collect(self) -> Iterable[dict]:
        yield from self.records

    def transform(self, raw_record: dict) -> dict:
        return map_to_standard_schema(
            raw_record,
            {
                "recordId": "source_record_id",
                "paperTitle": "title",
                "creators": "authors",
                "year": "publication_year",
            },
            source_name="example_repository",
            adapter_version="1.0",
            mapping_version="1.0",
        )

    def validate(self, transformed_record: dict) -> list[str]:
        errors = []
        if not transformed_record.get("title"):
            errors.append("Missing required field: title")
        return errors
