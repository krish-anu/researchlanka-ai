"""Map raw OAI Dublin Core records (see oai_pmh_collector.py) into the
project's common publication-metadata schema (proposal Sec. 3: title, DOI,
abstract, keywords, publication year/date, type, journal/publisher, authors,
institution).

This is a draft, source-specific mapping for repository (OAI-DC) records
only -- OpenAlex/Crossref collectors will need their own mappers into the
same target field names. Dublin Core is flat and unqualified (no way to
tell dc:date "issued" from "accessioned" apart, for example), so several
fields below are best-effort heuristics; see inline notes.
"""

from __future__ import annotations

import re
from typing import Any

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+")
YEAR_PATTERN = re.compile(r"(1[5-9]\d{2}|20\d{2})")


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def _pick_issued_date(dates: list[str] | None) -> str | None:
    """Best-effort pick of the "date issued" value out of DSpace's flat
    dc:date list, which commonly mixes dateAccessioned/dateAvailable
    (full timestamps) with dateIssued (often just a year or year-month).

    Heuristic: prefer a value without a time component ('T'), since
    accession/availability timestamps are typically full ISO datetimes
    and the issued date is typically coarser. Falls back to the last
    value, then the first, since DSpace tends to emit dateIssued last.
    """

    if not dates:
        return None

    coarse = [d for d in dates if "T" not in d]
    if coarse:
        return coarse[-1]
    return dates[-1]


def _extract_year(date_value: str | None, all_dates: list[str] | None) -> int | None:
    candidates = [date_value] if date_value else []
    candidates += all_dates or []
    for candidate in candidates:
        if not candidate:
            continue
        match = YEAR_PATTERN.search(candidate)
        if match:
            return int(match.group(1))
    return None


def _extract_doi(identifiers: list[str] | None) -> str | None:
    for identifier in identifiers or []:
        match = DOI_PATTERN.search(identifier)
        if match:
            return match.group(0).rstrip(".,)")
    return None


def _extract_url(identifiers: list[str] | None) -> str | None:
    for identifier in identifiers or []:
        match = URL_PATTERN.search(identifier)
        if match:
            return match.group(0).rstrip(".,)")
    return None


def map_oai_dc_record(record: dict[str, Any], *, institution_id: str) -> dict[str, Any]:
    """Map one harvested OAI-DC record (from OaiPmhCollector) into the
    common publication schema. Deleted records are passed through with
    only provenance fields populated -- callers should filter on
    ``deleted`` before using the rest.
    """

    if record.get("deleted"):
        return {
            "source": "institutional_repository",
            "source_institution_id": institution_id,
            "source_record_id": record.get("oai_identifier"),
            "deleted": True,
        }

    dates = record.get("date")
    issued_date = _pick_issued_date(dates)

    return {
        "source": "institutional_repository",
        "source_institution_id": institution_id,
        "source_record_id": record.get("oai_identifier"),
        "source_datestamp": record.get("datestamp"),
        "source_set_specs": record.get("set_specs", []),
        "deleted": False,
        "title": _first(record.get("title")),
        "abstract": _first(record.get("description")),
        "keywords": record.get("subject", []),
        "authors": record.get("creator", []),
        "contributors": record.get("contributor", []),
        "publication_date": issued_date,
        "publication_year": _extract_year(issued_date, dates),
        "publication_type": _first(record.get("type")),
        "publisher": _first(record.get("publisher")),
        "language": _first(record.get("language")),
        "rights": _first(record.get("rights")),
        "doi": _extract_doi(record.get("identifier")),
        "url": _extract_url(record.get("identifier")),
        "raw_identifiers": record.get("identifier", []),
    }


JATS_TAG_RE = re.compile(r"</?jats:[^>]+>|</?[a-z]+:?[^>]*>")


def _strip_jats(abstract: str | None) -> str | None:
    """Crossref abstracts arrive as JATS XML fragments -- strip the tags."""

    if not abstract:
        return None
    text = JATS_TAG_RE.sub(" ", abstract)
    return re.sub(r"\s+", " ", text).strip() or None


def map_crossref_record(record: dict[str, Any], *, institution_id: str) -> dict[str, Any]:
    """Map one raw Crossref work (from CrossrefPrefixCollector) into the
    common publication schema. Used for SLJOL (prefix 10.4038).
    """

    def author_name(author: dict[str, Any]) -> str | None:
        if author.get("name"):
            return author["name"]
        parts = [author.get("given"), author.get("family")]
        joined = " ".join(p for p in parts if p)
        return joined or None

    authors = [name for a in record.get("author", []) if (name := author_name(a))]

    date_parts = (record.get("issued") or {}).get("date-parts") or [[]]
    issued = date_parts[0]
    publication_date = "-".join(f"{part:02d}" if i else str(part) for i, part in enumerate(issued)) or None
    publication_year = issued[0] if issued else None

    doi = record.get("DOI")
    container_titles = record.get("container-title") or []

    return {
        "source": "sljol_via_crossref",
        "source_institution_id": institution_id,
        "source_record_id": doi,
        "source_datestamp": (record.get("deposited") or {}).get("date-time"),
        "source_set_specs": [],
        "deleted": False,
        "title": _first(record.get("title")),
        "abstract": _strip_jats(record.get("abstract")),
        "keywords": record.get("subject", []),
        "authors": authors,
        "contributors": [],
        "publication_date": publication_date,
        "publication_year": publication_year,
        "publication_type": record.get("type"),
        "publisher": record.get("publisher"),
        "journal": _first(container_titles),
        "language": record.get("language"),
        "rights": None,
        "doi": doi,
        "url": record.get("URL"),
        "raw_identifiers": [x for x in [doi, record.get("URL")] + (record.get("ISSN") or []) if x],
    }


def map_html_meta_record(record: dict[str, Any], *, institution_id: str) -> dict[str, Any]:
    """Map one crawled item-page record (from HtmlMetaCollector) into the
    common publication schema. Metadata comes from the DC/DCTERMS/citation
    <meta> tags DSpace embeds in item pages.
    """

    meta = record.get("meta") or {}

    def values(*fields: str) -> list[str]:
        for field in fields:
            if meta.get(field):
                return meta[field]
        return []

    identifiers = meta.get("DC.identifier", [])
    issued_date = _first(values("DCTERMS.issued", "citation_date"))

    return {
        "source": "institutional_repository",
        "source_institution_id": institution_id,
        "source_record_id": record.get("handle_path"),
        "source_datestamp": _first(values("DCTERMS.available", "DCTERMS.dateAccepted")),
        "source_set_specs": [],
        "deleted": False,
        "title": _first(values("DC.title", "citation_title")),
        "abstract": _first(values("DCTERMS.abstract", "DC.description")),
        "keywords": values("DC.subject", "citation_keywords"),
        "authors": values("DC.creator", "citation_author"),
        "contributors": values("DC.contributor"),
        "publication_date": issued_date,
        "publication_year": _extract_year(issued_date, values("DCTERMS.issued")),
        "publication_type": _first(values("DC.type")),
        "publisher": _first(values("DC.publisher", "citation_publisher")),
        "language": _first(values("DC.language")),
        "rights": _first(values("DC.rights")),
        "doi": _extract_doi(identifiers),
        "url": record.get("url") or _extract_url(identifiers),
        "raw_identifiers": identifiers,
    }


def map_dspace_rest_record(record: dict[str, Any], *, institution_id: str) -> dict[str, Any]:
    """Map one DSpace 7/8 REST item (from DspaceRestCollector) into the
    common publication schema.

    REST metadata is qualified Dublin Core keyed by full field name
    (e.g. ``dc.date.issued`` separate from ``dc.date.accessioned``), so
    unlike the flat OAI mapping no date heuristics are needed.
    """

    metadata = record.get("metadata") or {}

    def values(field: str) -> list[str]:
        return metadata.get(field, [])

    identifiers = values("dc.identifier.uri") + values("dc.identifier.citation") + values(
        "dc.identifier.doi"
    )
    issued_date = _first(values("dc.date.issued"))
    abstract = _first(values("dc.description.abstract")) or _first(values("dc.description"))

    return {
        "source": "institutional_repository",
        "source_institution_id": institution_id,
        "source_record_id": record.get("uuid"),
        "source_datestamp": record.get("last_modified"),
        "source_set_specs": [],
        "deleted": bool(record.get("withdrawn")),
        "title": _first(values("dc.title")) or record.get("name"),
        "abstract": abstract,
        "keywords": values("dc.subject"),
        "authors": values("dc.contributor.author") or values("dc.creator"),
        "contributors": values("dc.contributor") + values("dc.contributor.advisor"),
        "publication_date": issued_date,
        "publication_year": _extract_year(issued_date, values("dc.date.issued")),
        "publication_type": _first(values("dc.type")),
        "publisher": _first(values("dc.publisher")),
        "language": _first(values("dc.language.iso")) or _first(values("dc.language")),
        "rights": _first(values("dc.rights")),
        "doi": _extract_doi(identifiers),
        "url": _extract_url(values("dc.identifier.uri")),
        "raw_identifiers": identifiers,
    }
