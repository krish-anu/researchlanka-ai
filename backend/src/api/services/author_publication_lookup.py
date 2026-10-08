"""DOI metadata lookup and AI relevance checks for author-submitted publications.

Both run the same code the pipeline uses — the OpenAlex/Crossref normalisers
for Sri Lanka ownership evidence and `apply_ai_classification` for the AI
label — so an author submission is judged by the same rules as a harvested
record. Neither step decides anything: the results are evidence an
administrator reviews.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote

import requests

from src.api.core.errors import APIError
from src.collectors.crossref_collector import CROSSREF_BASE_URL, USER_AGENT
from src.collectors.openalex_collector import OPENALEX_BASE_URL
from src.preprocessing import crossref_normalizer, openalex_normalizer
from src.utils.doi import is_valid_doi, normalize_doi


logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT_SECONDS = 15
OWNERSHIP_EVIDENCE_KEYS = (
    "ownership_decision",
    "ownership_class",
    "ownership_confidence",
    "ownership_reason",
    "ownership_evidence",
    "lead_country",
    "corresponding_author_countries",
    "has_sri_lankan_participant",
    "needs_manual_review",
    "ownership_policy_version",
)
JATS_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")

HttpGet = Callable[..., Any]


def lookup_doi(doi: str, *, http_get: HttpGet | None = None) -> dict[str, Any]:
    """Fetch publication metadata for a DOI, OpenAlex first, then Crossref.

    Returns form-ready fields plus the source's Sri Lanka ownership evidence.
    A DOI neither service knows raises `doi_not_found`, so the author can fall
    back to the manual form.
    """

    normalized = normalize_doi(doi)
    if not normalized or not is_valid_doi(normalized):
        raise APIError("invalid_doi", "Enter a DOI such as 10.1234/abcd.5678.", status=400)

    get = http_get or requests.get
    work = fetch_openalex_work(normalized, get)
    if work is not None:
        return openalex_lookup_payload(work, normalized)

    crossref_work = fetch_crossref_work(normalized, get)
    if crossref_work is not None:
        return crossref_lookup_payload(crossref_work, normalized)

    raise APIError(
        "doi_not_found",
        "Neither OpenAlex nor Crossref has a record for this DOI. Enter the details by hand.",
        status=404,
    )


def fetch_openalex_work(doi: str, get: HttpGet) -> dict[str, Any] | None:
    params: dict[str, str] = {}
    if os.getenv("OPENALEX_EMAIL"):
        params["mailto"] = str(os.getenv("OPENALEX_EMAIL"))
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = str(os.getenv("OPENALEX_API_KEY"))
    return _fetch_json(
        get,
        f"{OPENALEX_BASE_URL}/works/doi:{quote(doi, safe='/')}",
        params=params,
        source="OpenAlex",
    )


def fetch_crossref_work(doi: str, get: HttpGet) -> dict[str, Any] | None:
    payload = _fetch_json(
        get,
        f"{CROSSREF_BASE_URL}/works/{quote(doi, safe='')}",
        params={},
        source="Crossref",
        headers={"User-Agent": USER_AGENT},
    )
    if payload is None:
        return None
    message = payload.get("message")
    return message if isinstance(message, dict) else None


def _fetch_json(
    get: HttpGet,
    url: str,
    *,
    params: Mapping[str, str],
    source: str,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    try:
        response = get(
            url,
            params=dict(params),
            headers=dict(headers or {}),
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("%s DOI lookup failed: %s", source, exc)
        return None
    if response.status_code == 404:
        return None
    if not response.ok:
        logger.warning("%s DOI lookup returned HTTP %s", source, response.status_code)
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def openalex_lookup_payload(work: dict[str, Any], doi: str) -> dict[str, Any]:
    row = openalex_normalizer.work_to_row(work)
    authorships = openalex_normalizer.authorships(work)
    authors = [openalex_author(authorship) for authorship in authorships]
    return {
        "source": "openalex",
        "doi": doi,
        "openalex_id": row.get("openalex_id"),
        "fields": {
            "title": row.get("title") or "",
            "abstract": abstract_from_inverted_index(work.get("abstract_inverted_index")),
            "keywords": keyword_names(work.get("keywords")),
            "publication_year": row.get("publication_year"),
            "publication_date": row.get("publication_date"),
            "type": row.get("type") or "",
            "journal": row.get("source_name") or "",
            "publisher": row.get("publisher") or "",
            "volume": row.get("volume") or "",
            "issue": row.get("issue") or "",
            "first_page": row.get("first_page") or "",
            "last_page": row.get("last_page") or "",
            "language": row.get("language") or "",
            "url": row.get("landing_page_url") or f"https://doi.org/{doi}",
            "pdf_url": row.get("pdf_url") or "",
            "authors": [author for author in authors if author["name"]],
        },
        "ownership": ownership_evidence(row),
        "countries": row.get("countries") or "",
        "institutions": row.get("institutions") or "",
        "sri_lankan_institutions": row.get("sri_lankan_institutions") or "",
        "category": {
            "primary_field": row.get("primary_field") or None,
            "primary_subfield": row.get("primary_subfield") or None,
            "primary_domain": row.get("primary_domain") or None,
            "primary_topic": row.get("primary_topic") or None,
            "topics": row.get("topics") or None,
            "concepts": row.get("concepts") or None,
        },
    }


def openalex_author(authorship: dict[str, Any]) -> dict[str, Any]:
    """One author with the institution OpenAlex recorded for this publication."""

    from src.api.services.author_reference import canonical_institution

    institutions = [
        institution
        for institution in openalex_normalizer.as_list(authorship.get("institutions"))
        if isinstance(institution, dict) and institution.get("display_name")
    ]
    first = institutions[0] if institutions else {}
    canonical = canonical_institution(first.get("display_name")) if first else None
    return {
        "name": openalex_normalizer.author_name(authorship) or "",
        "affiliation": "",
        "institution": canonical["label"] if canonical else "",
        "country_code": (canonical or {}).get("country_code") or str(first.get("country_code") or "").upper(),
    }


def crossref_lookup_payload(work: dict[str, Any], doi: str) -> dict[str, Any]:
    ownership = crossref_normalizer.classify_sri_lanka_ownership(work)
    authors = []
    for author in work.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = crossref_normalizer.crossref_author_name(author)
        if name:
            # Crossref gives free-text affiliations only; the author confirms
            # the institution in the form.
            affiliation = "; ".join(crossref_normalizer.author_affiliation_names(author))
            authors.append({"name": name, "affiliation": affiliation, "institution": "", "country_code": ""})
    first_page, last_page = split_page_range(work.get("page"))
    return {
        "source": "crossref",
        "doi": doi,
        "openalex_id": None,
        "fields": {
            "title": first_text(work.get("title")),
            "abstract": strip_jats(work.get("abstract")),
            "keywords": "; ".join(str(item) for item in work.get("subject") or [] if item),
            "publication_year": crossref_year(work),
            "publication_date": None,
            "type": str(work.get("type") or ""),
            "journal": first_text(work.get("container-title")),
            "publisher": str(work.get("publisher") or ""),
            "volume": str(work.get("volume") or ""),
            "issue": str(work.get("issue") or ""),
            "first_page": first_page,
            "last_page": last_page,
            "language": str(work.get("language") or ""),
            "url": str(work.get("URL") or f"https://doi.org/{doi}"),
            "pdf_url": "",
            "authors": authors,
        },
        "ownership": ownership_evidence(ownership),
        "countries": "",
        "institutions": "",
        "sri_lankan_institutions": "",
        "category": {},
    }


def ownership_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in OWNERSHIP_EVIDENCE_KEYS if key in row}


def abstract_from_inverted_index(index: Any) -> str:
    """Rebuild OpenAlex's word-position abstract into plain text."""

    if not isinstance(index, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, str(word)))
    positioned.sort()
    return " ".join(word for _, word in positioned)


def keyword_names(values: Any) -> str:
    names = []
    for value in values or []:
        if isinstance(value, dict):
            name = value.get("display_name") or value.get("keyword")
        else:
            name = value
        if name:
            names.append(str(name))
    return "; ".join(dict.fromkeys(names))


def strip_jats(value: Any) -> str:
    if not value:
        return ""
    text = JATS_TAG_PATTERN.sub(" ", str(value))
    text = re.sub(r"^\s*Abstract\s+", "", WHITESPACE_PATTERN.sub(" ", text).strip(), flags=re.I)
    return text


def first_text(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value or "").strip()


def crossref_year(work: Mapping[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (work.get(key) or {}).get("date-parts") if isinstance(work.get(key), dict) else None
        if parts and isinstance(parts[0], list) and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def split_page_range(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    first, _, last = text.partition("-")
    return first.strip(), last.strip()


# ------------------------------------------------------------- AI relevance

Classifier = Callable[[dict[str, Any]], dict[str, Any]]


def classify_submission(record: Mapping[str, Any]) -> dict[str, Any]:
    """Run the production AI relevance model on one submitted record.

    A missing or broken model is a normal state on a developer machine, so it
    is reported as label `review` with the reason rather than raised: the
    administrator still decides, they just decide without a model score.
    """

    from src.pipeline.incremental_update import apply_ai_classification
    from src.pipeline.refresh_policy import (
        configured_confidence_review_threshold,
        configured_model_path,
        configured_text_columns,
    )

    try:
        model_path = configured_model_path(None)
        if model_path is None or not model_path.is_file():
            # The path is for operators, not for the review screen.
            logger.warning("AI relevance model not found at %s; author submission left for review", model_path)
            return unavailable_classifier_result("model_not_found")
        classified = apply_ai_classification(
            [dict(record)],
            model_path=model_path,
            text_columns=configured_text_columns(None),
            confidence_review_threshold=configured_confidence_review_threshold(None),
        )[0]
    except Exception as exc:  # noqa: BLE001 - any model failure becomes evidence, not a 500
        logger.warning("AI relevance check failed for author submission: %s", exc)
        return unavailable_classifier_result(f"model_error:{type(exc).__name__}")

    return {
        "label": classified.get("ai_classification_label") or "review",
        "confidence": classified.get("ai_classification_confidence"),
        "model": classified.get("ai_classification_model"),
        "reason": classified.get("ai_classification_reason"),
        "available": True,
    }


def unavailable_classifier_result(reason: str) -> dict[str, Any]:
    return {
        "label": "review",
        "confidence": None,
        "model": None,
        "reason": reason,
        "available": False,
    }
