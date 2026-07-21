"""Shared HTTP helpers for collector modules."""

from __future__ import annotations

from collections.abc import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_RETRY_STATUSES = (429, 500, 502, 503, 504)


def create_retry_session(
    *,
    user_agent: str | None = None,
    total_retries: int = 5,
    backoff_factor: float = 2,
    status_forcelist: Iterable[int] = DEFAULT_RETRY_STATUSES,
    allowed_methods: Iterable[str] = ("GET",),
    mount_http: bool = True,
) -> requests.Session:
    """Create a requests session with retry behavior for transient failures."""

    retry_strategy = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=tuple(status_forcelist),
        allowed_methods=tuple(allowed_methods),
        respect_retry_after_header=True,
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)

    if mount_http:
        session.mount("http://", adapter)

    if user_agent:
        session.headers.update({"User-Agent": user_agent})

    return session
