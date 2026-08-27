from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
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


SRI_LANKA_COUNTRY_CODE = "LK"
SRI_LANKA_COUNTRY_NAMES = ("sri lanka", "srilanka", "ceylon")


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
    reduced = {field: get_nested(work, field) for field in CROSSREF_FIELDS}
    first_author = first_author_record(work)
    first_affiliations = author_affiliation_names(first_author)
    reduced.update(
        {
            "first_author_name": crossref_author_name(first_author),
            "first_author_affiliation": "; ".join(first_affiliations),
            "first_author_country": (
                SRI_LANKA_COUNTRY_CODE
                if first_author_is_from_sri_lanka(work)
                else ""
            ),
            "has_sri_lankan_participant": has_sri_lankan_affiliated_author(work),
            "keep_in_strict_sri_lanka_dataset": first_author_is_from_sri_lanka(work),
        }
    )
    return reduced


def first_author_record(work: dict[str, Any]) -> dict[str, Any] | None:
    """Return Crossref's first author object when present."""
    authors = work.get("author")
    if not isinstance(authors, list) or not authors:
        return None
    first = authors[0]
    return first if isinstance(first, dict) else None


def crossref_author_name(author: dict[str, Any] | None) -> str:
    """Return a display name for one Crossref author."""
    if not isinstance(author, dict) or not author:
        return ""
    if author.get("name"):
        return str(author["name"]).strip()
    parts = [author.get("given"), author.get("family")]
    return " ".join(str(part).strip() for part in parts if part).strip()


def author_affiliation_names(author: dict[str, Any] | None) -> list[str]:
    """Return publication-specific affiliation names for one Crossref author."""
    if not author:
        return []
    affiliations = author.get("affiliation")
    if not isinstance(affiliations, list):
        return []
    names: list[str] = []
    for affiliation in affiliations:
        if not isinstance(affiliation, dict):
            continue
        name = str(affiliation.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def first_author_is_from_sri_lanka(work: dict[str, Any]) -> bool:
    """Check whether the first Crossref author has a Sri Lankan affiliation."""
    return any(
        affiliation_is_sri_lankan(affiliation)
        for affiliation in author_affiliation_names(first_author_record(work))
    )


def has_sri_lankan_affiliated_author(work: dict[str, Any]) -> bool:
    """Check whether any Crossref author has a Sri Lankan affiliation."""
    authors = work.get("author")
    if not isinstance(authors, list):
        return False
    for author in authors:
        if not isinstance(author, dict):
            continue
        if any(
            affiliation_is_sri_lankan(name)
            for name in author_affiliation_names(author)
        ):
            return True
    return False


def affiliation_is_sri_lankan(value: Any) -> bool:
    """Resolve an affiliation string to Sri Lanka using country or registry evidence."""
    text = str(value or "").strip()
    if not text:
        return False
    normalized = _normalize_affiliation_key(text)
    if any(country_name in normalized for country_name in SRI_LANKA_COUNTRY_NAMES):
        return True
    return any(alias in normalized for alias in _sri_lankan_institution_alias_keys())


def _normalize_affiliation_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


@lru_cache(maxsize=1)
def _sri_lankan_institution_alias_keys() -> tuple[str, ...]:
    registry_path = _find_sri_lanka_institution_registry()
    if registry_path is None:
        return ()

    aliases: set[str] = set()
    with registry_path.open(newline="", encoding="utf-8") as registry_file:
        for row in csv.DictReader(registry_file):
            if str(row.get("country_code", "")).upper() != SRI_LANKA_COUNTRY_CODE:
                continue
            for column in ("preferred_name", "alternative_name"):
                alias = _normalize_affiliation_key(row.get(column) or "")
                if len(alias) > 4:
                    aliases.add(alias)
    return tuple(sorted(aliases, key=len, reverse=True))


def _find_sri_lanka_institution_registry() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "configurations" / "sri_lanka" / "institutions.csv"
        if candidate.exists():
            return candidate
    return None
