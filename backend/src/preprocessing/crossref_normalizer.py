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

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.preprocessing.ownership import (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    DECISION_EXCLUDE,
    DECISION_INCLUDE,
    DECISION_REVIEW,
    OWNERSHIP_POLICY_VERSION,
    OwnershipDecision,
)

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
FOREIGN_COUNTRY_NAMES = {
    "australia": "AU",
    "canada": "CA",
    "china": "CN",
    "france": "FR",
    "germany": "DE",
    "india": "IN",
    "japan": "JP",
    "malaysia": "MY",
    "singapore": "SG",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "united states": "US",
    "usa": "US",
}


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
            **classify_sri_lanka_ownership(work),
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


def corresponding_author_records(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explicit Crossref corresponding/project-lead records if present.

    Crossref does not consistently expose corresponding authors. This accepts
    only explicit flags/roles present in harvested or enriched payloads.
    """
    authors = work.get("author")
    if not isinstance(authors, list):
        return []
    records: list[dict[str, Any]] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        role = str(author.get("role") or author.get("contributor_role") or "").casefold()
        if (
            author.get("is_corresponding") is True
            or author.get("corresponding") is True
            or role in {"corresponding", "corresponding_author", "project_lead", "lead"}
        ):
            records.append(author)
    return records


def author_country_codes(author: dict[str, Any] | None) -> set[str]:
    countries: set[str] = set()
    for affiliation in author_affiliation_names(author):
        countries.update(affiliation_country_codes(affiliation))
    return countries


def all_author_country_codes(work: dict[str, Any]) -> set[str]:
    countries: set[str] = set()
    authors = work.get("author")
    if not isinstance(authors, list):
        return countries
    for author in authors:
        if isinstance(author, dict):
            countries.update(author_country_codes(author))
    return countries


def classify_sri_lanka_ownership(work: dict[str, Any]) -> dict[str, Any]:
    """Classify Crossref ownership without treating first author as proof."""
    all_codes = all_author_country_codes(work)
    first_codes = author_country_codes(first_author_record(work))
    corresponding_codes: set[str] = set()
    for author in corresponding_author_records(work):
        corresponding_codes.update(author_country_codes(author))

    has_lk = SRI_LANKA_COUNTRY_CODE in all_codes
    has_foreign = bool(all_codes - {SRI_LANKA_COUNTRY_CODE})
    corresponding = tuple(sorted(corresponding_codes))

    if corresponding_codes:
        if corresponding_codes == {SRI_LANKA_COUNTRY_CODE}:
            return OwnershipDecision(
                decision=DECISION_INCLUDE,
                ownership_class="SL_OWNED_INTERNATIONAL" if has_foreign else "SL_DOMESTIC",
                confidence=CONFIDENCE_MEDIUM,
                reason="Verified Sri Lankan corresponding/project-lead affiliation.",
                evidence="crossref:explicit_corresponding_or_project_lead_affiliation",
                lead_country=SRI_LANKA_COUNTRY_CODE,
                corresponding_author_countries=corresponding,
                has_sri_lankan_participant=True,
                has_foreign_participant=has_foreign,
                needs_manual_review=False,
            ).as_dict()
        if SRI_LANKA_COUNTRY_CODE in corresponding_codes:
            return OwnershipDecision(
                decision=DECISION_REVIEW,
                ownership_class="CONFLICTING_CORRESPONDING_LEADERSHIP",
                confidence=CONFIDENCE_LOW,
                reason="Sri Lankan and foreign Crossref leadership signals conflict.",
                evidence="crossref:explicit_corresponding_or_project_lead_affiliation",
                lead_country="; ".join(sorted(corresponding_codes)),
                corresponding_author_countries=corresponding,
                has_sri_lankan_participant=has_lk,
                has_foreign_participant=has_foreign,
                needs_manual_review=True,
            ).as_dict()
        if has_lk:
            return OwnershipDecision(
                decision=DECISION_EXCLUDE,
                ownership_class="FOREIGN_PROJECT_WITH_SL_PARTICIPATION",
                confidence=CONFIDENCE_MEDIUM,
                reason="Verified foreign corresponding/project-lead affiliation with LK participation only.",
                evidence="crossref:explicit_corresponding_or_project_lead_affiliation",
                lead_country="; ".join(sorted(corresponding_codes)),
                corresponding_author_countries=corresponding,
                has_sri_lankan_participant=True,
                has_foreign_participant=has_foreign,
                needs_manual_review=False,
            ).as_dict()

    if not has_lk:
        return OwnershipDecision(
            decision=DECISION_EXCLUDE,
            ownership_class="NO_LK_SIGNAL",
            confidence=CONFIDENCE_LOW,
            reason="No Sri Lankan affiliation signal is present in Crossref metadata.",
            evidence="crossref:author_affiliations",
            lead_country="; ".join(sorted(all_codes)),
            has_sri_lankan_participant=False,
            has_foreign_participant=has_foreign,
            needs_manual_review=False,
        ).as_dict()

    if SRI_LANKA_COUNTRY_CODE in first_codes:
        return OwnershipDecision(
            decision=DECISION_REVIEW,
            ownership_class="FIRST_AUTHOR_ONLY_LK_EVIDENCE",
            confidence=CONFIDENCE_LOW,
            reason="Crossref first-author Sri Lankan affiliation is candidate evidence, not ownership proof.",
            evidence="crossref:first_author_affiliation",
            lead_country="; ".join(sorted(first_codes)),
            has_sri_lankan_participant=True,
            has_foreign_participant=has_foreign,
            needs_manual_review=True,
        ).as_dict()

    return OwnershipDecision(
        decision=DECISION_REVIEW,
        ownership_class="MISSING_LEADERSHIP_EVIDENCE",
        confidence=CONFIDENCE_LOW,
        reason="Sri Lankan participant exists, but Crossref has no reliable leadership evidence.",
        evidence="crossref:participant_affiliation_without_leadership",
        lead_country="; ".join(sorted(all_codes)),
        has_sri_lankan_participant=True,
        has_foreign_participant=has_foreign,
        needs_manual_review=True,
    ).as_dict()


def affiliation_is_sri_lankan(value: Any) -> bool:
    """Resolve an affiliation string to Sri Lanka using country or registry evidence."""
    text = str(value or "").strip()
    if not text:
        return False
    normalized = _normalize_affiliation_key(text)
    if any(_contains_normalized_phrase(normalized, country_name) for country_name in SRI_LANKA_COUNTRY_NAMES):
        return True
    return any(_contains_normalized_phrase(normalized, alias) for alias in _sri_lankan_institution_alias_keys())


def affiliation_country_codes(value: Any) -> set[str]:
    normalized = _normalize_affiliation_key(str(value or ""))
    if not normalized:
        return set()
    countries: set[str] = set()
    if any(_contains_normalized_phrase(normalized, name) for name in SRI_LANKA_COUNTRY_NAMES):
        countries.add(SRI_LANKA_COUNTRY_CODE)
    for name, code in FOREIGN_COUNTRY_NAMES.items():
        if _contains_normalized_phrase(normalized, name):
            countries.add(code)
    if any(_contains_normalized_phrase(normalized, alias) for alias in _sri_lankan_institution_alias_keys()):
        countries.add(SRI_LANKA_COUNTRY_CODE)
    return countries


def _contains_normalized_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    phrase = _normalize_affiliation_key(normalized_phrase)
    if not phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized_text) is not None


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
