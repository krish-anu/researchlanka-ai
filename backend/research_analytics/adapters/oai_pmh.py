"""Generic OAI-PMH adapter for repository metadata."""

from __future__ import annotations

from typing import Iterator

from src.collectors.oai_pmh_collector import OaiPmhCollector
from src.collectors.schema_mapping import map_oai_dc_record

from research_analytics.adapters.base import SourceAdapter
from research_analytics.schema import map_to_standard_schema


class OAIPMHAdapter(SourceAdapter):
    """Collect and transform OAI Dublin Core repository records."""

    def __init__(
        self,
        *,
        endpoint: str,
        source_name: str = "oai_pmh",
        max_records: int | None = None,
        timeout: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.source_name = source_name
        self.max_records = max_records
        self.collector = OaiPmhCollector(base_url=endpoint, timeout=timeout)

    def connect(self) -> None:
        # Fetching one record is the most portable OAI-PMH accessibility check.
        next(self.collector.iter_records(max_records=1), None)

    def collect(self) -> Iterator[dict]:
        yield from self.collector.iter_records(max_records=self.max_records)

    def transform(self, record: dict) -> dict:
        mapped = map_oai_dc_record(record, institution_id=self.source_name)
        return map_to_standard_schema(
            mapped,
            {
                "source_record_id": "source_record_id",
                "publication_type": "publication_type",
                "url": "source_url",
            },
            source_name=self.source_name,
        )

    def validate(self, record: dict) -> list[str]:
        return [] if record.get("title") else ["Missing required field: title"]
