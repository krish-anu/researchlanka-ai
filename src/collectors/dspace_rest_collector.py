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

import time
from dataclasses import dataclass
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session() -> requests.Session:
    """Session that retries dropped connections and transient 5xx.

    Several of these hosts (uwu especially) close the connection part-way
    through a long harvest -- ``RemoteDisconnected`` rather than an HTTP
    error -- which previously ended the run outright. Matches the retry
    strategy already used by the OpenAlex and Crossref collectors.
    """

    retry_strategy = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@dataclass
class DspaceRestCollector:
    """Harvest items from a DSpace 7/8 REST API (/server/api base URL)."""

    api_base_url: str
    timeout: int = 30
    page_size: int = 100
    delay: float = 0.3
    verify_ssl: bool = True
    session: requests.Session | None = None
    # The discover endpoint returns metadata only. ``owningCollection``
    # adds the department/faculty that owns each item -- information the
    # Dublin Core fields never carry -- and ``bundles/bitstreams`` adds
    # the file listing (ORIGINAL = the PDF, TEXT = DSpace's extracted
    # full text). Both are opt-out because they enlarge every response.
    embeds: tuple[str, ...] = ("owningCollection",)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_session()
        self.api_base_url = self.api_base_url.rstrip("/")

    def _fetch_page(self, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"dsoType": "item", "page": page, "size": self.page_size}
        if self.embeds:
            params["embed"] = ",".join(self.embeds)
        response = self.session.get(
            f"{self.api_base_url}/discover/search/objects",
            params=params,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _parse_files(embedded: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten the embedded bundle/bitstream tree into a file list."""

        bundles = (embedded.get("bundles") or {}).get("_embedded", {}).get("bundles", [])
        files: list[dict[str, Any]] = []
        for bundle in bundles:
            if not isinstance(bundle, dict):
                continue
            bundle_name = bundle.get("name")
            # LICENSE/THUMBNAIL bundles are boilerplate, not research content.
            if bundle_name in {"LICENSE", "THUMBNAIL"}:
                continue
            bitstreams = (
                (bundle.get("_embedded") or {})
                .get("bitstreams", {})
                .get("_embedded", {})
                .get("bitstreams", [])
            )
            for bitstream in bitstreams:
                if not isinstance(bitstream, dict):
                    continue
                content = ((bitstream.get("_links") or {}).get("content") or {}).get("href")
                files.append(
                    {
                        "bundle": bundle_name,
                        "name": bitstream.get("name"),
                        "size_bytes": bitstream.get("sizeBytes"),
                        "url": content,
                    }
                )
        return files

    @classmethod
    def _parse_item(cls, indexable_object: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            field: [entry.get("value") for entry in entries if entry.get("value")]
            for field, entries in (indexable_object.get("metadata") or {}).items()
        }
        embedded = indexable_object.get("_embedded") or {}
        owning_collection = embedded.get("owningCollection")
        if not isinstance(owning_collection, dict):
            owning_collection = {}

        item = {
            "uuid": indexable_object.get("uuid"),
            "name": indexable_object.get("name"),
            "handle": indexable_object.get("handle"),
            "last_modified": indexable_object.get("lastModified"),
            "withdrawn": indexable_object.get("withdrawn"),
            "metadata": metadata,
        }
        if owning_collection:
            item["collection"] = owning_collection.get("name")
            item["collection_uuid"] = owning_collection.get("uuid")
            item["collection_handle"] = owning_collection.get("handle")
        if "bundles" in embedded:
            item["files"] = cls._parse_files(embedded)
        return item

    def total_items(self) -> int | None:
        payload = self._fetch_page(0)
        return (
            payload.get("_embedded", {})
            .get("searchResult", {})
            .get("page", {})
            .get("totalElements")
        )

    def iter_items(self, *, max_records: int | None = None) -> Iterator[dict[str, Any]]:
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
                if max_records is not None and records_seen >= max_records:
                    return
                records_seen += 1
                yield self._parse_item(indexable)

            page_info = search_result.get("page", {})
            total_pages = page_info.get("totalPages")
            page += 1
            if total_pages is not None and page >= total_pages:
                return
            if self.delay:
                time.sleep(self.delay)
