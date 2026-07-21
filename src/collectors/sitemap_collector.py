"""Sitemap-based fallback discovery for repositories where OAI-PMH is
unavailable or blocked (see data/config/repositories.json notes for e.g.
Kelaniya, PGIM, UCSC).

This only discovers item URLs -- it does not extract metadata. Standard
DSpace sitemaps are a sitemap_index.xml pointing at several sitemap_N.xml
files, each listing <loc> URLs for individual /handle/... or /items/...
item pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests

from src.collectors.http import create_retry_session

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# DSpace item-page URL fragments, used to filter out non-item pages
# (community/collection browse pages, static pages, etc.) that also
# appear in some sitemaps.
ITEM_URL_MARKERS = ("/handle/", "/items/")


@dataclass
class SitemapCollector:
    """Discover item URLs for a repository via its sitemap(s)."""

    repository_url: str
    timeout: int = 30
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_retry_session()
        parsed = urlparse(self.repository_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

    def _fetch_xml(self, url: str) -> ElementTree.Element | None:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            return ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            return None

    def _locs(self, root: ElementTree.Element, tag: str) -> list[str]:
        return [
            loc.text.strip()
            for entry in root.findall(f"{SITEMAP_NS}{tag}")
            for loc in entry.findall(f"{SITEMAP_NS}loc")
            if loc.text
        ]

    def find_sitemap_entrypoints(self) -> list[str]:
        """Locate the top-level sitemap(s) for this repository."""

        for name in ("sitemap_index.xml", "sitemap.xml"):
            url = urljoin(self.origin + "/", name)
            root = self._fetch_xml(url)
            if root is not None:
                return [url]
        return []

    def iter_item_urls(self, *, max_urls: int | None = None) -> list[str]:
        """Return discovered item-page URLs, following nested sitemap indexes."""

        entrypoints = self.find_sitemap_entrypoints()
        if not entrypoints:
            return []

        to_visit = list(entrypoints)
        visited: set[str] = set()
        item_urls: list[str] = []

        while to_visit:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            root = self._fetch_xml(url)
            if root is None:
                continue

            child_sitemaps = self._locs(root, "sitemap")
            if child_sitemaps:
                to_visit.extend(s for s in child_sitemaps if s not in visited)
                continue

            for loc in self._locs(root, "url"):
                if any(marker in loc for marker in ITEM_URL_MARKERS):
                    item_urls.append(loc)
                    if max_urls is not None and len(item_urls) >= max_urls:
                        return item_urls

        return item_urls
