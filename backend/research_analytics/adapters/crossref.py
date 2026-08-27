"""Crossref source adapter."""

from __future__ import annotations

from typing import Iterator

from src.collectors.crossref_collector import CrossrefCollector

from research_analytics.adapters.base import SourceAdapter
from research_analytics.schema import map_to_standard_schema


class CrossrefAdapter(SourceAdapter):
    """Collect Crossref works through the common source-adapter interface."""

    def __init__(
        self,
        *,
        affiliation_query: str,
        email: str | None = None,
        filters: list[str] | None = None,
        max_records: int | None = None,
        rows: int = 100,
        require_first_author_lk: bool = True,
    ) -> None:
        self.affiliation_query = affiliation_query
        self.filters = filters
        self.max_records = max_records
        self.rows = rows
        self.require_first_author_lk = require_first_author_lk
        self.collector = CrossrefCollector(email=email)

    def connect(self) -> None:
        self.collector.fetch_works(
            affiliation_query=self.affiliation_query,
            filters=self.filters,
            rows=1,
        )

    def collect(self) -> Iterator[dict]:
        yield from self.collector.iter_works(
            affiliation_query=self.affiliation_query,
            filters=self.filters,
            rows=self.rows,
            max_records=self.max_records,
            require_first_author_lk=self.require_first_author_lk,
        )

    def transform(self, raw_record: dict) -> dict:
        return map_to_standard_schema(
            raw_record,
            {
                "source": "source_name",
                "source_id": "source_record_id",
                "year": "publication_year",
                "type": "publication_type",
                "url": "source_url",
            },
            source_name="crossref",
        )

    def validate(self, transformed_record: dict) -> list[str]:
        return [] if transformed_record.get("title") else ["Missing required field: title"]
