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


def map_crossref_record(
    record: dict[str, Any],
    *,
    institution_id: str,
    source: str = "sljol_via_crossref",
) -> dict[str, Any]:
    """Map one raw Crossref work into the common publication schema.

    Used for SLJOL (prefix 10.4038, the default ``source``) and for the
    affiliation-scoped recovery harvests, which pass
    ``source="crossref_affiliation"`` -- same record shape, different
    provenance.
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
    affiliations = [
        name
        for author in record.get("author", [])
        for affiliation in (author.get("affiliation") or [])
        if isinstance(affiliation, dict) and (name := affiliation.get("name"))
    ]
    funders = [
        name for funder in record.get("funder", []) if (name := funder.get("name"))
    ]

    return {
        "source": source,
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
        "volume": record.get("volume"),
        "issue": record.get("issue"),
        "issn": _first(record.get("ISSN")),
        "isbn": _first(record.get("ISBN")),
        "funding": funders,
        "cited_by_count": record.get("is-referenced-by-count"),
        "affiliated_institutions": sorted(set(affiliations)),
        "language": record.get("language"),
        "rights": None,
        "doi": doi,
        "url": record.get("URL"),
        "raw_identifiers": [x for x in [doi, record.get("URL")] + (record.get("ISSN") or []) if x],
    }


def map_pubmed_record(record: dict[str, Any], *, institution_id: str) -> dict[str, Any]:
    """Map one PubMed record (from PubmedCollector) into the common schema.

    PubMed gives no issued date beyond the year for many records, so
    ``publication_date`` is left as that year rather than invented.
    MeSH terms are merged into keywords -- they are the richest subject
    vocabulary in this source and repository records have no equivalent.
    """

    year = record.get("publication_year")
    try:
        publication_year = int(year) if year else None
    except (TypeError, ValueError):
        publication_year = None

    pmid = record.get("pmid")
    keywords = list(record.get("keywords") or []) + list(record.get("mesh_terms") or [])

    return {
        "source": "pubmed",
        "source_institution_id": institution_id,
        "source_record_id": pmid,
        "source_datestamp": None,
        "source_set_specs": [],
        "deleted": False,
        "title": record.get("title"),
        "abstract": record.get("abstract"),
        "keywords": keywords,
        "authors": record.get("authors") or [],
        "contributors": [],
        "publication_date": str(year) if year else None,
        "publication_year": publication_year,
        "publication_type": _first(record.get("publication_types")),
        "publisher": None,
        "journal": record.get("journal"),
        "volume": record.get("volume"),
        "issue": record.get("issue"),
        "issn": record.get("issn"),
        "funding": record.get("grants") or [],
        "affiliated_institutions": sorted(set(record.get("affiliations") or [])),
        "language": record.get("language"),
        "rights": None,
        "doi": record.get("doi"),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
        "pdf_url": (
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{record['pmc']}/"
            if record.get("pmc")
            else None
        ),
        "raw_identifiers": [
            x for x in [record.get("doi"), pmid, record.get("pmc")] if x
        ],
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

    # dc.identifier.other carries "DOI: https://doi.org/..." strings on
    # several hosts (cmb), so it is worth scanning for the DOI regex.
    identifiers = (
        values("dc.identifier.uri")
        + values("dc.identifier.citation")
        + values("dc.identifier.doi")
        + values("dc.identifier.other")
    )
    issued_date = _first(values("dc.date.issued"))
    abstract = _first(values("dc.description.abstract")) or _first(values("dc.description"))

    # Present only when the harvest ran with the bitstreams embed.
    files = [f for f in (record.get("files") or []) if isinstance(f, dict)]
    original = [f for f in files if f.get("bundle") == "ORIGINAL" and f.get("url")]
    extracted_text = [f for f in files if f.get("bundle") == "TEXT" and f.get("url")]

    return {
        "source": "institutional_repository",
        "source_institution_id": institution_id,
        "source_record_id": record.get("uuid"),
        "source_datestamp": record.get("last_modified"),
        # The owning collection is the department/faculty that deposited
        # the item -- the only faculty-level signal in DSpace, and absent
        # from every Dublin Core field.
        "collection": record.get("collection"),
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
        # Qualified DC carries venue/provenance detail the flat OAI feed
        # loses. dc.relation.ispartof is the journal proper; the citation
        # string is the only venue signal on hosts that never filled it in
        # (pdn, uwu), so both are kept rather than collapsed into one field.
        "journal": _first(values("dc.relation.ispartof")),
        "citation": _first(values("dc.identifier.citation")),
        "series": _first(values("dc.relation.ispartofseries")),
        "volume": _first(values("oaire.citation.volume")),
        "issue": _first(values("oaire.citation.issue")),
        "isbn": _first(values("dc.identifier.isbn")),
        "issn": _first(values("dc.identifier.issn")),
        "funding": values("dc.description.sponsorship"),
        "alternative_title": _first(values("dc.title.alternative")),
        "language": _first(values("dc.language.iso")) or _first(values("dc.language")),
        "rights": _first(values("dc.rights")),
        "doi": _extract_doi(identifiers),
        "url": _extract_url(values("dc.identifier.uri")),
        "pdf_url": _first([f["url"] for f in original]),
        "fulltext_url": _first([f["url"] for f in extracted_text]),
        "file_count": len(original) or None,
        "raw_identifiers": identifiers,
    }


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Rebuild plain text from OpenAlex's abstract_inverted_index.

    OpenAlex stores abstracts as {token: [positions]} for licensing
    reasons; the original word order is recoverable by sorting positions.
    """

    if not isinstance(inverted_index, dict) or not inverted_index:
        return None

    positions: list[tuple[int, str]] = []
    for token, indices in inverted_index.items():
        for index in indices or []:
            if isinstance(index, int):
                positions.append((index, token))

    if not positions:
        return None

    positions.sort()
    return " ".join(token for _, token in positions) or None


def map_openalex_record(record: dict[str, Any], *, institution_id: str) -> dict[str, Any]:
    """Map one raw OpenAlex work (from collect_openalex_institution.py)
    into the common publication schema.

    Complements the repository records for the same institution rather
    than replacing them: this is the DOI-bearing journal output, and it
    carries citation counts, open-access status and topic labels that no
    repository route provides.
    """

    ids = record.get("ids") or {}
    primary_location = record.get("primary_location") or {}
    if not isinstance(primary_location, dict):
        primary_location = {}
    source = primary_location.get("source") or {}
    if not isinstance(source, dict):
        source = {}
    open_access = record.get("open_access") or {}
    if not isinstance(open_access, dict):
        open_access = {}
    biblio = record.get("biblio") or {}
    if not isinstance(biblio, dict):
        biblio = {}

    authorships = [a for a in (record.get("authorships") or []) if isinstance(a, dict)]
    authors = [
        name
        for a in authorships
        if (name := ((a.get("author") or {}).get("display_name") or a.get("raw_author_name")))
    ]
    institutions = [
        institution.get("display_name")
        for a in authorships
        for institution in (a.get("institutions") or [])
        if isinstance(institution, dict) and institution.get("display_name")
    ]

    keywords = [
        keyword.get("display_name")
        for keyword in (record.get("keywords") or [])
        if isinstance(keyword, dict) and keyword.get("display_name")
    ]
    topics = [
        topic.get("display_name")
        for topic in (record.get("topics") or [])
        if isinstance(topic, dict) and topic.get("display_name")
    ]
    funders = [
        award.get("funder_display_name")
        for award in (record.get("awards") or [])
        if isinstance(award, dict) and award.get("funder_display_name")
    ]

    doi = record.get("doi")
    if isinstance(doi, str):
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "") or None

    return {
        "source": "openalex",
        "source_institution_id": institution_id,
        "source_record_id": record.get("id"),
        "source_datestamp": record.get("updated_date"),
        "source_set_specs": [],
        "deleted": bool(record.get("is_retracted")),
        "title": record.get("title") or record.get("display_name"),
        "abstract": _reconstruct_abstract(record.get("abstract_inverted_index")),
        "keywords": keywords or topics,
        "authors": authors,
        "contributors": [],
        "publication_date": record.get("publication_date"),
        "publication_year": record.get("publication_year"),
        "publication_type": record.get("type"),
        "publisher": source.get("host_organization_name"),
        "journal": source.get("display_name"),
        "citation": None,
        "series": None,
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "isbn": None,
        "issn": source.get("issn_l"),
        "funding": [f for f in funders if f],
        "alternative_title": None,
        "language": record.get("language"),
        "rights": primary_location.get("license") or open_access.get("oa_status"),
        "doi": doi,
        "url": primary_location.get("landing_page_url") or record.get("doi"),
        "raw_identifiers": [str(v) for v in ids.values() if v],
        # OpenAlex-only signals, kept because they drive the impact and
        # open-access parts of the analysis.
        "cited_by_count": record.get("cited_by_count"),
        "is_open_access": open_access.get("is_oa"),
        "oa_status": open_access.get("oa_status"),
        "pdf_url": primary_location.get("pdf_url"),
        "topics": topics,
        "affiliated_institutions": sorted(set(institutions)),
    }
