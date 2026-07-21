from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

import logging
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.preprocessing.crossref_normalizer import reduce_work

CROSSREF_BASE_URL = "https://api.crossref.org"
USER_AGENT = "SriLankaCollector/1.0"

KEEP_TYPES = {
    "journal-article",
    "proceedings-article",
    "posted-content",
}

logger = logging.getLogger(__name__)


# shift to util?
def create_session(
    user_agent: str,
) -> requests.Session:

    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    session = requests.Session()

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount("https://", adapter)

    session.headers.update({"User-Agent": user_agent})

    return session


@dataclass
class CrossrefCollector:
    """Collect and normalize publication records from Crossref."""

    email: str | None = None
    timeout: tuple[int, int] = (10, 60)
    base_url: str = CROSSREF_BASE_URL
    user_agent: str = USER_AGENT
    session: requests.Session = field(init=False)
    keep_types: set[str] | None = field(default_factory=lambda: KEEP_TYPES.copy())

    def __post_init__(self) -> None:
        user_agent = self.user_agent

        if self.email:
            user_agent = f"{self.user_agent} (mailto:{self.email})"

        self.session = create_session(user_agent)

    def fetch_works(
        self,
        *,
        affiliation_query: str,
        filters: list[str] | None = None,
        rows: int = 100,
        cursor: str = "*",
    ) -> dict[str, Any]:

        params = {
            "query.affiliation": affiliation_query,
            "rows": rows,
        }
        if cursor:
            params["cursor"] = cursor

        if filters:
            params["filter"] = ",".join(filters)

        response = self.session.get(
            f"{self.base_url}/works",
            params=params,
            timeout=self.timeout,
        )

        if not response.ok:
            logger.error(
                "Crossref request failed: %s %s",
                response.status_code,
                response.text,
            )

        response.raise_for_status()

        return response.json()

    def iter_works(
        self,
        *,
        affiliation_query: str,
        filters: list[str] | None = None,
        rows: int = 100,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate over Crossref works with cursor pagination."""

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
