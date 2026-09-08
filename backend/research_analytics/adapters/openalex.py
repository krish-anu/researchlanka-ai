"""Generic OpenAlex adapter driven by country/year configuration."""

from __future__ import annotations

import logging
from typing import Any
from typing import Iterator

from src.collectors.openalex_collector import OpenAlexCollector, build_filters
from src.preprocessing.openalex_normalizer import detected_country_codes
from src.preprocessing.openalex_normalizer import has_sri_lankan_author
from src.preprocessing.openalex_normalizer import work_to_row

from research_analytics.adapters.base import SourceAdapter
from research_analytics.schema import map_to_standard_schema
from research_analytics.transformations import apply_transformations


logger = logging.getLogger(__name__)


DEFAULT_OPENALEX_COLUMN_MAPPING = {
    "openalex_id": "publication_id",
    "type": "publication_type",
    "cited_by_count": "citation_count",
    "landing_page_url": "source_url",
}


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
        strict_country_only: bool = False,
        retry_limit: int = 3,
        retry_backoff_seconds: float = 2.0,
        column_mapping: dict[str, str] | None = None,
        transformations: dict[str, dict[str, Any]] | None = None,
        source_name: str = "openalex",
        required_fields: tuple[str, ...] = ("title",),
        require_any_fields: tuple[str, ...] = (
            "doi",
            "authors",
            "publication_year",
            "source_record_id",
        ),
        adapter_version: str = "1.0",
        mapping_version: str = "1.0",
    ) -> None:
        self.country_code = country_code
        self.start_year = start_year
        self.end_year = end_year
        self.per_page = per_page
        self.max_records = max_records
        self.strict_country_only = strict_country_only
        self.column_mapping = {
            **DEFAULT_OPENALEX_COLUMN_MAPPING,
            **(column_mapping or {}),
        }
        self.transformations = transformations or {}
        self.source_name = source_name
        self.required_fields = required_fields
        self.require_any_fields = require_any_fields
        self.adapter_version = adapter_version
        self.mapping_version = mapping_version
        self.collector = OpenAlexCollector(
            email=email,
            api_key=api_key,
            retry_limit=retry_limit,
            retry_backoff_seconds=retry_backoff_seconds,
        )

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
        page_number = 0
        cursor: str | None = "*"
        seen_cursors: set[str] = set()
        logger.info(
            "OpenAlex collection started: country=%s years=%s-%s max_records=%s strict_country_only=%s",
            self.country_code,
            self.start_year or "*",
            self.end_year or "*",
            self.max_records if self.max_records is not None else "all",
            self.strict_country_only,
        )
        while cursor:
            if cursor in seen_cursors:
                raise RuntimeError(f"OpenAlex pagination cursor repeated: {cursor}")
            seen_cursors.add(cursor)
            page_number += 1
            logger.info("OpenAlex fetching page %s", page_number)
            response = self.collector.fetch_works(
                filters=filters,
                cursor=cursor,
                per_page=self.per_page,
            )
            results = _as_list(response.get("results"))
            page_yielded = 0
            page_skipped = 0
            for work in results:
                if not isinstance(work, dict):
                    continue
                if not self._matches_country_scope(work):
                    page_skipped += 1
                    continue
                if self.max_records is not None and yielded >= self.max_records:
                    logger.info("OpenAlex collection reached max_records=%s", self.max_records)
                    return
                yielded += 1
                page_yielded += 1
                yield work
            meta = response.get("meta", {})
            api_total = meta.get("count") if isinstance(meta, dict) else None
            logger.info(
                "OpenAlex page %s complete: fetched=%s yielded=%s skipped=%s total_yielded=%s api_total=%s",
                page_number,
                len(results),
                page_yielded,
                page_skipped,
                yielded,
                api_total if api_total is not None else "unknown",
            )
            cursor = meta.get("next_cursor") if isinstance(meta, dict) else None
        logger.info("OpenAlex collection complete: %s records", yielded)

    def _matches_country_scope(self, work: dict[str, Any]) -> bool:
        if not self.country_code:
            return False
        if self.country_code.upper() == "LK" and not has_sri_lankan_author(work):
            return False
        if self.country_code.upper() != "LK" and self.country_code.upper() not in detected_country_codes(work):
            return False
        if not self.strict_country_only:
            return True
        return detected_country_codes(work) == {self.country_code.upper()}

    def transform(self, record: dict) -> dict:
        row = work_to_row(record)
        mapped = map_to_standard_schema(
            row,
            self.column_mapping,
            source_name=self.source_name,
            adapter_version=self.adapter_version,
            mapping_version=self.mapping_version,
        )
        transformed = apply_transformations(mapped, self.transformations)
        transformed["raw_record"] = record
        provenance = dict(transformed.get("_provenance") or {})
        provenance["raw_record_format"] = "openalex_api_work"
        transformed["_provenance"] = provenance
        return transformed

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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False
