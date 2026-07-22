"""Generic OpenAlex adapter driven by country/year configuration."""

from __future__ import annotations

from typing import Any
from typing import Iterator

from src.collectors.openalex_collector import OpenAlexCollector, build_filters
from src.preprocessing.openalex_normalizer import work_to_row

from research_analytics.adapters.base import SourceAdapter
from research_analytics.schema import map_to_standard_schema


class OpenAlexAdapter(SourceAdapter):
    """Collect OpenAlex records for a configured country code and year range."""

    def __init__(
        self,
        *,
        country_code: str | None,
        start_year: int | None = None,
        end_year: int | None = None,
        email: str | None = None,
        api_key: str | None = None,
        per_page: int = 200,
        max_records: int | None = None,
    ) -> None:
        self.country_code = country_code
        self.start_year = start_year
        self.end_year = end_year
        self.per_page = per_page
        self.max_records = max_records
        self.collector = OpenAlexCollector(email=email, api_key=api_key)

    def connect(self) -> None:
        if not self.country_code:
            raise ValueError("OpenAlexAdapter requires project.country_code in configuration.")
        filters = [f"authorships.institutions.country_code:{self.country_code}"]
        filters = build_filters(filters, from_year=self.start_year, to_year=self.end_year)
        self.collector.fetch_works(filters=filters, cursor="*", per_page=1)

    def collect(self) -> Iterator[dict]:
        if not self.country_code:
            raise ValueError("OpenAlexAdapter requires project.country_code in configuration.")
        filters = [f"authorships.institutions.country_code:{self.country_code}"]
        filters = build_filters(filters, from_year=self.start_year, to_year=self.end_year)
        yielded = 0
        cursor: str | None = "*"
        seen_cursors: set[str] = set()
        while cursor:
            if cursor in seen_cursors:
                raise RuntimeError(f"OpenAlex pagination cursor repeated: {cursor}")
            seen_cursors.add(cursor)
            response = self.collector.fetch_works(
                filters=filters,
                cursor=cursor,
                per_page=self.per_page,
            )
            for work in _as_list(response.get("results")):
                if not isinstance(work, dict):
                    continue
                if self.max_records is not None and yielded >= self.max_records:
                    return
                yielded += 1
                yield work
            meta = response.get("meta", {})
            cursor = meta.get("next_cursor") if isinstance(meta, dict) else None

    def transform(self, record: dict) -> dict:
        row = work_to_row(record)
        return map_to_standard_schema(
            row,
            {
                "openalex_id": "publication_id",
                "type": "publication_type",
                "cited_by_count": "citation_count",
                "landing_page_url": "source_url",
            },
            source_name="openalex",
        )

    def validate(self, record: dict) -> list[str]:
        return [] if record.get("title") else ["Missing required field: title"]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
