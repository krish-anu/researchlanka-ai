"""Crossref works collector, by DOI prefix.

Used to collect SLJOL (Sri Lanka Journals Online) metadata: sljol.info
itself WAF-blocks all scripted access (see registry -- we do not bypass
it), but every SLJOL article has a DOI under the NSF-registered prefix
10.4038, and Crossref's public REST API serves the same bibliographic
metadata openly. Coverage check 2026-07-20: 26,200 works under 10.4038
vs "25,506 articles" claimed on the SLJOL homepage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator

import requests

CROSSREF_BASE_URL = "https://api.crossref.org"


@dataclass
class CrossrefPrefixCollector:
    """Fetch all works registered under one DOI prefix."""

    prefix: str
    email: str | None = None  # for the Crossref polite pool
    rows: int = 500
    timeout: int = 60
    delay: float = 0.5
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()

    def total_works(self) -> int:
        params: dict[str, Any] = {"rows": 0}
        if self.email:
            params["mailto"] = self.email
        response = self.session.get(
            f"{CROSSREF_BASE_URL}/prefixes/{self.prefix}/works",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["total-results"]

    def iter_works(self, *, max_records: int | None = None) -> Iterator[dict[str, Any]]:
        """Yield raw Crossref work records using cursor pagination."""

        cursor = "*"
        records_seen = 0

        while cursor:
            params: dict[str, Any] = {"rows": self.rows, "cursor": cursor}
            if self.email:
                params["mailto"] = self.email

            response = self.session.get(
                f"{CROSSREF_BASE_URL}/prefixes/{self.prefix}/works",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            message = response.json()["message"]

            items = message.get("items", [])
            if not items:
                return

            for work in items:
                if max_records is not None and records_seen >= max_records:
                    return
                records_seen += 1
                yield work

            cursor = message.get("next-cursor")
            if self.delay:
                time.sleep(self.delay)
