"""OpenAlex normalization and flattening helpers for analysis-ready datasets."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.preprocessing.ownership import (
    OWNERSHIP_POLICY_VERSION,
    openalex_publication_ownership,
)
from src.utils.doi import normalize_doi


SRI_LANKA_COUNTRY_CODE = "LK"

CSV_COLUMNS = [
    "openalex_id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "cited_by_count",
    "author_count",
    "authors",
    "sri_lankan_authors",
    "institutions",
    "sri_lankan_institutions",
    "raw_affiliation_strings",
    "sri_lankan_raw_affiliation_strings",
    "countries",
    "first_author_countries",
    "corresponding_author_countries",
    "first_author_name",
    "first_author_institution",
    "first_author_country",
    "corresponding_author_name",
    "corresponding_author_institution",
    "corresponding_author_country",
    "last_author_name",
    "last_author_institution",
    "last_author_country",
    "project_pi",
    "project_lead_institution",
    "project_lead_country",
    "degree_awarding_institution",
    "repository_institution",
    "funder",
    "grant_award",
    "all_author_countries",
    "has_sri_lankan_participant",
    "has_foreign_participant",
    "venue_is_sri_lankan",
    "ownership_decision",
    "country_owner",
    "ownership_class",
    "ownership_classification",
    "ownership_confidence",
    "ownership_reason",
    "ownership_evidence",
    "lead_country",
    "keep_in_strict_sri_lanka_dataset",
    "keep_in_sri_lanka_owned_dataset",
    "needs_manual_review",
    "ownership_policy_version",
    "source_name",
    "publisher",
    "is_retracted",
    "is_oa",
    "landing_page_url",
    "pdf_url",
    "locations_count",
    "location_landing_page_urls",
    "location_pdf_urls",
    "location_source_names",
    "location_source_types",
    "location_licenses",
    "location_versions",
    "referenced_works_count",
    "concepts",
    "topics",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "language",
    "oa_status",
    "license",
    "source_type",
    "issn_l",
    "volume",
    "issue",
    "first_page",
    "last_page",
]


def as_list(value: Any) -> list[Any]:
    """Return OpenAlex list fields safely when a response omits or nulls them."""
    return value if isinstance(value, list) else []


def unique_join(values: Any, separator: str = "; ") -> str:
    """Join unique non-empty values in first-seen order for flat CSV columns."""
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return separator.join(output)


def authorships(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only dict-shaped authorships from an OpenAlex work."""
    return [
        authorship
        for authorship in as_list(work.get("authorships"))
        if isinstance(authorship, dict)
    ]


def first_authorship(work: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first author authorship from an OpenAlex work."""
    valid_authorships = authorships(work)
    if not valid_authorships:
        return None
    first = next(
        (
            authorship
            for authorship in valid_authorships
            if authorship.get("author_position") == "first"
        ),
        None,
    )
    if first is not None:
        return first
    if any(authorship.get("author_position") for authorship in valid_authorships):
        return None
    return valid_authorships[0]


def last_authorship(work: dict[str, Any]) -> dict[str, Any] | None:
    """Return the last/senior author authorship from an OpenAlex work."""
    valid_authorships = authorships(work)
    if not valid_authorships:
        return None
    last = next(
        (
            authorship
            for authorship in valid_authorships
            if authorship.get("author_position") == "last"
        ),
        None,
    )
    if last is not None:
        return last
    if any(authorship.get("author_position") for authorship in valid_authorships):
        return None
    return valid_authorships[-1]


def corresponding_authorships(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Return authorships OpenAlex marks as corresponding authors."""
    marked = [
        authorship
        for authorship in authorships(work)
        if authorship.get("is_corresponding") is True
    ]
    if marked:
        return marked

    institution_ids = {
        str(value)
        for value in as_list(work.get("corresponding_institution_ids"))
        if value
    }
    if not institution_ids:
        return []

    return [
        authorship
        for authorship in authorships(work)
        if any(
            isinstance(institution, dict)
            and institution.get("id") is not None
            and str(institution["id"]) in institution_ids
            for institution in as_list(authorship.get("institutions"))
        )
    ]


def country_codes_from_authorship(authorship: dict[str, Any]) -> set[str]:
    """Collect country codes from both authorship countries and institutions."""
    codes = {
        str(country).upper()
        for country in as_list(authorship.get("countries"))
        if country
    }
    for institution in as_list(authorship.get("institutions")):
        if isinstance(institution, dict) and institution.get("country_code"):
            codes.add(str(institution["country_code"]).upper())
    return codes


def country_codes_from_authorships(authorships_: list[dict[str, Any]]) -> set[str]:
    """Collect country codes from several authorships."""
    codes: set[str] = set()
    for authorship in authorships_:
        codes.update(country_codes_from_authorship(authorship))
    return codes


def first_author_country_codes(work: dict[str, Any]) -> set[str]:
    """Return affiliation country codes from only the first authorship."""
    first = first_authorship(work)
    if first is None:
        return set()
    return country_codes_from_authorship(first)


def corresponding_author_country_codes(work: dict[str, Any]) -> set[str]:
    """Return affiliation country codes from corresponding authorships only."""
    return country_codes_from_authorships(corresponding_authorships(work))


def affiliation_institution_names(authorship: dict[str, Any] | None) -> str:
    """Flatten publication-specific institution names for one authorship."""
    if authorship is None:
        return ""
    return unique_join(
        institution.get("display_name")
        for institution in as_list(authorship.get("institutions"))
        if isinstance(institution, dict)
    )


def affiliation_country_codes(authorship: dict[str, Any] | None) -> str:
    """Flatten publication-specific affiliation country codes for one authorship."""
    if authorship is None:
        return ""
    return unique_join(sorted(country_codes_from_authorship(authorship)))


def corresponding_author_names(work: dict[str, Any]) -> str:
    """Flatten names for all corresponding authors OpenAlex identifies."""
    return unique_join(
        author_name(authorship) for authorship in corresponding_authorships(work)
    )


def corresponding_author_institutions(work: dict[str, Any]) -> str:
    """Flatten publication-specific institutions for all corresponding authors."""
    names: list[str] = []
    for authorship in corresponding_authorships(work):
        text = affiliation_institution_names(authorship)
        if text:
            names.extend(text.split("; "))
    return unique_join(names)


def is_sri_lankan_authorship(authorship: dict[str, Any]) -> bool:
    """Check whether one authorship has a Sri Lankan affiliation signal."""
    return SRI_LANKA_COUNTRY_CODE in country_codes_from_authorship(authorship)


def is_first_authorship_from_country(work: dict[str, Any], country_code: str) -> bool:
    """Check whether the first author has an affiliation signal for a country."""
    return country_code.upper() in first_author_country_codes(work)


def has_sri_lankan_first_author(work: dict[str, Any]) -> bool:
    """Check whether a work's first author has a Sri Lankan affiliation signal."""
    return is_first_authorship_from_country(work, SRI_LANKA_COUNTRY_CODE)


def has_sri_lankan_author(work: dict[str, Any]) -> bool:
    """Keep broad Sri Lankan-affiliated works with at least one LK signal."""
    if any(is_sri_lankan_authorship(authorship) for authorship in authorships(work)):
        return True

    for institution in as_list(work.get("institutions")):
        if (
            isinstance(institution, dict)
            and str(institution.get("country_code", "")).upper()
            == SRI_LANKA_COUNTRY_CODE
        ):
            return True

    return False


def author_name(authorship: dict[str, Any]) -> str | None:
    """Prefer normalized OpenAlex author names, falling back to raw names."""
    author = authorship.get("author")
    if isinstance(author, dict) and author.get("display_name"):
        return str(author["display_name"])
    if authorship.get("raw_author_name"):
        return str(authorship["raw_author_name"])
    return None


def author_names(work: dict[str, Any], *, sri_lankan_only: bool = False) -> str:
    """Flatten author names, optionally keeping only LK-affiliated authorships."""
    names: list[str | None] = []
    for authorship in authorships(work):
        if sri_lankan_only and not is_sri_lankan_authorship(authorship):
            continue
        names.append(author_name(authorship))
    return unique_join(names)


def institution_names(work: dict[str, Any], *, sri_lankan_only: bool = False) -> str:
    """Flatten institution names, optionally keeping only Sri Lankan institutions."""
    names: list[Any] = []
    for authorship in authorships(work):
        for institution in as_list(authorship.get("institutions")):
            if not isinstance(institution, dict):
                continue
            country_code = str(institution.get("country_code", "")).upper()
            if sri_lankan_only and country_code != SRI_LANKA_COUNTRY_CODE:
                continue
            names.append(institution.get("display_name"))
    return unique_join(names)


def raw_affiliation_strings(
    work: dict[str, Any],
    *,
    sri_lankan_only: bool = False,
) -> str:
    """Flatten raw affiliation strings preserved on OpenAlex authorships."""
    values: list[Any] = []
    for authorship in authorships(work):
        if sri_lankan_only and not is_sri_lankan_authorship(authorship):
            continue

        raw_strings = as_list(authorship.get("raw_affiliation_strings"))
        if raw_strings:
            values.extend(raw_strings)
        elif authorship.get("raw_affiliation_string"):
            values.append(authorship.get("raw_affiliation_string"))

    return unique_join(values)


def country_codes(work: dict[str, Any]) -> str:
    """Flatten all detected country codes into a stable semicolon-separated value."""
    return unique_join(sorted(detected_country_codes(work)))


def country_owner(work: dict[str, Any]) -> str:
    """Return the best available country leadership proxy for OpenAlex data."""
    classification = classify_sri_lanka_ownership(work)
    return classification["lead_country"]


def ownership_classification(work: dict[str, Any]) -> str:
    """Classify Sri Lanka ownership/leadership from structured affiliation metadata."""
    return classify_sri_lanka_ownership(work)["ownership_class"]


def keep_in_sri_lanka_owned_dataset(work: dict[str, Any]) -> bool:
    """Return True only for records that satisfy the Sri Lankan ownership rule."""
    return keep_in_country_owned_dataset(work, SRI_LANKA_COUNTRY_CODE)


def keep_in_country_owned_dataset(work: dict[str, Any], country_code: str) -> bool:
    """Return True for works owned/led by the configured country."""
    return classify_country_ownership(work, country_code)["keep_in_strict_dataset"]


def classify_sri_lanka_ownership(work: dict[str, Any]) -> dict[str, Any]:
    """Classify Sri Lanka ownership/leadership using OpenAlex structured fields."""
    return classify_country_ownership(work, SRI_LANKA_COUNTRY_CODE)


def classify_country_ownership(work: dict[str, Any], country_code: str) -> dict[str, Any]:
    """Classify project ownership using corresponding-author evidence before first author.

    OpenAlex does not expose PI, grant-administering, degree-awarding, or project
    host fields in the records handled here, so journal-article classification
    uses publication-specific affiliations only and leaves weak cases for review.
    """
    return openalex_publication_ownership(
        target_country=country_code,
        all_countries=detected_country_codes(work),
        first_author_countries=first_author_country_codes(work),
        corresponding_author_countries=corresponding_author_country_codes(work),
    ).as_dict()


def detected_country_codes(work: dict[str, Any]) -> set[str]:
    """Detect affiliation country codes from work-level and authorship metadata."""
    codes: set[str] = set()
    for authorship in authorships(work):
        codes.update(country_codes_from_authorship(authorship))

    for institution in as_list(work.get("institutions")):
        if isinstance(institution, dict) and institution.get("country_code"):
            codes.add(str(institution["country_code"]).upper())

    return codes


def is_strict_sri_lanka_only(work: dict[str, Any]) -> bool:
    """Return True only when every detected affiliation country code is LK."""
    return detected_country_codes(work) == {SRI_LANKA_COUNTRY_CODE}


def display_names(values: Any) -> str:
    """Flatten OpenAlex lists of objects that expose a display_name field."""
    names: list[Any] = []
    for value in as_list(values):
        if isinstance(value, dict):
            names.append(value.get("display_name"))
    return unique_join(names)


def locations(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only dict-shaped locations from an OpenAlex work."""
    return [
        location
        for location in as_list(work.get("locations"))
        if isinstance(location, dict)
    ]


def location_values(work: dict[str, Any], *keys: str) -> str:
    """Flatten values from every OpenAlex location for one nested path."""
    values: list[Any] = []
    for location in locations(work):
        values.append(get_nested(location, *keys))
    return unique_join(values)


def get_nested(value: dict[str, Any], *keys: str) -> Any:
    """Read a nested dictionary path without raising on missing levels."""
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def openalex_work_id(work: dict[str, Any]) -> str | None:
    """Return the required OpenAlex work ID used as the record key."""
    work_id = work.get("id")
    if work_id is None:
        return None
    normalized_id = str(work_id).strip()
    return normalized_id or None


def normalize_publication_year(value: Any) -> int | None:
    """Normalize OpenAlex publication_year to an integer when valid."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def normalize_publication_date(value: Any) -> str | None:
    """Normalize OpenAlex publication_date to ISO YYYY-MM-DD for CSV output."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def work_to_row(work: dict[str, Any]) -> dict[str, Any]:
    """Convert one raw OpenAlex work into the analysis-friendly CSV schema."""
    source = get_nested(work, "primary_location", "source") or {}
    primary_location = work.get("primary_location") or {}
    open_access = work.get("open_access") or {}
    biblio = work.get("biblio") or {}
    first = first_authorship(work)
    last = last_authorship(work)
    ownership = classify_sri_lanka_ownership(work)
    primary_topic = work.get("primary_topic")
    # Older or partial OpenAlex records may not include primary_topic, so use
    # the first topic as a best-effort classification fallback.
    if not isinstance(primary_topic, dict):
        primary_topic = next(
            (topic for topic in as_list(work.get("topics")) if isinstance(topic, dict)),
            {},
        )

    if not isinstance(source, dict):
        source = {}
    if not isinstance(primary_location, dict):
        primary_location = {}
    if not isinstance(open_access, dict):
        open_access = {}
    if not isinstance(biblio, dict):
        biblio = {}

    return {
        "openalex_id": openalex_work_id(work),
        "doi": normalize_doi(work.get("doi")),
        "title": work.get("title") or work.get("display_name"),
        "publication_year": normalize_publication_year(work.get("publication_year")),
        "publication_date": normalize_publication_date(work.get("publication_date")),
        "type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "author_count": len(authorships(work)),
        "authors": author_names(work),
        "sri_lankan_authors": author_names(work, sri_lankan_only=True),
        "institutions": institution_names(work),
        "sri_lankan_institutions": institution_names(work, sri_lankan_only=True),
        "raw_affiliation_strings": raw_affiliation_strings(work),
        "sri_lankan_raw_affiliation_strings": raw_affiliation_strings(
            work,
            sri_lankan_only=True,
        ),
        "countries": country_codes(work),
        "first_author_countries": unique_join(sorted(first_author_country_codes(work))),
        "corresponding_author_countries": unique_join(
            sorted(corresponding_author_country_codes(work))
        ),
        "first_author_name": author_name(first) if first else "",
        "first_author_institution": affiliation_institution_names(first),
        "first_author_country": affiliation_country_codes(first),
        "corresponding_author_name": corresponding_author_names(work),
        "corresponding_author_institution": corresponding_author_institutions(work),
        "corresponding_author_country": unique_join(
            sorted(corresponding_author_country_codes(work))
        ),
        "last_author_name": author_name(last) if last else "",
        "last_author_institution": affiliation_institution_names(last),
        "last_author_country": affiliation_country_codes(last),
        "project_pi": "",
        "project_lead_institution": "",
        "project_lead_country": "",
        "degree_awarding_institution": "",
        "repository_institution": "",
        "funder": display_names(work.get("grants")),
        "grant_award": unique_join(
            grant.get("award_id")
            for grant in as_list(work.get("grants"))
            if isinstance(grant, dict)
        ),
        "all_author_countries": country_codes(work),
        "has_sri_lankan_participant": has_sri_lankan_author(work),
        "has_foreign_participant": bool(
            detected_country_codes(work) - {SRI_LANKA_COUNTRY_CODE}
        ),
        "venue_is_sri_lankan": "",
        "ownership_decision": ownership["ownership_decision"],
        "country_owner": ownership["country_owner"],
        "ownership_class": ownership["ownership_class"],
        "ownership_classification": ownership["ownership_class"],
        "ownership_confidence": ownership["ownership_confidence"],
        "ownership_reason": ownership["ownership_reason"],
        "ownership_evidence": ownership["ownership_evidence"],
        "lead_country": ownership["lead_country"],
        "keep_in_strict_sri_lanka_dataset": ownership["keep_in_strict_dataset"],
        "keep_in_sri_lanka_owned_dataset": ownership["keep_in_strict_dataset"],
        "needs_manual_review": ownership["needs_manual_review"],
        "ownership_policy_version": OWNERSHIP_POLICY_VERSION,
        "source_name": source.get("display_name"),
        "publisher": source.get("host_organization_name"),
        "is_retracted": work.get("is_retracted") is True,
        "is_oa": open_access.get("is_oa"),
        "landing_page_url": primary_location.get("landing_page_url"),
        "pdf_url": primary_location.get("pdf_url"),
        "locations_count": len(locations(work)),
        "location_landing_page_urls": location_values(work, "landing_page_url"),
        "location_pdf_urls": location_values(work, "pdf_url"),
        "location_source_names": location_values(work, "source", "display_name"),
        "location_source_types": location_values(work, "source", "type"),
        "location_licenses": location_values(work, "license"),
        "location_versions": location_values(work, "version"),
        "referenced_works_count": work.get("referenced_works_count")
        or len(as_list(work.get("referenced_works"))),
        "concepts": display_names(work.get("concepts")),
        "topics": display_names(work.get("topics")),
        "primary_topic": primary_topic.get("display_name"),
        "primary_field": get_nested(primary_topic, "field", "display_name"),
        "primary_subfield": get_nested(primary_topic, "subfield", "display_name"),
        "primary_domain": get_nested(primary_topic, "domain", "display_name"),
        "language": work.get("language"),
        "oa_status": open_access.get("oa_status"),
        "license": open_access.get("license") or primary_location.get("license"),
        "source_type": source.get("type"),
        "issn_l": source.get("issn_l"),
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "first_page": biblio.get("first_page"),
        "last_page": biblio.get("last_page"),
    }
