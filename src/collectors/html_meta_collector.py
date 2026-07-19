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

import re
import time
from dataclasses import dataclass
from typing import Any, Iterator

import requests

HANDLE_LINK_RE = re.compile(r'href="([^"]*?/handle/[0-9.]+/\d+)"')
META_TAG_RE = re.compile(
    r'<meta\s+name="((?:DC|DCTERMS|citation)[.\w]*)"\s+content="([^"]*)"',
    re.IGNORECASE,
)


def _decode_entities(text: str) -> str:
    import html

    return html.unescape(text)


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
            self.session = requests.Session()
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

        meta: dict[str, list[str]] = {}
        for name, content in META_TAG_RE.findall(response.text):
            if not content:
                continue
            meta.setdefault(name, []).append(_decode_entities(content))

        if not meta:
            return None

        return {"handle_path": handle_path, "url": url, "meta": meta}

    def iter_items(self, *, max_records: int | None = None) -> Iterator[dict[str, Any]]:
        count = 0
        for handle_path in self.iter_handle_paths():
            if max_records is not None and count >= max_records:
                return
            item = self.fetch_item(handle_path)
            if item is not None:
                count += 1
                yield item
            if self.delay:
                time.sleep(self.delay)
