"""HTML meta-tag collector for legacy DSpace instances with a dead OAI
index and no REST API.

Route of last resort, used only where (a) the OAI record store is
verifiably empty even for GetRecord, (b) no sitemap exists, and (c) the
site declares no crawling restrictions (robots.txt 404) -- currently the
two University of Jaffna repositories. Item discovery walks the public
browse-by-title listing; metadata comes from the Dublin Core /
Google-Scholar ``<meta>`` tags DSpace embeds in every item page, so no
screen-scraping of visible HTML is involved.

Be polite: keep the delay at or above the default; these are small
university servers.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any, Iterator

import requests

from src.collectors.http import create_retry_session

HANDLE_LINK_RE = re.compile(r'href="([^"]*?/handle/[0-9.]+/\d+)"')
META_NAME_RE = re.compile(r"^(?:DC|DCTERMS|citation)[.\w]*$", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(1[5-9]\d{2}|20\d{2})")
DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = date.today().year


class _MetaTagParser(HTMLParser):
    """Extract Dublin Core and citation metadata from HTML <meta> tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "meta":
            return

        attr_map = {
            name.casefold(): value
            for name, value in attrs
            if name is not None and value is not None
        }
        meta_name = attr_map.get("name")
        content = attr_map.get("content")

        if not meta_name or not content or not META_NAME_RE.match(meta_name):
            return

        self.meta.setdefault(meta_name, []).append(html.unescape(content))


def _parse_meta_tags(page_html: str) -> dict[str, list[str]]:
    parser = _MetaTagParser()
    parser.feed(page_html)
    return parser.meta


def _first_existing(meta: dict[str, list[str]], *fields: str) -> list[str]:
    for field in fields:
        if meta.get(field):
            return meta[field]
    return []


def _publication_year(item: dict[str, Any]) -> int | None:
    meta = item.get("meta") or {}
    candidates = _first_existing(
        meta,
        "DCTERMS.issued",
        "citation_publication_date",
        "citation_date",
        "DC.date",
    )
    for value in candidates:
        match = YEAR_PATTERN.search(value)
        if match:
            return int(match.group(1))
    return None


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
class HtmlMetaCollector:
    """Enumerate item pages via /browse and parse their <meta> tags."""

    base_url: str  # e.g. http://repo.lib.jfn.ac.lk/ujrr
    timeout: int = 30
    page_size: int = 100
    delay: float = 0.5
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_retry_session()
        self.base_url = self.base_url.rstrip("/")
        match = re.match(r"(https?://[^/]+)(/.*)?", self.base_url)
        self.origin = match.group(1)
        self.context_path = match.group(2) or ""

    def iter_handle_paths(self) -> Iterator[str]:
        """Yield unique /handle/... paths from the browse-by-title listing."""

        seen: set[str] = set()
        offset = 0

        while True:
            response = self.session.get(
                f"{self.base_url}/browse",
                params={"type": "title", "rpp": self.page_size, "offset": offset},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return

            new_paths = []
            for link in HANDLE_LINK_RE.findall(response.text):
                # Links come prefixed with the webapp context (/ujrr, /med).
                path = link[len(self.context_path):] if self.context_path and link.startswith(self.context_path) else link
                if path not in seen:
                    seen.add(path)
                    new_paths.append(path)

            if not new_paths:
                return

            yield from new_paths
            offset += self.page_size
            if self.delay:
                time.sleep(self.delay)

    def fetch_item(self, handle_path: str) -> dict[str, Any] | None:
        """Fetch one item page and parse its embedded metadata tags."""

        url = f"{self.origin}{self.context_path}{handle_path}"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None

        meta = _parse_meta_tags(response.text)

        if not meta:
            return None

        return {"handle_path": handle_path, "url": url, "meta": meta}

    def iter_items(
        self,
        *,
        max_records: int | None = None,
        start_year: int | None = DEFAULT_START_YEAR,
        end_year: int | None = DEFAULT_END_YEAR,
    ) -> Iterator[dict[str, Any]]:
        count = 0
        for handle_path in self.iter_handle_paths():
            if max_records is not None and count >= max_records:
                return
            item = self.fetch_item(handle_path)
            if item is not None:
                if not _is_in_year_range(
                    item,
                    start_year=start_year,
                    end_year=end_year,
                ):
                    continue
                if max_records is not None and count >= max_records:
                    return
                count += 1
                yield item
            if self.delay:
                time.sleep(self.delay)
