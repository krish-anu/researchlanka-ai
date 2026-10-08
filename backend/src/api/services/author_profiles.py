"""Author profiles: applications, publication claims, contributions and public profiles.

The workflow, end to end:

1. A researcher applies (from the author sign-up form, or from an existing
   account). The application names the publications they wrote and which
   listed author they are on each one — researcher identity in this dataset is
   a name string, so a claim has to point at a specific listed author.
2. An administrator approves, rejects or asks for changes, using evidence
   computed here: name match, ORCID match, email domain, competing claims.
3. An approved author edits their bio and links directly. Edits to a
   publication and newly added publications are contributions, which wait for
   an administrator.
4. Approved edits land in `publication_corrections`, merged into the public view
   on read so a pipeline reload cannot overwrite them. Approved new publications
   are loaded into `final_publications` as `author_submission` records after an
   administrator confirms the AI relevance check and Sri Lanka-led ownership.

Who the caller is comes from the frontend server, which holds the admin API
token and forwards the signed-in account as actor headers. Ownership is still
re-checked here on every write: a valid token says the request came from the
frontend, not that this actor owns this profile.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from psycopg.rows import dict_row

from src.api.core.errors import APIError
from src.api.core.serializers import (
    list_response,
    normalize_value,
    publication_summary,
    split_semicolon_value,
)
from src.api.repositories.sql import (
    BASE_COLUMNS,
    PUBLIC_PUBLICATION_SOURCE_SQL,
    PUBLICATION_YEAR_SQL,
    quote_identifier,
    select_columns,
)
from src.api.services.ai_review import record_human_acceptance
from src.api.services.author_publication_lookup import (
    Classifier,
    classify_submission,
    lookup_doi,
)
from src.api.services.author_reference import (
    PROFILE_SPELLINGS_SQL,
    canonical_institution,
    category_taxonomy,
    claimed_name_profiles,
    field_domains,
    institution_breakdown,
    suggest_category,
)
from src.database.connection import get_connection
from src.database.final_schema import AUTHOR_SUBMISSION_SOURCE
from src.utils.doi import is_valid_doi, normalize_doi


PROFILE_STATUSES = ("pending", "changes_requested", "approved", "rejected")
OPEN_PROFILE_STATUSES = ("pending", "changes_requested")
CLAIM_STATUSES = ("pending", "approved", "rejected")
CONTRIBUTION_TYPES = ("publication_edit", "new_publication")
CONTRIBUTION_STATUSES = ("pending", "approved", "rejected", "withdrawn")
APPLICATION_DECISIONS = ("approve", "request_changes", "reject")
CONTRIBUTION_DECISIONS = ("approve", "reject")

# Fields an author may correct on a publication they have an approved claim on.
# Must match `corrected_columns` in refresh_public_publication_views()
# (database/migrations/016_create_author_profiles.sql). Identity fields (DOI,
# author list, affiliations) are deliberately absent: changing them affects
# deduplication and other people's profiles, so they go through flags.
EDITABLE_PUBLICATION_FIELDS: dict[str, str] = {
    "title": "Title",
    "abstract": "Abstract",
    "keywords": "Keywords",
    "publication_year": "Publication year",
    "type": "Publication type",
    "journal": "Journal or venue",
    "publisher": "Publisher",
    "volume": "Volume",
    "issue": "Issue",
    "first_page": "First page",
    "last_page": "Last page",
    "language": "Language",
    "url": "Link",
    "pdf_url": "PDF link",
}
FIELD_MAX_LENGTH = {
    "title": 500,
    "abstract": 10_000,
    "keywords": 1_000,
    "journal": 300,
    "publisher": 300,
    "url": 500,
    "pdf_url": 500,
}
DEFAULT_FIELD_MAX_LENGTH = 120
MULTILINE_FIELDS = {"abstract", "bio", "application_note", "author_note"}
URL_FIELDS = {"url", "pdf_url"}

PUBLICATION_TYPES = (
    "article",
    "journal-article",
    "proceedings-article",
    "book-chapter",
    "book",
    "preprint",
    "dissertation",
    "report",
    "dataset",
    "other",
)

PROFILE_LINK_FIELDS = {
    "website_url": ("Website", ()),
    "google_scholar_url": ("Google Scholar", ("scholar.google.",)),
    "researchgate_url": ("ResearchGate", ("researchgate.net",)),
    "linkedin_url": ("LinkedIn", ("linkedin.com",)),
}
FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.in",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
    "zoho.com",
}

MAX_NAME_VARIANTS = 20
MAX_CLAIMS_PER_REQUEST = 200
MAX_PENDING_CLAIMS = 500
MAX_AFFILIATIONS = 20
MAX_PENDING_CONTRIBUTIONS = 20
MAX_SUBMISSION_AUTHORS = 100
MIN_ABSTRACT_LENGTH = 50
MIN_TITLE_MATCH_LENGTH = 20
MIN_PUBLICATION_YEAR = 1950

WHITESPACE_PATTERN = re.compile(r"[ \t\f\v]+")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ORCID_PATTERN = re.compile(r"(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dX])")
TITLE_KEY_PATTERN = re.compile(r"[^a-z0-9]+")
NAME_TOKEN_PATTERN = re.compile(r"[^\W\d_]+")

Actor = Mapping[str, str]
DoiLookup = Callable[[str], dict[str, Any]]


# --------------------------------------------------------------- validation


def clean_text(
    value: Any,
    *,
    field: str,
    label: str | None = None,
    max_length: int | None = None,
    required: bool = False,
) -> str:
    """Trim, drop control characters and enforce length; keep newlines only in long text."""

    raw = CONTROL_CHARACTERS.sub("", str(value if value is not None else ""))
    if field in MULTILINE_FIELDS:
        lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in raw.replace("\r\n", "\n").split("\n")]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    else:
        text = WHITESPACE_PATTERN.sub(" ", raw.replace("\n", " ").replace("\r", " ")).strip()
    name = label or field.replace("_", " ").capitalize()
    if required and not text:
        raise APIError("field_required", f"{name} is required.", status=400, details={"field": field})
    limit = max_length or FIELD_MAX_LENGTH.get(field, DEFAULT_FIELD_MAX_LENGTH)
    if len(text) > limit:
        raise APIError(
            "field_too_long",
            f"{name} must be at most {limit} characters.",
            status=400,
            details={"field": field, "max_length": limit},
        )
    return text


def normalize_orcid(value: Any) -> str | None:
    """Return a checksum-valid ORCID iD as 0000-0000-0000-000X, or None when blank."""

    text = str(value or "").strip().upper()
    if not text:
        return None
    text = re.sub(r"^HTTPS?://(WWW\.)?ORCID\.ORG/", "", text)
    match = ORCID_PATTERN.fullmatch(text)
    if not match:
        raise APIError(
            "invalid_orcid",
            "Enter an ORCID iD such as 0000-0002-1825-0097.",
            status=400,
            details={"field": "orcid"},
        )
    orcid = "-".join(match.groups())
    if not orcid_checksum_ok(orcid):
        raise APIError(
            "invalid_orcid",
            "That ORCID iD fails its checksum. Check it for a typo.",
            status=400,
            details={"field": "orcid"},
        )
    return orcid


def orcid_checksum_ok(orcid: str) -> bool:
    """ISO 7064 MOD 11-2, the check digit ORCID uses."""

    digits = orcid.replace("-", "")
    total = 0
    for character in digits[:-1]:
        total = (total + int(character)) * 2
    result = (12 - total % 11) % 11
    return digits[-1] == ("X" if result == 10 else str(result))


def normalize_url(value: Any, *, field: str, label: str, hosts: tuple[str, ...] = ()) -> str | None:
    text = clean_text(value, field=field, label=label, max_length=500)
    if not text:
        return None
    parsed = urlparse(text)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not host:
        raise APIError(
            "invalid_url",
            f"{label} must be a full link starting with https://.",
            status=400,
            details={"field": field},
        )
    if hosts and not any(fragment in host for fragment in hosts):
        raise APIError(
            "invalid_url",
            f"{label} must be a {label} link.",
            status=400,
            details={"field": field},
        )
    return text


def parse_year(value: Any, *, field: str = "publication_year") -> int:
    text = str(value if value is not None else "").strip()
    latest = datetime.now(UTC).year + 1
    try:
        year = int(text)
    except ValueError:
        year = 0
    if year < MIN_PUBLICATION_YEAR or year > latest:
        raise APIError(
            "invalid_year",
            f"Publication year must be between {MIN_PUBLICATION_YEAR} and {latest}.",
            status=400,
            details={"field": field},
        )
    return year


def parse_publication_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise APIError(
            "invalid_date",
            "Publication date must be a full date (YYYY-MM-DD), or left blank.",
            status=400,
            details={"field": "publication_date"},
        ) from exc


def string_list(value: Any) -> list[str]:
    """Accept a JSON list or a newline/semicolon separated string."""

    if value is None:
        return []
    if isinstance(value, str):
        items: Iterable[Any] = re.split(r"[\n;]", value)
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise APIError("invalid_request", "Expected a list of values.", status=400)
    return [str(item) for item in items]


# ------------------------------------------------------------ name evidence


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def name_tokens(name: Any) -> list[str]:
    """Lower-cased name parts, with "Surname, Given" turned into "Given Surname"."""

    text = _strip_marks(str(name or ""))
    if "," in text:
        surname, _, given = text.partition(",")
        text = f"{given} {surname}"
    return NAME_TOKEN_PATTERN.findall(text.casefold())


def _match_tokens(left: list[str], right: list[str]) -> str:
    if not left or not right:
        return "none"
    if left == right:
        return "exact"
    if left[-1] != right[-1]:
        return "none"
    left_given, right_given = left[:-1], right[:-1]
    if not left_given or not right_given:
        return "initials"
    left_initials = [token[0] for token in left_given]
    right_initials = [token[0] for token in right_given]
    shorter, longer = sorted((left_initials, right_initials), key=len)
    if set(shorter) <= set(longer):
        return "initials"
    return "none"


NAME_MATCH_RANK = {"none": 0, "initials": 1, "exact": 2}


def name_match(left: Any, right: Any) -> str:
    """How strongly two author names agree: "exact", "initials" or "none".

    Sri Lankan names are often printed surname-first without a comma
    ("Perera A"), so both orders of the left name are tried.
    """

    left_tokens = name_tokens(left)
    right_tokens = name_tokens(right)
    candidates = [left_tokens]
    if len(left_tokens) > 1:
        candidates.append([*left_tokens[1:], left_tokens[0]])
    return max(
        (_match_tokens(candidate, right_tokens) for candidate in candidates),
        key=NAME_MATCH_RANK.__getitem__,
        default="none",
    )


def best_name_match(listed_name: Any, profile_names: Iterable[Any]) -> str:
    return max(
        (name_match(listed_name, name) for name in profile_names),
        key=NAME_MATCH_RANK.__getitem__,
        default="none",
    )


def same_listed_name(left: Any, right: Any) -> bool:
    return " ".join(str(left or "").split()).casefold() == " ".join(str(right or "").split()).casefold()


def title_key(title: Any) -> str:
    return TITLE_KEY_PATTERN.sub("", str(title or "").casefold())


def slugify(name: str) -> str:
    text = TITLE_KEY_PATTERN.sub("-", _strip_marks(name).casefold()).strip("-")
    return text[:60].strip("-") or "author"


def email_domain_evidence(email: Any) -> dict[str, str]:
    """Classify the account's email domain, as a hint for the reviewing admin.

    The email address is not verified, so this says where the applicant claims
    to receive mail, not that they do.
    """

    text = str(email or "").strip().casefold()
    domain = text.rsplit("@", 1)[-1] if "@" in text else ""
    dotted = f".{domain}."
    if not domain:
        kind = "unknown"
    elif domain in FREE_EMAIL_DOMAINS:
        kind = "free_webmail"
    elif ".ac." in dotted or domain.endswith(".edu"):
        kind = "academic"
    elif domain.endswith(".lk"):
        kind = "sri_lankan_organisation"
    else:
        kind = "other"
    return {"domain": domain, "kind": kind}


def profile_names(profile: Mapping[str, Any]) -> list[str]:
    return [str(profile.get("display_name") or ""), *list(profile.get("name_variants") or [])]


def orcid_in_publication(orcid: str | None, author_orcids: Any) -> bool:
    if not orcid:
        return False
    return orcid in str(author_orcids or "").upper()


# ---------------------------------------------------------------- payloads


def profile_payload(row: Mapping[str, Any], *, public: bool = False) -> dict[str, Any]:
    payload = {
        "profile_id": row.get("profile_id"),
        "slug": row.get("slug"),
        "display_name": row.get("display_name"),
        "name_variants": list(row.get("name_variants") or []),
        "orcid": row.get("orcid"),
        "institution": row.get("institution"),
        "department": row.get("department") or "",
        "position_title": row.get("position_title") or "",
        "bio": row.get("bio") or "",
        "links": {field: row.get(field) for field in PROFILE_LINK_FIELDS},
        "status": row.get("status"),
    }
    if public:
        payload["verified_at"] = row.get("decided_at")
        return normalize_value(payload)
    payload.update(
        {
            "user_id": row.get("user_id"),
            "user_email": row.get("user_email"),
            "application_note": row.get("application_note") or "",
            "decision_reason": row.get("decision_reason") or "",
            "decided_by": row.get("decided_by_name") or row.get("decided_by_email"),
            "decided_at": row.get("decided_at"),
            "record_version": row.get("record_version"),
            "submitted_at": row.get("submitted_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )
    return normalize_value(payload)


def claim_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_value(
        {
            "claim_id": row.get("claim_id"),
            "profile_id": row.get("profile_id"),
            "publication_key": row.get("publication_key"),
            "name_as_listed": row.get("name_as_listed"),
            "author_position": row.get("author_position"),
            "status": row.get("status"),
            "decision_reason": row.get("decision_reason") or "",
            "decided_at": row.get("decided_at"),
            "created_at": row.get("created_at"),
            "publication": {
                "title": row.get("publication_title"),
                "publication_year": row.get("publication_year"),
                "is_public": bool(row.get("is_public")),
            },
        }
    )


def contribution_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_value(
        {
            "contribution_id": row.get("contribution_id"),
            "profile_id": row.get("profile_id"),
            "contribution_type": row.get("contribution_type"),
            "publication_key": row.get("publication_key"),
            "proposed": row.get("proposed") or {},
            "base_snapshot": row.get("base_snapshot") or {},
            "author_note": row.get("author_note") or "",
            "lookup_source": row.get("lookup_source"),
            "lookup_evidence": row.get("lookup_evidence") or {},
            "classifier": row.get("classifier") or {},
            "status": row.get("status"),
            "decision_reason": row.get("decision_reason") or "",
            "decided_by": row.get("decided_by_name") or row.get("decided_by_email"),
            "decided_at": row.get("decided_at"),
            "record_version": row.get("record_version"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )


def require_actor(actor: Actor | None) -> dict[str, str]:
    prepared = {
        "id": str((actor or {}).get("id") or "").strip(),
        "email": str((actor or {}).get("email") or "").strip().lower(),
        "name": str((actor or {}).get("name") or "").strip(),
    }
    if not prepared["id"] or not prepared["email"]:
        raise APIError("actor_required", "A signed-in account is required.", status=401)
    return prepared


def actor_from_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    headers = headers or {}
    return {
        "id": str(headers.get("x-researchlanka-actor-id") or ""),
        "email": str(headers.get("x-researchlanka-actor-email") or ""),
        "name": str(headers.get("x-researchlanka-actor-name") or ""),
    }


# ------------------------------------------------------- validation: inputs


def validate_application(payload: Mapping[str, Any]) -> dict[str, Any]:
    display_name = clean_text(
        payload.get("display_name"), field="display_name", label="Name", max_length=120, required=True
    )
    if len(display_name) < 3:
        raise APIError("field_required", "Enter your full name.", status=400, details={"field": "display_name"})

    variants: list[str] = []
    for raw in string_list(payload.get("name_variants")):
        variant = clean_text(raw, field="name_variants", label="Name variant", max_length=120)
        if variant and not same_listed_name(variant, display_name) and not any(
            same_listed_name(variant, existing) for existing in variants
        ):
            variants.append(variant)
    if len(variants) > MAX_NAME_VARIANTS:
        raise APIError(
            "too_many_name_variants",
            f"List at most {MAX_NAME_VARIANTS} name variants.",
            status=400,
            details={"field": "name_variants"},
        )

    return {
        "display_name": display_name,
        "name_variants": variants,
        "orcid": normalize_orcid(payload.get("orcid")),
        "institution": clean_text(
            payload.get("institution"), field="institution", label="Institution", max_length=200, required=True
        ),
        "department": clean_text(payload.get("department"), field="department", label="Department", max_length=200),
        "position_title": clean_text(
            payload.get("position_title"), field="position_title", label="Position", max_length=120
        ),
        "application_note": clean_text(
            payload.get("application_note"), field="application_note", label="Note", max_length=2_000
        ),
        "claims": validate_claim_requests(payload.get("claims")),
    }


def validate_claim_requests(value: Any) -> list[dict[str, str]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise APIError("invalid_request", "claims must be a list.", status=400)
    if len(value) > MAX_CLAIMS_PER_REQUEST:
        raise APIError(
            "too_many_claims",
            f"Claim at most {MAX_CLAIMS_PER_REQUEST} publications at a time.",
            status=400,
        )
    claims: dict[str, dict[str, str]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise APIError("invalid_request", "Each claim must be an object.", status=400)
        key = clean_text(item.get("publication_key"), field="publication_key", max_length=500, required=True)
        listed = clean_text(
            item.get("name_as_listed"), field="name_as_listed", label="Your name as listed", max_length=200, required=True
        )
        claims[key] = {"publication_key": key, "name_as_listed": listed}
    return list(claims.values())


def validate_profile_update(payload: Mapping[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "bio": clean_text(payload.get("bio"), field="bio", label="Bio", max_length=2_000),
        "department": clean_text(payload.get("department"), field="department", label="Department", max_length=200),
        "position_title": clean_text(
            payload.get("position_title"), field="position_title", label="Position", max_length=120
        ),
    }
    links = payload.get("links") if isinstance(payload.get("links"), Mapping) else payload
    for field, (label, hosts) in PROFILE_LINK_FIELDS.items():
        updates[field] = normalize_url(links.get(field), field=field, label=label, hosts=hosts)
    return updates


def validate_affiliations(value: Any) -> list[dict[str, Any]]:
    """An author's institutions over time, newest first.

    Years are optional, but when given they decide which institution a paper
    from a given year is attributed to on the profile. A missing end year
    means the author is still there.
    """

    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise APIError("invalid_request", "affiliations must be a list.", status=400)
    if len(value) > MAX_AFFILIATIONS:
        raise APIError(
            "too_many_affiliations",
            f"List at most {MAX_AFFILIATIONS} affiliations.",
            status=400,
            details={"field": "affiliations"},
        )
    affiliations = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise APIError("invalid_request", "Each affiliation must be an object.", status=400)
        where = {"field": "affiliations", "index": index}
        institution = clean_text(item.get("institution"), field="institution", label="Institution", max_length=300)
        if not institution:
            raise APIError("field_required", "Each affiliation needs an institution.", status=400, details=where)
        years = []
        for key in ("start_year", "end_year"):
            raw = item.get(key)
            if raw in (None, ""):
                years.append(None)
                continue
            try:
                years.append(parse_year(raw, field=key))
            except APIError as error:
                raise APIError(error.code, error.message, status=400, details=where) from error
        start, end = years
        if start is not None and end is not None and start > end:
            raise APIError(
                "invalid_years",
                f"The years for {institution} end before they start.",
                status=400,
                details=where,
            )
        affiliations.append(
            {
                "institution": canonical_institution(institution)["label"],
                "department": clean_text(item.get("department"), field="department", label="Department", max_length=200),
                "position_title": clean_text(
                    item.get("position_title"), field="position_title", label="Position", max_length=120
                ),
                "start_year": start,
                "end_year": end,
            }
        )
    # Current positions first, then most recently ended.
    return sorted(
        affiliations,
        key=lambda item: (item["end_year"] is not None, -(item["end_year"] or 0), -(item["start_year"] or 0)),
    )


def affiliation_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_value(
        {
            "institution": row.get("institution"),
            "department": row.get("department") or "",
            "position_title": row.get("position_title") or "",
            "start_year": row.get("start_year"),
            "end_year": row.get("end_year"),
        }
    )


def _affiliations(cursor: Any, profile_id: Any) -> list[dict[str, Any]]:
    rows = _fetch_all(
        cursor,
        """
        SELECT * FROM author_profile_affiliations
        WHERE profile_id = %s
        ORDER BY end_year IS NOT NULL, end_year DESC NULLS FIRST, start_year DESC NULLS LAST, created_at
        """,
        [profile_id],
    )
    return [affiliation_payload(row) for row in rows]


def coerce_editable_value(field: str, value: Any) -> Any:
    label = EDITABLE_PUBLICATION_FIELDS[field]
    if field == "publication_year":
        return parse_year(value)
    if field in URL_FIELDS:
        url = normalize_url(value, field=field, label=label)
        if url is None:
            raise blank_field_error(field, label)
        return url
    text = clean_text(value, field=field, label=label)
    if not text:
        raise blank_field_error(field, label)
    if field == "type" and text not in PUBLICATION_TYPES:
        raise APIError(
            "invalid_type",
            "Choose a publication type from the list.",
            status=400,
            details={"field": field, "allowed": list(PUBLICATION_TYPES)},
        )
    return text


def blank_field_error(field: str, label: str) -> APIError:
    return APIError(
        "field_required",
        f"{label} cannot be cleared here. Leave it unchanged, or flag the record so an administrator can remove the value.",
        status=400,
        details={"field": field},
    )


def comparable(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())


def diff_publication_changes(
    changes: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate proposed values and keep only those that differ from the public record."""

    if not isinstance(changes, Mapping) or not changes:
        raise APIError("no_changes", "Change at least one field.", status=400)
    unknown = sorted(set(changes) - set(EDITABLE_PUBLICATION_FIELDS))
    if unknown:
        raise APIError(
            "field_not_editable",
            "Some fields cannot be edited by authors.",
            status=400,
            details={"fields": unknown, "editable": list(EDITABLE_PUBLICATION_FIELDS)},
        )
    proposed: dict[str, Any] = {}
    base: dict[str, Any] = {}
    for field in EDITABLE_PUBLICATION_FIELDS:
        if field not in changes:
            continue
        value = coerce_editable_value(field, changes[field])
        if comparable(value) == comparable(current.get(field)):
            continue
        proposed[field] = value
        base[field] = normalize_value(current.get(field))
    if not proposed:
        raise APIError("no_changes", "Nothing differs from the current record.", status=400)
    return proposed, base


def validate_new_publication(payload: Mapping[str, Any]) -> dict[str, Any]:
    doi_text = str(payload.get("doi") or "").strip()
    doi = normalize_doi(doi_text) if doi_text else None
    if doi_text and (not doi or not is_valid_doi(doi)):
        raise APIError("invalid_doi", "Enter a DOI such as 10.1234/abcd.5678.", status=400, details={"field": "doi"})

    title = clean_text(payload.get("title"), field="title", label="Title", required=True)
    abstract = clean_text(payload.get("abstract"), field="abstract", label="Abstract", required=True)
    if len(abstract) < MIN_ABSTRACT_LENGTH:
        raise APIError(
            "abstract_too_short",
            f"Add the full abstract (at least {MIN_ABSTRACT_LENGTH} characters). The AI relevance check reads it.",
            status=400,
            details={"field": "abstract"},
        )
    publication_type = clean_text(payload.get("type"), field="type", label="Publication type") or "article"
    if publication_type not in PUBLICATION_TYPES:
        raise APIError(
            "invalid_type",
            "Choose a publication type from the list.",
            status=400,
            details={"field": "type", "allowed": list(PUBLICATION_TYPES)},
        )
    url = normalize_url(payload.get("url"), field="url", label="Link")
    if not doi and not url:
        raise APIError(
            "link_required",
            "A publication without a DOI needs a link where an administrator can check it.",
            status=400,
            details={"field": "url"},
        )

    authors = validate_submission_authors(payload.get("authors"))
    submitter = mark_submitter(authors, payload.get("your_author_name"))
    category = validate_category(payload.get("primary_field"), payload.get("primary_subfield"))

    return {
        "doi": doi,
        "title": title,
        "abstract": abstract,
        "keywords": clean_text(payload.get("keywords"), field="keywords", label="Keywords"),
        "publication_year": parse_year(payload.get("publication_year")),
        "publication_date": parse_publication_date(payload.get("publication_date")),
        "type": publication_type,
        "journal": clean_text(payload.get("journal"), field="journal", label="Journal or venue"),
        "publisher": clean_text(payload.get("publisher"), field="publisher", label="Publisher"),
        "volume": clean_text(payload.get("volume"), field="volume", label="Volume"),
        "issue": clean_text(payload.get("issue"), field="issue", label="Issue"),
        "first_page": clean_text(payload.get("first_page"), field="first_page", label="First page"),
        "last_page": clean_text(payload.get("last_page"), field="last_page", label="Last page"),
        "language": clean_text(payload.get("language"), field="language", label="Language"),
        "url": url,
        "pdf_url": normalize_url(payload.get("pdf_url"), field="pdf_url", label="PDF link"),
        "authors": authors,
        "your_author_name": submitter["name"],
        **category,
    }


def validate_category(field: Any, subfield: Any) -> dict[str, str]:
    """An optional field/subfield from the classifier taxonomy; blank leaves it to the model."""

    field_text = clean_text(field, field="primary_field", label="Field", max_length=200)
    subfield_text = clean_text(subfield, field="primary_subfield", label="Subfield", max_length=200)
    taxonomy = category_taxonomy()
    if field_text and taxonomy and field_text not in taxonomy:
        raise APIError("invalid_category", "Choose a field from the list.", status=400, details={"field": "primary_field"})
    if subfield_text:
        if not field_text:
            raise APIError("invalid_category", "Choose the field first.", status=400, details={"field": "primary_field"})
        if taxonomy and subfield_text not in taxonomy.get(field_text, []):
            raise APIError(
                "invalid_category",
                "That subfield is not part of the chosen field.",
                status=400,
                details={"field": "primary_subfield"},
            )
    return {"primary_field": field_text, "primary_subfield": subfield_text}


def mark_submitter(authors: list[dict[str, Any]], your_author_name: Any) -> dict[str, Any]:
    """Exactly one author row is the person submitting.

    Rows say so with `is_submitter`; older clients send `your_author_name`
    instead, which is matched against the names.
    """

    flagged = [author for author in authors if author.get("is_submitter")]
    if not flagged and your_author_name:
        flagged = [author for author in authors if same_listed_name(author["name"], your_author_name)][:1]
        for author in flagged:
            author["is_submitter"] = True
    if len(flagged) != 1:
        raise APIError(
            "author_not_listed",
            "Mark which listed author you are." if not flagged else "Only one author can be you.",
            status=400,
            details={"field": "your_author_name"},
        )
    return flagged[0]


def validate_submission_authors(value: Any) -> list[dict[str, Any]]:
    """Every author with the institution they were at for this publication.

    The institution is required for each author because it is what this
    publication counts towards in institution rankings — and it is recorded
    per publication, so an author who later moves does not take their earlier
    work with them.
    """
    if not isinstance(value, list) or not value:
        raise APIError("authors_required", "List every author, in order.", status=400, details={"field": "authors"})
    if len(value) > MAX_SUBMISSION_AUTHORS:
        raise APIError(
            "too_many_authors",
            f"List at most {MAX_SUBMISSION_AUTHORS} authors.",
            status=400,
            details={"field": "authors"},
        )
    authors: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        row = item if isinstance(item, Mapping) else {"name": item}
        cleaned_name = clean_text(row.get("name"), field="authors", label="Author name", max_length=200)
        if not cleaned_name:
            continue
        where = {"field": "authors", "index": index}
        if ";" in cleaned_name:
            raise APIError("invalid_author_name", "Put each author on their own row.", status=400, details=where)
        if any(same_listed_name(existing["name"], cleaned_name) for existing in authors):
            raise APIError(
                "duplicate_author",
                f"{cleaned_name} is listed twice.",
                status=400,
                details=where,
            )
        institution_text = clean_text(row.get("institution"), field="institution", label="Institution", max_length=300)
        if not institution_text:
            raise APIError(
                "institution_required",
                f"Add the institution {cleaned_name} was at for this publication.",
                status=400,
                details={**where, "field": "institution"},
            )
        institution = canonical_institution(institution_text)
        country = clean_text(row.get("country_code"), field="country_code", label="Country", max_length=60).upper()
        if country and not re.fullmatch(r"[A-Z]{2}", country):
            raise APIError("invalid_country", "Use a two-letter country code, e.g. LK.", status=400, details=where)
        profile_slug = clean_text(row.get("profile_slug"), field="profile_slug", max_length=80) or None
        authors.append(
            {
                "name": cleaned_name,
                "affiliation": clean_text(row.get("affiliation"), field="affiliation", label="Department", max_length=500),
                "institution": institution["label"],
                "country_code": institution["country_code"] or country or None,
                "profile_slug": profile_slug,
                "is_submitter": bool(row.get("is_submitter")),
            }
        )
    if not authors:
        raise APIError("authors_required", "List every author, in order.", status=400, details={"field": "authors"})
    return authors


# ------------------------------------------------------------ SQL helpers


def _fetch_all(cursor: Any, sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    cursor.execute(sql, list(params or []))
    return [dict(row) for row in cursor.fetchall()]


def _fetch_one(cursor: Any, sql: str, params: Iterable[Any] | None = None) -> dict[str, Any] | None:
    cursor.execute(sql, list(params or []))
    row = cursor.fetchone()
    return dict(row) if row else None


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(normalize_value(value))


def _insert_event(
    cursor: Any,
    *,
    profile_id: Any,
    subject_type: str,
    subject_id: Any,
    event_type: str,
    actor: Actor,
    from_status: str | None = None,
    to_status: str | None = None,
    notes: str = "",
) -> None:
    cursor.execute(
        """
        INSERT INTO author_profile_events (
            profile_id, subject_type, subject_id, event_type,
            actor_id, actor_email, actor_name, from_status, to_status, notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            profile_id,
            subject_type,
            subject_id,
            event_type,
            actor.get("id"),
            actor.get("email"),
            actor.get("name"),
            from_status,
            to_status,
            notes[:2_000],
        ),
    )


def _profile_for_actor(cursor: Any, actor: Actor, *, lock: bool = False) -> dict[str, Any] | None:
    return _fetch_one(
        cursor,
        f"SELECT * FROM author_profiles WHERE user_id = %s{' FOR UPDATE' if lock else ''}",
        [actor["id"]],
    )


def _approved_profile_for_actor(cursor: Any, actor: Actor, *, lock: bool = False) -> dict[str, Any]:
    profile = _profile_for_actor(cursor, actor, lock=lock)
    if profile is None or profile["status"] != "approved":
        raise APIError(
            "author_profile_required",
            "This needs an approved author profile.",
            status=403,
        )
    return profile


def _unique_slug(cursor: Any, display_name: str) -> str:
    base = slugify(display_name)
    rows = _fetch_all(
        cursor,
        "SELECT slug FROM author_profiles WHERE slug = %s OR slug LIKE %s",
        [base, f"{base}-%"],
    )
    taken = {row["slug"] for row in rows}
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


def _public_rows_by_key(cursor: Any, keys: list[str], columns: str) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    rows = _fetch_all(
        cursor,
        f"""
        SELECT publication_key, {columns}
        FROM public_eligible_publications
        WHERE publication_key = ANY(%s::text[])
        """,
        [keys],
    )
    return {row["publication_key"]: row for row in rows}


def _resolve_claims(cursor: Any, claims: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Check each claim names a public publication and one of its listed authors."""

    publications = _public_rows_by_key(
        cursor,
        [claim["publication_key"] for claim in claims],
        "title, authors",
    )
    resolved = []
    for claim in claims:
        publication = publications.get(claim["publication_key"])
        if publication is None:
            raise APIError(
                "publication_not_found",
                "One of the claimed publications is not in the public dataset.",
                status=400,
                details={"publication_key": claim["publication_key"]},
            )
        authors = split_semicolon_value(publication.get("authors"))
        position = next(
            (index for index, name in enumerate(authors, start=1) if same_listed_name(name, claim["name_as_listed"])),
            None,
        )
        if position is None:
            raise APIError(
                "author_not_listed",
                "Pick your name from the publication's author list.",
                status=400,
                details={"publication_key": claim["publication_key"], "title": publication.get("title")},
            )
        resolved.append(
            {
                "publication_key": claim["publication_key"],
                "name_as_listed": authors[position - 1],
                "author_position": position,
            }
        )
    return resolved


def _insert_claims(
    cursor: Any,
    profile_id: Any,
    claims: list[dict[str, Any]],
    *,
    status: str = "pending",
) -> int:
    inserted = 0
    for claim in claims:
        cursor.execute(
            """
            INSERT INTO author_publication_claims (
                profile_id, publication_key, name_as_listed, author_position, status
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (profile_id, publication_key) DO UPDATE
            -- A declined or removed claim can be asked for again; it goes back
            -- to the administrator rather than being silently ignored.
            SET status = EXCLUDED.status,
                name_as_listed = EXCLUDED.name_as_listed,
                author_position = EXCLUDED.author_position,
                decision_reason = '',
                decided_by_id = NULL,
                decided_by_email = NULL,
                decided_by_name = NULL,
                decided_at = NULL,
                updated_at = now()
            WHERE author_publication_claims.status = 'rejected'
            """,
            (profile_id, claim["publication_key"], claim["name_as_listed"], claim.get("author_position"), status),
        )
        inserted += int(getattr(cursor, "rowcount", 0) or 0)
    return inserted


CLAIMS_WITH_PUBLICATION_SQL = """
    SELECT c.*,
           COALESCE(v.title, p.title) AS publication_title,
           COALESCE(v.publication_year, p.publication_year,
                    EXTRACT(YEAR FROM p.publication_date)::int) AS publication_year,
           (v.publication_key IS NOT NULL) AS is_public
    FROM author_publication_claims c
    JOIN final_publications p ON p.publication_key = c.publication_key
    LEFT JOIN public_eligible_publications v ON v.publication_key = c.publication_key
"""


# ------------------------------------------------------------ author side


def get_author_workspace(connection: Any, actor: Actor | None) -> dict[str, Any]:
    """Everything the signed-in author sees about their own profile."""

    actor = require_actor(actor)
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _profile_for_actor(cursor, actor)
        if profile is None:
            return {"profile": None, "claims": [], "contributions": [], "limits": workspace_limits()}
        claims = _fetch_all(
            cursor,
            f"{CLAIMS_WITH_PUBLICATION_SQL} WHERE c.profile_id = %s ORDER BY c.created_at, c.claim_id",
            [profile["profile_id"]],
        )
        contributions = _fetch_all(
            cursor,
            """
            SELECT * FROM author_contributions
            WHERE profile_id = %s
            ORDER BY created_at DESC
            LIMIT 200
            """,
            [profile["profile_id"]],
        )
        affiliations = _affiliations(cursor, profile["profile_id"])
    payload = profile_payload(profile)
    payload["affiliations"] = affiliations
    return {
        "profile": payload,
        "claims": [claim_payload(row) for row in claims],
        "contributions": [contribution_payload(row) for row in contributions],
        "limits": workspace_limits(),
    }


def workspace_limits() -> dict[str, Any]:
    return {
        "max_pending_contributions": MAX_PENDING_CONTRIBUTIONS,
        "max_claims_per_request": MAX_CLAIMS_PER_REQUEST,
        "editable_fields": EDITABLE_PUBLICATION_FIELDS,
        "publication_types": list(PUBLICATION_TYPES),
    }


def submit_application(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create an application, or resubmit one that is pending or needs changes."""

    actor = require_actor(actor)
    data = validate_application(payload)
    with connection.cursor(row_factory=dict_row) as cursor:
        existing = _profile_for_actor(cursor, actor, lock=True)
        if existing is not None and existing["status"] not in OPEN_PROFILE_STATUSES:
            raise APIError(
                "application_closed",
                "This account already has a decided author application. Contact an administrator to change it.",
                status=409,
                details={"status": existing["status"]},
            )
        if data["orcid"]:
            holder = _fetch_one(
                cursor,
                "SELECT profile_id FROM author_profiles WHERE orcid = %s AND status = 'approved'",
                [data["orcid"]],
            )
            if holder is not None and (existing is None or holder["profile_id"] != existing["profile_id"]):
                raise APIError(
                    "orcid_in_use",
                    "An approved profile already uses this ORCID iD. Contact an administrator if it is yours.",
                    status=409,
                    details={"field": "orcid"},
                )
        claims = _resolve_claims(cursor, data["claims"])

        if existing is None:
            profile = _fetch_one(
                cursor,
                """
                INSERT INTO author_profiles (
                    user_id, user_email, slug, display_name, name_variants, orcid,
                    institution, department, position_title, application_note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                [
                    actor["id"],
                    actor["email"],
                    _unique_slug(cursor, data["display_name"]),
                    data["display_name"],
                    data["name_variants"],
                    data["orcid"],
                    data["institution"],
                    data["department"],
                    data["position_title"],
                    data["application_note"],
                ],
            )
            event_type = "application_submitted"
        else:
            profile = _fetch_one(
                cursor,
                """
                UPDATE author_profiles
                SET user_email = %s,
                    display_name = %s,
                    name_variants = %s,
                    orcid = %s,
                    institution = %s,
                    department = %s,
                    position_title = %s,
                    application_note = %s,
                    status = 'pending',
                    record_version = record_version + 1,
                    submitted_at = now(),
                    updated_at = now()
                WHERE profile_id = %s
                RETURNING *
                """,
                [
                    actor["email"],
                    data["display_name"],
                    data["name_variants"],
                    data["orcid"],
                    data["institution"],
                    data["department"],
                    data["position_title"],
                    data["application_note"],
                    existing["profile_id"],
                ],
            )
            # A resubmission replaces the claim list rather than appending to it.
            cursor.execute(
                "DELETE FROM author_publication_claims WHERE profile_id = %s AND status = 'pending'",
                [existing["profile_id"]],
            )
            event_type = "application_resubmitted"

        assert profile is not None
        _insert_claims(cursor, profile["profile_id"], claims)
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="profile",
            subject_id=profile["profile_id"],
            event_type=event_type,
            actor=actor,
            from_status=existing["status"] if existing else None,
            to_status="pending",
            notes=f"{len(claims)} publication claim(s)",
        )
    return get_author_workspace(connection, actor)


def update_profile(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Bio, position and links: an approved author's own words, live immediately."""

    actor = require_actor(actor)
    updates = validate_profile_update(payload)
    # Absent means "leave the history alone", so a form without the history
    # section cannot wipe it.
    affiliations = validate_affiliations(payload["affiliations"]) if "affiliations" in payload else None
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor, lock=True)
        assignments = ", ".join(f"{quote_identifier(field)} = %s" for field in updates)
        cursor.execute(
            f"UPDATE author_profiles SET {assignments}, updated_at = now() WHERE profile_id = %s",
            [*updates.values(), profile["profile_id"]],
        )
        changed = [field for field, value in updates.items() if value != profile.get(field)]
        if affiliations is not None:
            cursor.execute("DELETE FROM author_profile_affiliations WHERE profile_id = %s", [profile["profile_id"]])
            for item in affiliations:
                cursor.execute(
                    """
                    INSERT INTO author_profile_affiliations (
                        profile_id, institution, department, position_title, start_year, end_year
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        profile["profile_id"],
                        item["institution"],
                        item["department"],
                        item["position_title"],
                        item["start_year"],
                        item["end_year"],
                    ],
                )
            changed.append("affiliations")
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="profile",
            subject_id=profile["profile_id"],
            event_type="profile_updated",
            actor=actor,
            notes=", ".join(changed),
        )
    return get_author_workspace(connection, actor)


def remove_claim(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Take a publication off the author's own profile.

    Used when a co-author linked the wrong person, or when a merged name
    spelling turns out to include someone else's paper. The publication itself
    is untouched; only this author's attribution ends.
    """

    actor = require_actor(actor)
    claim_id = clean_text(payload.get("claim_id"), field="claim_id", required=True)
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor)
        claim = _fetch_one(
            cursor,
            "SELECT * FROM author_publication_claims WHERE claim_id = %s::uuid AND profile_id = %s FOR UPDATE",
            [claim_id, profile["profile_id"]],
        )
        if claim is None:
            raise APIError("not_found", "That publication is not on your profile.", status=404)
        if claim["status"] == "rejected":
            raise APIError("already_decided", "That publication is already off your profile.", status=409)
        cursor.execute(
            """
            UPDATE author_publication_claims
            SET status = 'rejected', decision_reason = 'Removed by the author.',
                decided_by_id = %s, decided_by_email = %s, decided_by_name = %s,
                decided_at = now(), updated_at = now()
            WHERE claim_id = %s
            """,
            [*_decided_by(actor), claim["claim_id"]],
        )
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="claim",
            subject_id=claim["claim_id"],
            event_type="claim_removed_by_author",
            actor=actor,
            from_status=claim["status"],
            to_status="rejected",
        )
    return get_author_workspace(connection, actor)


def request_claims(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """An approved author claims more publications; each claim waits for an admin."""

    actor = require_actor(actor)
    requested = validate_claim_requests(payload.get("claims"))
    if not requested:
        raise APIError("claims_required", "Choose at least one publication.", status=400)
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor, lock=True)
        pending = _fetch_one(
            cursor,
            "SELECT count(*) AS total FROM author_publication_claims WHERE profile_id = %s AND status = 'pending'",
            [profile["profile_id"]],
        )
        if int((pending or {}).get("total") or 0) + len(requested) > MAX_PENDING_CLAIMS:
            raise APIError(
                "too_many_pending",
                "You have many claims waiting for review. Wait for an administrator before adding more.",
                status=409,
            )
        claims = _resolve_claims(cursor, requested)
        inserted = _insert_claims(cursor, profile["profile_id"], claims)
        added_variants = _add_name_variants(cursor, profile, payload.get("name_variants"))
        if inserted or added_variants:
            _insert_event(
                cursor,
                profile_id=profile["profile_id"],
                subject_type="profile",
                subject_id=profile["profile_id"],
                event_type="claims_requested",
                actor=actor,
                notes=f"{inserted} publication claim(s)"
                + (f"; spellings added: {', '.join(added_variants)}" if added_variants else ""),
            )
    workspace = get_author_workspace(connection, actor)
    workspace["claims_added"] = inserted
    return workspace


def _add_name_variants(cursor: Any, profile: Mapping[str, Any], value: Any) -> list[str]:
    """Record spellings the author merged into their profile while claiming.

    A spelling only takes effect publicly where it is printed on one of the
    author's approved publications (see PROFILE_SPELLINGS_SQL), so declaring
    one cannot attach anybody else's work.
    """

    existing = [profile["display_name"], *list(profile.get("name_variants") or [])]
    added: list[str] = []
    for raw in string_list(value):
        variant = clean_text(raw, field="name_variants", label="Name variant", max_length=120)
        if variant and not any(same_listed_name(variant, known) for known in [*existing, *added]):
            added.append(variant)
    if not added:
        return []
    variants = [*list(profile.get("name_variants") or []), *added]
    if len(variants) > MAX_NAME_VARIANTS:
        raise APIError(
            "too_many_name_variants",
            f"A profile can list at most {MAX_NAME_VARIANTS} spellings.",
            status=400,
            details={"field": "name_variants"},
        )
    cursor.execute(
        "UPDATE author_profiles SET name_variants = %s, updated_at = now() WHERE profile_id = %s",
        [variants, profile["profile_id"]],
    )
    return added


def _count_pending_contributions(cursor: Any, profile_id: Any) -> int:
    row = _fetch_one(
        cursor,
        "SELECT count(*) AS total FROM author_contributions WHERE profile_id = %s AND status = 'pending'",
        [profile_id],
    )
    return int((row or {}).get("total") or 0)


def _ensure_contribution_capacity(cursor: Any, profile_id: Any) -> None:
    if _count_pending_contributions(cursor, profile_id) >= MAX_PENDING_CONTRIBUTIONS:
        raise APIError(
            "too_many_pending",
            f"You have {MAX_PENDING_CONTRIBUTIONS} changes waiting for review. Wait for an administrator before sending more.",
            status=409,
        )


def _approved_claim(cursor: Any, profile_id: Any, publication_key: str) -> dict[str, Any] | None:
    return _fetch_one(
        cursor,
        """
        SELECT * FROM author_publication_claims
        WHERE profile_id = %s AND publication_key = %s AND status = 'approved'
        """,
        [profile_id, publication_key],
    )


def _editable_columns_sql() -> str:
    return select_columns(list(EDITABLE_PUBLICATION_FIELDS))


def get_editable_publication(connection: Any, actor: Actor | None, publication_key: str) -> dict[str, Any]:
    """Current public values of the editable fields, for the author's edit form."""

    actor = require_actor(actor)
    publication_key = clean_text(publication_key, field="publication_key", max_length=500, required=True)
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor)
        claim = _approved_claim(cursor, profile["profile_id"], publication_key)
        if claim is None:
            raise APIError(
                "not_your_publication",
                "You can only edit publications on your approved author profile.",
                status=403,
            )
        current = _fetch_one(
            cursor,
            f"SELECT {_editable_columns_sql()} FROM {PUBLIC_PUBLICATION_SOURCE_SQL} WHERE publication_key = %s",
            [publication_key],
        )
        if current is None:
            raise APIError("not_found", "Publication not found in the public dataset.", status=404)
        pending = _fetch_one(
            cursor,
            """
            SELECT * FROM author_contributions
            WHERE profile_id = %s AND publication_key = %s
              AND contribution_type = 'publication_edit' AND status = 'pending'
            """,
            [profile["profile_id"], publication_key],
        )
    return {
        "publication_key": publication_key,
        "values": normalize_value(current),
        "name_as_listed": claim["name_as_listed"],
        "pending_edit": contribution_payload(pending) if pending else None,
        "fields": EDITABLE_PUBLICATION_FIELDS,
        "publication_types": list(PUBLICATION_TYPES),
    }


def propose_edit(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_actor(actor)
    publication_key = clean_text(payload.get("publication_key"), field="publication_key", max_length=500, required=True)
    note = clean_text(payload.get("note"), field="author_note", label="Note", max_length=1_000)
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor, lock=True)
        if _approved_claim(cursor, profile["profile_id"], publication_key) is None:
            raise APIError(
                "not_your_publication",
                "You can only edit publications on your approved author profile.",
                status=403,
            )
        current = _fetch_one(
            cursor,
            f"SELECT {_editable_columns_sql()} FROM {PUBLIC_PUBLICATION_SOURCE_SQL} WHERE publication_key = %s",
            [publication_key],
        )
        if current is None:
            raise APIError("not_found", "Publication not found in the public dataset.", status=404)
        proposed, base = diff_publication_changes(payload.get("changes") or {}, current)
        existing = _fetch_one(
            cursor,
            """
            SELECT contribution_id FROM author_contributions
            WHERE profile_id = %s AND publication_key = %s
              AND contribution_type = 'publication_edit' AND status = 'pending'
            """,
            [profile["profile_id"], publication_key],
        )
        if existing is not None:
            raise APIError(
                "edit_already_pending",
                "An edit to this publication is already waiting for review. Withdraw it to send a new one.",
                status=409,
                details={"contribution_id": str(existing["contribution_id"])},
            )
        _ensure_contribution_capacity(cursor, profile["profile_id"])
        contribution = _fetch_one(
            cursor,
            """
            INSERT INTO author_contributions (
                profile_id, contribution_type, publication_key, proposed, base_snapshot, author_note
            )
            VALUES (%s, 'publication_edit', %s, %s, %s, %s)
            RETURNING *
            """,
            [profile["profile_id"], publication_key, _jsonb(proposed), _jsonb(base), note],
        )
        assert contribution is not None
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="contribution",
            subject_id=contribution["contribution_id"],
            event_type="edit_proposed",
            actor=actor,
            to_status="pending",
            notes=", ".join(proposed),
        )
    return contribution_payload(contribution)


def find_duplicates(cursor: Any, *, doi: str | None, title: str) -> list[dict[str, Any]]:
    """Existing records with the same DOI or title, public or not, and why any are hidden."""

    key = title_key(title)
    if not doi and len(key) < MIN_TITLE_MATCH_LENGTH:
        return []
    rows = _fetch_all(
        cursor,
        """
        SELECT p.publication_key,
               p.title,
               COALESCE(p.publication_year, EXTRACT(YEAR FROM p.publication_date)::int) AS publication_year,
               p.doi,
               p.retired_at,
               p.ownership_decision,
               p.ownership_confidence,
               p.needs_manual_review,
               r.review_status,
               EXISTS (
                   SELECT 1 FROM public_eligible_publications v
                   WHERE v.publication_key = p.publication_key
               ) AS is_public
        FROM final_publications p
        LEFT JOIN ai_review_records r ON r.publication_key = p.publication_key
        WHERE (%s::text IS NOT NULL AND p.doi = %s::text)
           OR (length(%s::text) >= %s
               AND regexp_replace(lower(coalesce(p.title, '')), '[^a-z0-9]+', '', 'g') = %s::text)
        LIMIT 5
        """,
        [doi, doi, key, MIN_TITLE_MATCH_LENGTH, key],
    )
    return [duplicate_payload(row) for row in rows]


def duplicate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_value(
        {
            "publication_key": row.get("publication_key"),
            "title": row.get("title"),
            "publication_year": row.get("publication_year"),
            "doi": row.get("doi"),
            "is_public": bool(row.get("is_public")),
            "hidden_reason": None if row.get("is_public") else hidden_reason(row),
        }
    )


def hidden_reason(row: Mapping[str, Any]) -> str:
    if row.get("retired_at"):
        return "It was retired from the dataset."
    status = row.get("review_status")
    if status == "human_rejected":
        return "It was reviewed and excluded: judged not AI-related or not Sri Lanka-led."
    if status == "pending_review":
        return "It is waiting for AI relevance review."
    decision = str(row.get("ownership_decision") or "").upper()
    confidence = str(row.get("ownership_confidence") or "").upper()
    if decision != "INCLUDE" or confidence not in {"HIGH", "MEDIUM"}:
        return "Its Sri Lanka-led ownership could not be verified."
    return "It is not currently public."


def _pending_submission_conflict(cursor: Any, *, doi: str | None, title: str) -> dict[str, Any] | None:
    key = title_key(title)
    return _fetch_one(
        cursor,
        """
        SELECT contribution_id, proposed->>'title' AS title
        FROM author_contributions
        WHERE contribution_type = 'new_publication'
          AND status = 'pending'
          AND (
              (%s::text IS NOT NULL AND proposed->>'doi' = %s::text)
              OR (length(%s::text) >= %s
                  AND regexp_replace(lower(coalesce(proposed->>'title', '')), '[^a-z0-9]+', '', 'g') = %s::text)
          )
        LIMIT 1
        """,
        [doi, doi, key, MIN_TITLE_MATCH_LENGTH, key],
    )


def _ensure_not_already_known(cursor: Any, record: Mapping[str, Any]) -> None:
    duplicates = find_duplicates(cursor, doi=record["doi"], title=record["title"])
    if duplicates:
        raise APIError(
            "duplicate_publication",
            "This publication is already in the dataset.",
            status=409,
            details={"matches": duplicates},
        )
    if _pending_submission_conflict(cursor, doi=record["doi"], title=record["title"]) is not None:
        raise APIError(
            "submission_already_pending",
            "This publication has already been submitted and is waiting for review.",
            status=409,
        )


def lookup_publication_doi(
    connection: Any,
    doi: str,
    *,
    lookup: DoiLookup = lookup_doi,
) -> dict[str, Any]:
    """DOI autofill for the new-publication form, plus any existing record."""

    result = lookup(doi)
    with connection.cursor(row_factory=dict_row) as cursor:
        result["duplicates"] = find_duplicates(
            cursor,
            doi=result.get("doi"),
            title=str((result.get("fields") or {}).get("title") or ""),
        )
    return normalize_value(result)


def classifier_input(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": record.get("title"),
        "abstract": record.get("abstract"),
        "keywords": record.get("keywords"),
        "journal": record.get("journal"),
        "type": record.get("type"),
        "authors": "; ".join(author["name"] for author in record.get("authors") or []),
    }


def _link_author_profiles(cursor: Any, record: dict[str, Any], profile: Mapping[str, Any]) -> None:
    """Resolve each author row's linked profile; the submitter's row is always their own."""

    slugs = sorted({author["profile_slug"] for author in record["authors"] if author.get("profile_slug")})
    found = {
        row["slug"]: row
        for row in (
            _fetch_all(
                cursor,
                "SELECT slug, display_name FROM author_profiles WHERE status = 'approved' AND slug = ANY(%s::text[])",
                [slugs],
            )
            if slugs
            else []
        )
    }
    for index, author in enumerate(record["authors"]):
        if author.get("is_submitter"):
            author["profile_slug"] = profile["slug"]
            author["profile_display_name"] = profile["display_name"]
            continue
        slug = author.get("profile_slug")
        if not slug:
            author["profile_display_name"] = None
            continue
        if slug == profile["slug"]:
            raise APIError(
                "author_not_listed",
                "Your own profile is linked to an author who is not marked as you.",
                status=400,
                details={"field": "authors", "index": index},
            )
        if slug not in found:
            raise APIError(
                "profile_not_found",
                f"The verified profile linked to {author['name']} is no longer available.",
                status=400,
                details={"field": "authors", "index": index},
            )
        author["profile_display_name"] = found[slug]["display_name"]


def submit_new_publication(
    connection: Any,
    actor: Actor | None,
    payload: Mapping[str, Any],
    *,
    classifier: Classifier = classify_submission,
    lookup: DoiLookup = lookup_doi,
    categorizer: Classifier = suggest_category,
) -> dict[str, Any]:
    """Queue a publication the pipeline missed, with the AI check and source evidence attached.

    The DOI lookup runs here rather than trusting what the form sent, so the
    ownership evidence an administrator sees came from OpenAlex or Crossref.
    """

    actor = require_actor(actor)
    record = validate_new_publication(payload)
    note = clean_text(payload.get("note"), field="author_note", label="Note", max_length=1_000)

    # Cheap checks first, without row locks: the DOI lookup and the model run
    # below can take seconds and must not hold the profile row while they do.
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor)
        _ensure_contribution_capacity(cursor, profile["profile_id"])
        _ensure_not_already_known(cursor, record)
        _link_author_profiles(cursor, record, profile)

    lookup_source = "manual"
    lookup_evidence: dict[str, Any] = {}
    if record["doi"]:
        try:
            found = lookup(record["doi"])
        except APIError:
            found = None
        if found:
            lookup_source = str(found.get("source") or "manual")
            lookup_evidence = {
                "ownership": found.get("ownership") or {},
                "openalex_id": found.get("openalex_id"),
                "countries": found.get("countries") or "",
                "institutions": found.get("institutions") or "",
                "sri_lankan_institutions": found.get("sri_lankan_institutions") or "",
                "source_title": (found.get("fields") or {}).get("title") or "",
                "source_authors": [author.get("name") for author in (found.get("fields") or {}).get("authors") or []],
                "category": found.get("category") or {},
            }

    classification = classifier(classifier_input(record))
    # The category model is a second opinion for the admin even when the author
    # chose one; it decides only when neither the author nor OpenAlex did.
    classification["category"] = categorizer(
        {"title": record["title"], "abstract": record["abstract"], "keywords": record["keywords"]}
    )

    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_for_actor(cursor, actor, lock=True)
        _ensure_contribution_capacity(cursor, profile["profile_id"])
        _ensure_not_already_known(cursor, record)
        contribution = _fetch_one(
            cursor,
            """
            INSERT INTO author_contributions (
                profile_id, contribution_type, proposed, author_note,
                lookup_source, lookup_evidence, classifier
            )
            VALUES (%s, 'new_publication', %s, %s, %s, %s, %s)
            RETURNING *
            """,
            [
                profile["profile_id"],
                _jsonb(record),
                note,
                lookup_source,
                _jsonb(lookup_evidence),
                _jsonb(classification),
            ],
        )
        assert contribution is not None
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="contribution",
            subject_id=contribution["contribution_id"],
            event_type="publication_submitted",
            actor=actor,
            to_status="pending",
            notes=f"AI check: {classification.get('label')}",
        )
    return contribution_payload(contribution)


def withdraw_contribution(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_actor(actor)
    contribution_id = clean_text(payload.get("contribution_id"), field="contribution_id", required=True)
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _profile_for_actor(cursor, actor)
        if profile is None:
            raise APIError("not_found", "Contribution not found.", status=404)
        contribution = _fetch_one(
            cursor,
            "SELECT * FROM author_contributions WHERE contribution_id = %s::uuid AND profile_id = %s FOR UPDATE",
            [contribution_id, profile["profile_id"]],
        )
        if contribution is None:
            raise APIError("not_found", "Contribution not found.", status=404)
        if contribution["status"] != "pending":
            raise APIError("already_decided", "Only changes still waiting for review can be withdrawn.", status=409)
        updated = _fetch_one(
            cursor,
            """
            UPDATE author_contributions
            SET status = 'withdrawn', record_version = record_version + 1, updated_at = now()
            WHERE contribution_id = %s
            RETURNING *
            """,
            [contribution["contribution_id"]],
        )
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="contribution",
            subject_id=contribution["contribution_id"],
            event_type="contribution_withdrawn",
            actor=actor,
            from_status="pending",
            to_status="withdrawn",
        )
    assert updated is not None
    return contribution_payload(updated)


# ----------------------------------------------------------- public profiles

PROFILE_YEAR_SQL = "COALESCE(v.publication_year, EXTRACT(YEAR FROM v.publication_date)::int)"


def _profile_stats(cursor: Any, profile_ids: list[Any]) -> dict[Any, dict[str, Any]]:
    if not profile_ids:
        return {}
    rows = _fetch_all(
        cursor,
        f"""
        SELECT c.profile_id,
               count(v.publication_key) AS publication_count,
               min({PROFILE_YEAR_SQL}) AS year_min,
               max({PROFILE_YEAR_SQL}) AS year_max,
               coalesce(sum(v.citation_count), 0) AS citation_total
        FROM author_publication_claims c
        JOIN public_eligible_publications v ON v.publication_key = c.publication_key
        WHERE c.status = 'approved' AND c.profile_id = ANY(%s::uuid[])
        GROUP BY c.profile_id
        """,
        [[str(profile_id) for profile_id in profile_ids]],
    )
    return {row["profile_id"]: row for row in rows}


def _public_profile_summary(profile: Mapping[str, Any], stats: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = profile_payload(profile, public=True)
    payload["stats"] = normalize_value(
        {
            "publication_count": int((stats or {}).get("publication_count") or 0),
            "year_min": (stats or {}).get("year_min"),
            "year_max": (stats or {}).get("year_max"),
            "citation_total": int((stats or {}).get("citation_total") or 0),
        }
    )
    return payload


def list_public_profiles(
    connection: Any,
    *,
    name: str | None = None,
    q: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Approved profiles, optionally those whose names match a researcher-page name."""

    limit = min(max(1, int(limit)), 100)
    query = clean_text(q, field="q", max_length=120)
    with connection.cursor(row_factory=dict_row) as cursor:
        if query:
            profiles = _fetch_all(
                cursor,
                """
                SELECT * FROM author_profiles
                WHERE status = 'approved'
                  AND (display_name ILIKE %s OR institution ILIKE %s
                       OR EXISTS (SELECT 1 FROM unnest(name_variants) AS variant WHERE variant ILIKE %s))
                ORDER BY display_name
                LIMIT %s
                """,
                [f"%{query}%", f"%{query}%", f"%{query}%", limit],
            )
        else:
            profiles = _fetch_all(
                cursor,
                "SELECT * FROM author_profiles WHERE status = 'approved' ORDER BY display_name LIMIT 1000",
            )
        claimed: dict[Any, int] = {}
        if name:
            # Profiles that own this exact printed spelling come first: their
            # papers under it are known to be theirs. Profiles with a merely
            # similar name follow as "may be".
            cursor.execute(
                f"""
                SELECT s.profile_id, count(DISTINCT s.publication_key) AS claimed_count
                FROM ({PROFILE_SPELLINGS_SQL}) AS s
                WHERE lower(s.spelling) = lower(%s)
                GROUP BY s.profile_id
                """,
                [name],
            )
            for row in cursor.fetchall():
                claimed[row["profile_id"]] = int(row["claimed_count"])
            profiles = [
                profile
                for profile in profiles
                if profile["profile_id"] in claimed or best_name_match(name, profile_names(profile)) != "none"
            ]
            profiles.sort(key=lambda profile: (profile["profile_id"] not in claimed, -claimed.get(profile["profile_id"], 0)))
        profiles = profiles[:limit]
        stats = _profile_stats(cursor, [profile["profile_id"] for profile in profiles])
    summaries = []
    for profile in profiles:
        summary = _public_profile_summary(profile, stats.get(profile["profile_id"]))
        if name:
            summary["match"] = "claimed" if profile["profile_id"] in claimed else "similar"
            summary["claimed_count"] = claimed.get(profile["profile_id"], 0)
        summaries.append(summary)
    return summaries


def profiles_by_names(connection: Any, names: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Printed name -> the verified profile that has claimed it, for directory listings."""

    wanted = [str(name) for name in names if str(name or "").strip()][:100]
    with connection.cursor(row_factory=dict_row) as cursor:
        claimed = claimed_name_profiles(cursor, wanted)
    return {name: claimed[name.casefold()] for name in wanted if name.casefold() in claimed}


def _approved_profile_by_slug(cursor: Any, slug: str) -> dict[str, Any]:
    profile = _fetch_one(
        cursor,
        "SELECT * FROM author_profiles WHERE slug = %s AND status = 'approved'",
        [slug],
    )
    if profile is None:
        raise APIError("not_found", "Author profile not found.", status=404)
    return profile


def public_profile(connection: Any, slug: str) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_by_slug(cursor, slug)
        stats = _profile_stats(cursor, [profile["profile_id"]])
        listed_names = _fetch_all(
            cursor,
            f"""
            SELECT s.spelling AS name_as_listed, count(DISTINCT s.publication_key) AS publication_count
            FROM ({PROFILE_SPELLINGS_SQL}) AS s
            JOIN public_eligible_publications v ON v.publication_key = s.publication_key
            WHERE s.profile_id = %s
            GROUP BY s.spelling
            ORDER BY count(DISTINCT s.publication_key) DESC, s.spelling
            """,
            [profile["profile_id"]],
        )
        affiliations = _affiliations(cursor, profile["profile_id"])
        papers = _fetch_all(
            cursor,
            f"""
            SELECT c.institution AS author_institution, v.institutions,
                   {PROFILE_YEAR_SQL} AS publication_year
            FROM author_publication_claims c
            JOIN public_eligible_publications v ON v.publication_key = c.publication_key
            WHERE c.profile_id = %s AND c.status = 'approved'
            """,
            [profile["profile_id"]],
        )
    payload = _public_profile_summary(profile, stats.get(profile["profile_id"]))
    payload["listed_names"] = [row["name_as_listed"] for row in listed_names]
    payload["listed_name_counts"] = normalize_value(listed_names)
    payload["affiliations"] = affiliations
    payload["institution_breakdown"] = institution_breakdown(papers, affiliations)
    return payload


def public_profile_publications(
    connection: Any,
    slug: str,
    *,
    page: int,
    page_size: int,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _approved_profile_by_slug(cursor, slug)
        rows = _fetch_all(
            cursor,
            f"""
            SELECT {select_columns(BASE_COLUMNS)}, count(*) OVER () AS total_rows
            FROM {PUBLIC_PUBLICATION_SOURCE_SQL}
            WHERE publication_key IN (
                SELECT publication_key FROM author_publication_claims
                WHERE profile_id = %s AND status = 'approved'
            )
            ORDER BY {PUBLICATION_YEAR_SQL} DESC NULLS LAST, title ASC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            [profile["profile_id"], page_size, (page - 1) * page_size],
        )
    total = int(rows[0]["total_rows"]) if rows else 0
    for row in rows:
        row.pop("total_rows", None)
    return list_response(
        [publication_summary(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        meta=meta,
    )


# ------------------------------------------------------------- admin side


def admin_summary(connection: Any) -> dict[str, int]:
    """Queue sizes for the admin navigation badges."""

    with connection.cursor(row_factory=dict_row) as cursor:
        row = _fetch_one(
            cursor,
            """
            SELECT
                (SELECT count(*) FROM author_profiles WHERE status = 'pending') AS applications,
                (SELECT count(*) FROM author_publication_claims c
                 JOIN author_profiles p ON p.profile_id = c.profile_id
                 WHERE c.status = 'pending' AND p.status = 'approved') AS claims,
                (SELECT count(*) FROM author_contributions WHERE status = 'pending') AS contributions
            """,
        )
    return {key: int(value or 0) for key, value in (row or {}).items()}


def _claim_evidence(
    cursor: Any,
    claims: list[dict[str, Any]],
    profiles: Mapping[Any, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the checks an administrator needs to each claim."""

    keys = sorted({claim["publication_key"] for claim in claims})
    publications = {
        row["publication_key"]: row
        for row in (
            _fetch_all(
                cursor,
                """
                SELECT publication_key, authors, author_orcids, author_affiliations
                FROM final_publications WHERE publication_key = ANY(%s::text[])
                """,
                [keys],
            )
            if keys
            else []
        )
    }
    competing_rows = (
        _fetch_all(
            cursor,
            """
            SELECT c.claim_id, c.profile_id, c.publication_key, c.name_as_listed, c.status,
                   p.display_name, p.slug
            FROM author_publication_claims c
            JOIN author_profiles p ON p.profile_id = c.profile_id
            WHERE c.publication_key = ANY(%s::text[]) AND c.status IN ('pending', 'approved')
            """,
            [keys],
        )
        if keys
        else []
    )
    enriched = []
    for claim in claims:
        profile = profiles.get(claim["profile_id"]) or {}
        publication = publications.get(claim["publication_key"]) or {}
        listed = split_semicolon_value(publication.get("authors"))
        competing = [
            {
                "claim_id": str(row["claim_id"]),
                "display_name": row["display_name"],
                "status": row["status"],
            }
            for row in competing_rows
            if row["publication_key"] == claim["publication_key"]
            and row["profile_id"] != claim["profile_id"]
            and same_listed_name(row["name_as_listed"], claim["name_as_listed"])
        ]
        payload = claim_payload(claim)
        payload["evidence"] = {
            "name_match": best_name_match(claim["name_as_listed"], profile_names(profile)),
            "still_listed": any(same_listed_name(name, claim["name_as_listed"]) for name in listed),
            "orcid_match": orcid_in_publication(profile.get("orcid"), publication.get("author_orcids")),
            "competing_claims": competing,
        }
        enriched.append(payload)
    return enriched


def list_applications(
    connection: Any,
    *,
    status: str | None = "pending",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if status and status not in PROFILE_STATUSES:
        raise APIError("invalid_status", "Unsupported application status.", status=400)
    page = max(1, int(page))
    page_size = min(50, max(1, int(page_size)))
    with connection.cursor(row_factory=dict_row) as cursor:
        profiles = _fetch_all(
            cursor,
            """
            SELECT *, count(*) OVER () AS total_rows
            FROM author_profiles
            WHERE (%s::text IS NULL OR status = %s::text)
            ORDER BY submitted_at ASC
            LIMIT %s OFFSET %s
            """,
            [status, status, page_size, (page - 1) * page_size],
        )
        total = int(profiles[0]["total_rows"]) if profiles else 0
        ids = [str(profile["profile_id"]) for profile in profiles]
        claims = (
            _fetch_all(
                cursor,
                f"{CLAIMS_WITH_PUBLICATION_SQL} WHERE c.profile_id = ANY(%s::uuid[]) ORDER BY c.author_position NULLS LAST, c.created_at",
                [ids],
            )
            if ids
            else []
        )
        by_id = {profile["profile_id"]: profile for profile in profiles}
        enriched_claims = _claim_evidence(cursor, claims, by_id)
        orcid_holders = _fetch_all(
            cursor,
            """
            SELECT profile_id, orcid, display_name FROM author_profiles
            WHERE status = 'approved' AND orcid = ANY(%s::text[])
            """,
            [[profile["orcid"] for profile in profiles if profile.get("orcid")]],
        )
    records = []
    for profile in profiles:
        payload = profile_payload(profile)
        payload["claims"] = [claim for claim in enriched_claims if claim["profile_id"] == str(profile["profile_id"])]
        payload["evidence"] = {
            "email": email_domain_evidence(profile.get("user_email")),
            "orcid_matches": sum(1 for claim in payload["claims"] if claim["evidence"]["orcid_match"]),
            "orcid_held_by": [
                holder["display_name"]
                for holder in orcid_holders
                if holder["orcid"] == profile.get("orcid") and holder["profile_id"] != profile["profile_id"]
            ],
        }
        records.append(payload)
    return {"records": records, "total": total, "page": page, "page_size": page_size}


def _decided_by(actor: Actor) -> list[Any]:
    return [actor.get("id"), actor.get("email"), actor.get("name")]


def _approve_claims(cursor: Any, claims: list[dict[str, Any]], actor: Actor) -> None:
    for claim in claims:
        conflict = _fetch_one(
            cursor,
            """
            SELECT c.claim_id, p.display_name
            FROM author_publication_claims c
            JOIN author_profiles p ON p.profile_id = c.profile_id
            WHERE c.publication_key = %s AND lower(c.name_as_listed) = lower(%s)
              AND c.status = 'approved' AND c.claim_id <> %s
            """,
            [claim["publication_key"], claim["name_as_listed"], claim["claim_id"]],
        )
        if conflict is not None:
            raise APIError(
                "claim_conflict",
                f"{conflict['display_name']} already holds an approved claim on this listed author. Reject one of the two claims.",
                status=409,
                details={"claim_id": str(claim["claim_id"]), "publication_key": claim["publication_key"]},
            )
        cursor.execute(
            """
            UPDATE author_publication_claims
            SET status = 'approved', decided_by_id = %s, decided_by_email = %s,
                decided_by_name = %s, decided_at = now(), decision_reason = '', updated_at = now()
            WHERE claim_id = %s
            """,
            [*_decided_by(actor), claim["claim_id"]],
        )


def _reject_claims(cursor: Any, claims: list[dict[str, Any]], actor: Actor, reason: str) -> None:
    for claim in claims:
        cursor.execute(
            """
            UPDATE author_publication_claims
            SET status = 'rejected', decided_by_id = %s, decided_by_email = %s,
                decided_by_name = %s, decided_at = now(), decision_reason = %s, updated_at = now()
            WHERE claim_id = %s
            """,
            [*_decided_by(actor), reason, claim["claim_id"]],
        )


def parse_claim_decisions(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise APIError("invalid_request", "claim_decisions must map claim ids to approved or rejected.", status=400)
    decisions = {}
    for claim_id, decision in value.items():
        if decision not in {"approved", "rejected"}:
            raise APIError("invalid_decision", "Each claim decision must be approved or rejected.", status=400)
        decisions[str(claim_id)] = decision
    return decisions


def decide_application(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Approve, reject or return an application.

    Idempotent per target status: repeating a decision the profile already has
    returns it unchanged with `already_decided`, so the frontend can safely
    retry the account activation that follows an approval.
    """

    actor = require_actor(actor)
    profile_id = clean_text(payload.get("profile_id"), field="profile_id", required=True)
    decision = str(payload.get("decision") or "")
    if decision not in APPLICATION_DECISIONS:
        raise APIError("invalid_decision", "Choose approve, request changes or reject.", status=400)
    reason = clean_text(payload.get("reason"), field="decision_reason", label="Reason", max_length=1_000)
    if decision != "approve" and not reason:
        raise APIError(
            "reason_required",
            "Tell the applicant why, so they know what to do next.",
            status=400,
            details={"field": "reason"},
        )
    claim_decisions = parse_claim_decisions(payload.get("claim_decisions"))
    target_status = {"approve": "approved", "request_changes": "changes_requested", "reject": "rejected"}[decision]

    with connection.cursor(row_factory=dict_row) as cursor:
        profile = _fetch_one(
            cursor,
            "SELECT * FROM author_profiles WHERE profile_id = %s::uuid FOR UPDATE",
            [profile_id],
        )
        if profile is None:
            raise APIError("not_found", "Application not found.", status=404)
        if profile["status"] == target_status:
            result = profile_payload(profile)
            result["already_decided"] = True
            return result
        if profile["status"] != "pending":
            raise APIError(
                "already_decided",
                f"This application is {profile['status'].replace('_', ' ')}, not waiting for a decision.",
                status=409,
            )
        expected_version = payload.get("record_version")
        if expected_version not in (None, "") and int(expected_version) != int(profile["record_version"]):
            raise APIError(
                "stale_application",
                "The applicant changed this application after the page loaded. Reload and review it again.",
                status=409,
            )

        pending_claims = _fetch_all(
            cursor,
            "SELECT * FROM author_publication_claims WHERE profile_id = %s AND status = 'pending' FOR UPDATE",
            [profile["profile_id"]],
        )
        if decision == "approve":
            if profile.get("orcid"):
                holder = _fetch_one(
                    cursor,
                    """
                    SELECT display_name FROM author_profiles
                    WHERE orcid = %s AND status = 'approved' AND profile_id <> %s
                    """,
                    [profile["orcid"], profile["profile_id"]],
                )
                if holder is not None:
                    raise APIError(
                        "orcid_in_use",
                        f"{holder['display_name']} already has an approved profile with this ORCID iD.",
                        status=409,
                    )
            approved = [claim for claim in pending_claims if claim_decisions.get(str(claim["claim_id"]), "approved") == "approved"]
            rejected = [claim for claim in pending_claims if claim_decisions.get(str(claim["claim_id"])) == "rejected"]
            _approve_claims(cursor, approved, actor)
            _reject_claims(cursor, rejected, actor, reason or "Not confirmed during application review.")
        elif decision == "reject":
            _reject_claims(cursor, pending_claims, actor, reason)

        updated = _fetch_one(
            cursor,
            """
            UPDATE author_profiles
            SET status = %s, decision_reason = %s, decided_by_id = %s, decided_by_email = %s,
                decided_by_name = %s, decided_at = now(), record_version = record_version + 1,
                updated_at = now()
            WHERE profile_id = %s
            RETURNING *
            """,
            [target_status, reason, *_decided_by(actor), profile["profile_id"]],
        )
        _insert_event(
            cursor,
            profile_id=profile["profile_id"],
            subject_type="profile",
            subject_id=profile["profile_id"],
            event_type=f"application_{target_status}",
            actor=actor,
            from_status=profile["status"],
            to_status=target_status,
            notes=reason,
        )
    assert updated is not None
    result = profile_payload(updated)
    result["already_decided"] = False
    return result


def list_claim_requests(connection: Any, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """Claims added by already-approved authors."""

    page = max(1, int(page))
    page_size = min(100, max(1, int(page_size)))
    with connection.cursor(row_factory=dict_row) as cursor:
        claims = _fetch_all(
            cursor,
            f"""
            {CLAIMS_WITH_PUBLICATION_SQL}
            JOIN author_profiles ap ON ap.profile_id = c.profile_id
            WHERE c.status = 'pending' AND ap.status = 'approved'
            ORDER BY c.created_at
            LIMIT %s OFFSET %s
            """,
            [page_size, (page - 1) * page_size],
        )
        profile_ids = sorted({str(claim["profile_id"]) for claim in claims})
        profiles = {
            row["profile_id"]: row
            for row in (
                _fetch_all(cursor, "SELECT * FROM author_profiles WHERE profile_id = ANY(%s::uuid[])", [profile_ids])
                if profile_ids
                else []
            )
        }
        enriched = _claim_evidence(cursor, claims, profiles)
    profiles_by_id = {str(key): row for key, row in profiles.items()}
    for claim in enriched:
        profile = profiles_by_id.get(claim["profile_id"], {})
        claim["profile"] = {
            "display_name": profile.get("display_name"),
            "slug": profile.get("slug"),
            "institution": profile.get("institution"),
            "orcid": profile.get("orcid"),
        }
    return {"records": enriched, "page": page, "page_size": page_size}


def decide_claims(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_actor(actor)
    decisions = parse_claim_decisions(payload.get("claim_decisions"))
    if not decisions:
        raise APIError("claims_required", "Choose at least one claim.", status=400)
    reason = clean_text(payload.get("reason"), field="decision_reason", label="Reason", max_length=1_000)
    if "rejected" in decisions.values() and not reason:
        raise APIError("reason_required", "Give a reason for rejecting a claim.", status=400, details={"field": "reason"})
    with connection.cursor(row_factory=dict_row) as cursor:
        claims = _fetch_all(
            cursor,
            """
            SELECT c.* FROM author_publication_claims c
            JOIN author_profiles p ON p.profile_id = c.profile_id
            WHERE c.claim_id = ANY(%s::uuid[]) AND c.status = 'pending' AND p.status = 'approved'
            FOR UPDATE OF c
            """,
            [list(decisions)],
        )
        if len(claims) != len(decisions):
            raise APIError("already_decided", "Some of these claims were already decided. Reload the queue.", status=409)
        approved = [claim for claim in claims if decisions[str(claim["claim_id"])] == "approved"]
        rejected = [claim for claim in claims if decisions[str(claim["claim_id"])] == "rejected"]
        _approve_claims(cursor, approved, actor)
        _reject_claims(cursor, rejected, actor, reason)
        for claim in claims:
            decision = decisions[str(claim["claim_id"])]
            _insert_event(
                cursor,
                profile_id=claim["profile_id"],
                subject_type="claim",
                subject_id=claim["claim_id"],
                event_type=f"claim_{decision}",
                actor=actor,
                from_status="pending",
                to_status=decision,
                notes=reason if decision == "rejected" else "",
            )
    return {"approved": len(approved), "rejected": len(rejected)}


def list_contributions(
    connection: Any,
    *,
    status: str | None = "pending",
    contribution_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if status and status not in CONTRIBUTION_STATUSES:
        raise APIError("invalid_status", "Unsupported contribution status.", status=400)
    if contribution_type and contribution_type not in CONTRIBUTION_TYPES:
        raise APIError("invalid_type", "Unsupported contribution type.", status=400)
    page = max(1, int(page))
    page_size = min(50, max(1, int(page_size)))
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = _fetch_all(
            cursor,
            """
            SELECT c.*, p.display_name, p.slug, p.institution, p.orcid, p.user_email,
                   p.name_variants, count(*) OVER () AS total_rows
            FROM author_contributions c
            JOIN author_profiles p ON p.profile_id = c.profile_id
            WHERE (%s::text IS NULL OR c.status = %s::text)
              AND (%s::text IS NULL OR c.contribution_type = %s::text)
            ORDER BY c.created_at ASC
            LIMIT %s OFFSET %s
            """,
            [status, status, contribution_type, contribution_type, page_size, (page - 1) * page_size],
        )
        total = int(rows[0]["total_rows"]) if rows else 0
        edit_keys = [row["publication_key"] for row in rows if row["contribution_type"] == "publication_edit" and row["publication_key"]]
        current = _public_rows_by_key(cursor, edit_keys, f"title AS current_title, {_editable_columns_sql()}")
        records = []
        for row in rows:
            payload = contribution_payload(row)
            payload["profile"] = {
                "display_name": row.get("display_name"),
                "slug": row.get("slug"),
                "institution": row.get("institution"),
                "orcid": row.get("orcid"),
                "email": row.get("user_email"),
            }
            if row["contribution_type"] == "publication_edit":
                public_row = current.get(row["publication_key"]) or {}
                current_values = {field: normalize_value(public_row.get(field)) for field in payload["proposed"]}
                payload["current"] = current_values
                payload["publication_title"] = public_row.get("current_title")
                payload["stale_fields"] = [
                    field
                    for field in payload["proposed"]
                    if comparable(current_values.get(field)) != comparable(payload["base_snapshot"].get(field))
                ]
            else:
                proposed = payload["proposed"]
                payload["duplicates"] = (
                    find_duplicates(cursor, doi=proposed.get("doi"), title=str(proposed.get("title") or ""))
                    if row["status"] == "pending"
                    else []
                )
                payload["name_match"] = best_name_match(
                    proposed.get("your_author_name"),
                    [row.get("display_name"), *list(row.get("name_variants") or [])],
                )
            records.append(payload)
    return {"records": records, "total": total, "page": page, "page_size": page_size}


def _apply_correction(cursor: Any, contribution: Mapping[str, Any], actor: Actor) -> None:
    proposed = dict(contribution["proposed"] or {})
    fields = [field for field in EDITABLE_PUBLICATION_FIELDS if field in proposed]
    if not fields:
        raise APIError("no_changes", "This edit has no changes to apply.", status=409)
    quoted = [quote_identifier(field) for field in fields]
    cursor.execute(
        f"""
        INSERT INTO publication_corrections (
            publication_key, {", ".join(quoted)}, last_contribution_id,
            corrected_by_id, corrected_by_email, corrected_by_name, corrected_at
        )
        VALUES (%s, {", ".join(["%s"] * len(fields))}, %s, %s, %s, %s, now())
        ON CONFLICT (publication_key) DO UPDATE SET
            {", ".join(f"{column} = EXCLUDED.{column}" for column in quoted)},
            last_contribution_id = EXCLUDED.last_contribution_id,
            corrected_by_id = EXCLUDED.corrected_by_id,
            corrected_by_email = EXCLUDED.corrected_by_email,
            corrected_by_name = EXCLUDED.corrected_by_name,
            corrected_at = now()
        """,
        [
            contribution["publication_key"],
            *[proposed[field] for field in fields],
            contribution["contribution_id"],
            *_decided_by(actor),
        ],
    )


def resolve_category(
    contribution: Mapping[str, Any],
    override: Mapping[str, Any] | None,
    domains: Mapping[str, str],
) -> dict[str, Any]:
    """The field and subfield a submission files under, and where they came from.

    In order: the administrator's choice when approving, the author's choice,
    OpenAlex's classification of the DOI, then the category model.
    """

    proposed = contribution.get("proposed") or {}
    lookup_category = (contribution.get("lookup_evidence") or {}).get("category") or {}
    model = (contribution.get("classifier") or {}).get("category") or {}
    candidates = [
        ("administrator", (override or {}).get("primary_field"), (override or {}).get("primary_subfield")),
        ("author", proposed.get("primary_field"), proposed.get("primary_subfield")),
        ("openalex", lookup_category.get("primary_field"), lookup_category.get("primary_subfield")),
        ("model", model.get("field"), model.get("subfield")),
    ]
    for source, field, subfield in candidates:
        if field:
            domain = domains.get(str(field))
            if source == "openalex" and lookup_category.get("primary_domain"):
                domain = lookup_category["primary_domain"]
            return {
                "primary_field": str(field),
                "primary_subfield": str(subfield) if subfield else None,
                "primary_domain": domain,
                "source": source,
            }
    return {"primary_field": None, "primary_subfield": None, "primary_domain": None, "source": None}


def submission_record(
    contribution: Mapping[str, Any],
    actor: Actor,
    category: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The final_publications record for an approved author submission.

    Institutions come from each author's row, the institution they were at
    for this publication, so the record counts towards those institutions in
    rankings regardless of where anyone works now.
    """

    proposed = dict(contribution["proposed"] or {})
    evidence = dict(contribution.get("lookup_evidence") or {})
    classifier = dict(contribution.get("classifier") or {})
    lookup_category = dict(evidence.get("category") or {})
    category = dict(category or {})
    authors = list(proposed.get("authors") or [])
    affiliations = list(
        dict.fromkeys(
            ", ".join(part for part in (author.get("affiliation"), author.get("institution")) if part)
            for author in authors
            if author.get("affiliation") or author.get("institution")
        )
    )
    institutions = list(dict.fromkeys(author["institution"] for author in authors if author.get("institution")))
    sri_lankan = [
        author for author in authors if author.get("institution") and (author.get("country_code") or "").upper() == "LK"
    ]
    sri_lankan_institutions = list(dict.fromkeys(author["institution"] for author in sri_lankan))
    countries = list(
        dict.fromkeys((author.get("country_code") or "").upper() for author in authors if author.get("country_code"))
    )
    return {
        "source_dataset": AUTHOR_SUBMISSION_SOURCE,
        "source_record_id": str(contribution["contribution_id"]),
        "openalex_id": evidence.get("openalex_id") or None,
        "doi": proposed.get("doi") or None,
        "url": proposed.get("url") or (f"https://doi.org/{proposed['doi']}" if proposed.get("doi") else None),
        "pdf_url": proposed.get("pdf_url") or None,
        "title": proposed.get("title"),
        "abstract": proposed.get("abstract"),
        "keywords": proposed.get("keywords") or None,
        "publication_date": proposed.get("publication_date") or None,
        "type": proposed.get("type") or None,
        "authors": "; ".join(author["name"] for author in authors),
        "author_count": len(authors),
        "author_affiliations": "; ".join(affiliations) or None,
        "institutions": "; ".join(institutions) or evidence.get("institutions") or None,
        "sri_lankan_institutions": "; ".join(sri_lankan_institutions) or evidence.get("sri_lankan_institutions") or None,
        "sri_lankan_authors": "; ".join(author["name"] for author in sri_lankan) or None,
        "countries": "; ".join(countries) or evidence.get("countries") or None,
        "primary_field": category.get("primary_field"),
        "primary_subfield": category.get("primary_subfield"),
        "primary_domain": category.get("primary_domain"),
        "primary_topic": lookup_category.get("primary_topic") or None,
        "topics": lookup_category.get("topics") or None,
        "concepts": lookup_category.get("concepts") or None,
        "journal": proposed.get("journal") or None,
        "publisher": proposed.get("publisher") or None,
        "volume": proposed.get("volume") or None,
        "issue": proposed.get("issue") or None,
        "first_page": proposed.get("first_page") or None,
        "last_page": proposed.get("last_page") or None,
        "language": proposed.get("language") or None,
        "ownership_decision": "INCLUDE",
        "ownership_class": "admin_verified_author_submission",
        "ownership_confidence": "HIGH",
        "ownership_reason": f"Sri Lanka-led ownership confirmed by {actor.get('email')} when approving an author submission.",
        "ownership_evidence": json.dumps(evidence.get("ownership") or {}, sort_keys=True) if evidence.get("ownership") else None,
        "needs_manual_review": "false",
        "ownership_policy_version": "author-submission-v1",
        "ai_classification_label": classifier.get("label") or "review",
        "ai_classification_confidence": classifier.get("confidence"),
        "ai_classification_model": classifier.get("model"),
        "ai_classification_reason": classifier.get("reason"),
    }


def _load_submission(
    cursor: Any,
    connection: Any,
    contribution: Mapping[str, Any],
    actor: Actor,
    notes: str,
    category: Mapping[str, Any],
) -> str:
    from src.database.loader import build_final_publication_row, load_final_publications

    record = submission_record(contribution, actor, category)
    publication_key = build_final_publication_row(record, 1)["publication_key"]
    load_final_publications([record], connection=connection, ensure_schema=False)
    # publication_year is not a loader column; harvested rows derive it from
    # publication_date, but an author may only know the year.
    cursor.execute(
        "UPDATE final_publications SET publication_year = %s WHERE publication_key = %s",
        [contribution["proposed"].get("publication_year"), publication_key],
    )
    record_human_acceptance(
        connection,
        publication_key=publication_key,
        actor=actor,
        notes=notes,
    )
    return publication_key


def _claim_submission_authors(
    cursor: Any,
    contribution: Mapping[str, Any],
    publication_key: str,
    actor: Actor,
) -> None:
    """Put an approved submission on every verified profile its authors were linked to.

    The submitter's claim is their own. A co-author's claim rests on the
    administrator having just reviewed the author list, and each co-author
    can remove the publication from their profile if the link was wrong.
    """

    proposed = contribution.get("proposed") or {}
    authors = list(proposed.get("authors") or [])
    slugs = sorted({author["profile_slug"] for author in authors if author.get("profile_slug")})
    profiles = {
        row["slug"]: row
        for row in (
            _fetch_all(
                cursor,
                "SELECT profile_id, slug FROM author_profiles WHERE status = 'approved' AND slug = ANY(%s::text[])",
                [slugs],
            )
            if slugs
            else []
        )
    }
    for position, author in enumerate(authors, start=1):
        if author.get("is_submitter") or same_listed_name(author.get("name"), proposed.get("your_author_name")):
            profile_id = contribution["profile_id"]
        elif author.get("profile_slug") in profiles:
            profile_id = profiles[author["profile_slug"]]["profile_id"]
        else:
            continue
        cursor.execute(
            """
            INSERT INTO author_publication_claims (
                profile_id, publication_key, name_as_listed, author_position, institution, status,
                decided_by_id, decided_by_email, decided_by_name, decided_at
            )
            VALUES (%s, %s, %s, %s, %s, 'approved', %s, %s, %s, now())
            ON CONFLICT (profile_id, publication_key) DO NOTHING
            RETURNING claim_id
            """,
            [profile_id, publication_key, author["name"], position, author.get("institution"), *_decided_by(actor)],
        )
        created = cursor.fetchone()
        if created and profile_id != contribution["profile_id"]:
            _insert_event(
                cursor,
                profile_id=profile_id,
                subject_type="claim",
                subject_id=created["claim_id"],
                event_type="claim_added_by_coauthor_submission",
                actor=actor,
                to_status="approved",
                notes=f"Listed as a co-author on a publication added by another author ({contribution['contribution_id']}).",
            )


def decide_contribution(connection: Any, actor: Actor | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Approve or reject one author contribution.

    Approving a new publication needs two explicit confirmations from the
    administrator — that it is AI research and that it is Sri Lanka-led — the
    same two gates every harvested record passes. Overriding a model that did
    not say AI needs a written reason, as it would in the AI review queue.
    """

    actor = require_actor(actor)
    contribution_id = clean_text(payload.get("contribution_id"), field="contribution_id", required=True)
    decision = str(payload.get("decision") or "")
    if decision not in CONTRIBUTION_DECISIONS:
        raise APIError("invalid_decision", "Choose approve or reject.", status=400)
    reason = clean_text(payload.get("reason"), field="decision_reason", label="Reason", max_length=1_000)
    if decision == "reject" and not reason:
        raise APIError("reason_required", "Tell the author why.", status=400, details={"field": "reason"})

    with connection.cursor(row_factory=dict_row) as cursor:
        contribution = _fetch_one(
            cursor,
            "SELECT * FROM author_contributions WHERE contribution_id = %s::uuid FOR UPDATE",
            [contribution_id],
        )
        if contribution is None:
            raise APIError("not_found", "Contribution not found.", status=404)
        if contribution["status"] != "pending":
            raise APIError("already_decided", f"This contribution is already {contribution['status']}.", status=409)
        expected_version = payload.get("record_version")
        if expected_version not in (None, "") and int(expected_version) != int(contribution["record_version"]):
            raise APIError("stale_contribution", "This contribution changed after the page loaded.", status=409)

        publication_key = contribution["publication_key"]
        if decision == "approve" and contribution["contribution_type"] == "publication_edit":
            if _approved_claim(cursor, contribution["profile_id"], publication_key) is None:
                raise APIError(
                    "claim_not_approved",
                    "The author no longer holds an approved claim on this publication.",
                    status=409,
                )
            _apply_correction(cursor, contribution, actor)
        elif decision == "approve":
            if str(payload.get("ai_decision") or "") != "AI":
                raise APIError(
                    "ai_confirmation_required",
                    "Confirm the publication is AI research. If it is not, reject it instead.",
                    status=400,
                )
            if payload.get("ownership_verified") is not True:
                raise APIError(
                    "ownership_confirmation_required",
                    "Confirm the publication is Sri Lanka-led before approving it.",
                    status=400,
                )
            model_label = str((contribution.get("classifier") or {}).get("label") or "")
            if model_label != "AI" and not reason:
                raise APIError(
                    "reason_required",
                    "The AI check did not label this AI. Add a reason for accepting it anyway.",
                    status=400,
                    details={"field": "reason"},
                )
            proposed = contribution["proposed"] or {}
            override = validate_category(payload.get("primary_field"), payload.get("primary_subfield"))
            category = resolve_category(contribution, override, field_domains(connection))
            duplicates = find_duplicates(cursor, doi=proposed.get("doi"), title=str(proposed.get("title") or ""))
            if duplicates:
                raise APIError(
                    "duplicate_publication",
                    "This publication reached the dataset after it was submitted. Reject the submission and ask the author to claim the existing record.",
                    status=409,
                    details={"matches": duplicates},
                )
            publication_key = _load_submission(
                cursor,
                connection,
                contribution,
                actor,
                reason or "Author submission accepted as AI and Sri Lanka-led.",
                category,
            )
            _claim_submission_authors(cursor, contribution, publication_key, actor)

        target_status = "approved" if decision == "approve" else "rejected"
        updated = _fetch_one(
            cursor,
            """
            UPDATE author_contributions
            SET status = %s, publication_key = %s, decision_reason = %s,
                decided_by_id = %s, decided_by_email = %s, decided_by_name = %s,
                decided_at = now(), record_version = record_version + 1, updated_at = now()
            WHERE contribution_id = %s
            RETURNING *
            """,
            [target_status, publication_key, reason, *_decided_by(actor), contribution["contribution_id"]],
        )
        _insert_event(
            cursor,
            profile_id=contribution["profile_id"],
            subject_type="contribution",
            subject_id=contribution["contribution_id"],
            event_type=f"contribution_{target_status}",
            actor=actor,
            from_status="pending",
            to_status=target_status,
            notes=reason,
        )
    assert updated is not None
    return contribution_payload(updated)


def with_connection(operation: Callable[[Any], Any]) -> Any:
    connection = get_connection()
    try:
        result = operation(connection)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
