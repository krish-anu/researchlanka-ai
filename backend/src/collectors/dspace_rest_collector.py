"""DSpace 7/8 REST API collector.

Alternate harvest route for DSpace 7/8 instances whose OAI-PMH index is
stale/unbuilt (returns noRecordsMatch despite real content -- see
data/config/repositories.json top-level notes). The public discover
endpoint (/server/api/discover/search/objects?dsoType=item) serves full
item metadata without authentication, unlike /server/api/core/items
which returns 401 on these hosts.

Metadata comes back as qualified Dublin Core (dc.date.issued distinct
from dc.date.accessioned, etc.) -- richer than the flat oai_dc feed.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

import requests

from src.collectors.http import create_retry_session

YEAR_PATTERN = re.compile(r"(1[5-9]\d{2}|20\d{2})")
DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = date.today().year


def _extract_year(values: list[str] | None) -> int | None:
    for value in values or []:
        match = YEAR_PATTERN.search(value)
        if match:
            return int(match.group(1))
    return None


def _publication_year(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") or {}
    candidates = (
        metadata.get("dc.date.issued")
        or metadata.get("dcterms.issued")
        or metadata.get("dc.date")
        or []
    )
    return _extract_year(candidates)


def _is_in_year_range(
    item: dict[str, Any],
    *,
    start_year: int | None,
    end_year: int | None,
) -> bool:
    if start_year is None and end_year is None:
        return True
    year = _publication_year(item)
    if year is None:
        return False
    effective_start_year = max(start_year or DEFAULT_START_YEAR, DEFAULT_START_YEAR)
    if year < effective_start_year:
        return False
    effective_end_year = min(end_year or DEFAULT_END_YEAR, DEFAULT_END_YEAR)
    if year > effective_end_year:
        return False
    return True


@dataclass
class DspaceRestCollector:
    """Harvest items from a DSpace 7/8 REST API (/server/api base URL)."""

    api_base_url: str
    timeout: int = 30
    page_size: int = 100
    delay: float = 0.3
    verify_ssl: bool = True
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_retry_session()
        self.api_base_url = self.api_base_url.rstrip("/")

    def _fetch_page(self, page: int) -> dict[str, Any]:
        response = self.session.get(
            f"{self.api_base_url}/discover/search/objects",
            params={"dsoType": "item", "page": page, "size": self.page_size},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _parse_item(indexable_object: dict[str, Any]) -> dict[str, Any]:
        metadata = {}

        for field, entries in (indexable_object.get("metadata") or {}).items():
            values = [entry.get("value") for entry in entries if entry.get("value")]

            if values:
                metadata[field] = values

        return {
            "uuid": indexable_object.get("uuid"),
            "name": indexable_object.get("name"),
            "handle": indexable_object.get("handle"),
            "last_modified": indexable_object.get("lastModified"),
            "withdrawn": indexable_object.get("withdrawn"),
            "metadata": metadata,
        }

    def total_items(self) -> int | None:
        payload = self._fetch_page(0)
        return (
            payload.get("_embedded", {})
            .get("searchResult", {})
            .get("page", {})
            .get("totalElements")
        )

    def iter_items(
        self,
        *,
        max_records: int | None = None,
        start_year: int | None = DEFAULT_START_YEAR,
        end_year: int | None = DEFAULT_END_YEAR,
    ) -> Iterator[dict[str, Any]]:
        """Yield every item, paging through the discover endpoint."""

        page = 0
        records_seen = 0

        while True:
            payload = self._fetch_page(page)
            search_result = payload.get("_embedded", {}).get("searchResult", {})
            objects = search_result.get("_embedded", {}).get("objects", [])

            if not objects:
                return

            for wrapper in objects:
                indexable = wrapper.get("_embedded", {}).get("indexableObject")
                if not indexable:
                    continue
                item = self._parse_item(indexable)
                if not _is_in_year_range(
                    item,
                    start_year=start_year,
                    end_year=end_year,
                ):
                    continue
                if max_records is not None and records_seen >= max_records:
                    return
                records_seen += 1
                yield item

            page_info = search_result.get("page", {})
            total_pages = page_info.get("totalPages")
            page += 1
            if total_pages is not None and page >= total_pages:
                return
            if self.delay:
                time.sleep(self.delay)
