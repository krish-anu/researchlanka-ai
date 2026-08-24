"""Crossref work normalization.

Flattens a raw Crossref ``/works`` payload down to ``CROSSREF_FIELDS`` -- the
stable subset the pipeline consumes -- using dotted paths so nested values
like ``issued.date-parts`` can be pulled without a chain of ``.get()`` calls
that raise on a missing branch.

Field names are kept in Crossref's own spelling (``DOI``, ``container-title``,
``is-referenced-by-count``); renaming onto the common schema happens later, in
``src/processing/map_to_common_schema.py``.
"""

from __future__ import annotations

from typing import Any


CROSSREF_FIELDS = [
    "reference-count",
    "publisher",
    "issue",
    "abstract",
    "DOI",
    "type",
    "is-referenced-by-count",
    "title",
    "volume",
    "author",
    "container-title",
    "URL",
    "ISSN",
    "issued.date-parts",
    "published.date-parts",
    "created.date-parts",
    "license",
    "page",
    "reference",
    "event.name",
    "event.location",
    "event.start.date-parts",
    "event.end.date-parts",
    "language",
    "editor",
    "funder",
    "article-number",
    "publisher-location",
    "event.acronym",
    "group-title",
    "subtype",
    "event.sponsor",
    "original-title",
    "subtitle",
]


def get_nested(value: dict[str, Any], dotted_key: str) -> Any:
    """Read a dotted Crossref path without raising on missing keys."""
    current: Any = value
    for key in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def reduce_work(work: dict[str, Any]) -> dict[str, Any]:
    """Flatten one raw Crossref work to the stable downstream field set."""
    return {field: get_nested(work, field) for field in CROSSREF_FIELDS}
