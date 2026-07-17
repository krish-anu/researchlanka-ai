from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


OPENALEX_BASE_URL = "https://api.openalex.org"
SRI_LANKA_COUNTRY_CODE = "LK"
LK_AUTHORSHIP_FILTER = "authorships.institutions.country_code:LK"

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
    "countries",
    "source_name",
    "publisher",
    "is_oa",
    "landing_page_url",
    "pdf_url",
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


def create_session() -> requests.Session:
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
    session.mount("http://", adapter)
    return session


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_join(values: list[Any], separator: str = "; ") -> str:
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
    return [
        authorship
        for authorship in as_list(work.get("authorships"))
        if isinstance(authorship, dict)
    ]


def country_codes_from_authorship(authorship: dict[str, Any]) -> set[str]:
    codes = {
        str(country).upper()
        for country in as_list(authorship.get("countries"))
        if country
    }
    for institution in as_list(authorship.get("institutions")):
        if isinstance(institution, dict) and institution.get("country_code"):
            codes.add(str(institution["country_code"]).upper())
    return codes


def is_sri_lankan_authorship(authorship: dict[str, Any]) -> bool:
    return SRI_LANKA_COUNTRY_CODE in country_codes_from_authorship(authorship)


def has_sri_lankan_author(work: dict[str, Any]) -> bool:
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
    author = authorship.get("author")
    if isinstance(author, dict) and author.get("display_name"):
        return str(author["display_name"])
    if authorship.get("raw_author_name"):
        return str(authorship["raw_author_name"])
    return None


def author_names(work: dict[str, Any], *, sri_lankan_only: bool = False) -> str:
    names: list[str] = []
    for authorship in authorships(work):
        if sri_lankan_only and not is_sri_lankan_authorship(authorship):
            continue
        names.append(author_name(authorship))
    return unique_join(names)


def institution_names(work: dict[str, Any], *, sri_lankan_only: bool = False) -> str:
    names: list[str] = []
    for authorship in authorships(work):
        for institution in as_list(authorship.get("institutions")):
            if not isinstance(institution, dict):
                continue
            country_code = str(institution.get("country_code", "")).upper()
            if sri_lankan_only and country_code != SRI_LANKA_COUNTRY_CODE:
                continue
            names.append(institution.get("display_name"))
    return unique_join(names)


def country_codes(work: dict[str, Any]) -> str:
    codes: list[str] = []
    for authorship in authorships(work):
        codes.extend(sorted(country_codes_from_authorship(authorship)))
    return unique_join(codes)


def display_names(values: Any) -> str:
    names: list[str] = []
    for value in as_list(values):
        if isinstance(value, dict):
            names.append(value.get("display_name"))
    return unique_join(names)


def get_nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def work_to_row(work: dict[str, Any]) -> dict[str, Any]:
    source = get_nested(work, "primary_location", "source") or {}
    primary_location = work.get("primary_location") or {}
    open_access = work.get("open_access") or {}
    biblio = work.get("biblio") or {}
    primary_topic = work.get("primary_topic")
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
        "openalex_id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title") or work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "author_count": len(authorships(work)),
        "authors": author_names(work),
        "sri_lankan_authors": author_names(work, sri_lankan_only=True),
        "institutions": institution_names(work),
        "sri_lankan_institutions": institution_names(work, sri_lankan_only=True),
        "countries": country_codes(work),
        "source_name": source.get("display_name"),
        "publisher": source.get("host_organization_name"),
        "is_oa": open_access.get("is_oa"),
        "landing_page_url": primary_location.get("landing_page_url"),
        "pdf_url": primary_location.get("pdf_url"),
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


def build_filters(
    filters: list[str] | None = None,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[str]:
    built_filters = list(filters or [LK_AUTHORSHIP_FILTER])

    if from_year is not None or to_year is not None:
        start = from_year if from_year is not None else "*"
        end = to_year if to_year is not None else "*"
        built_filters.append(f"publication_year:{start}-{end}")

    return built_filters


@dataclass
class OpenAlexWorkPage:
    """A fetched OpenAlex page after local Sri Lankan-affiliation filtering."""

    cursor: str
    next_cursor: str | None
    filters: list[str]
    works: list[dict[str, Any]]
    skipped_count: int = 0


@dataclass
class OpenAlexCollector:
    """Collect OpenAlex works with Sri Lankan affiliation metadata."""

    email: str | None = None
    api_key: str | None = None
    timeout: int | tuple[int, int] = 60
    base_url: str = OPENALEX_BASE_URL
    session: requests.Session = field(default_factory=create_session)

    def fetch_works(
        self,
        *,
        filters: list[str],
        cursor: str,
        per_page: int,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "filter": ",".join(filters),
            "cursor": cursor,
            "per-page": per_page,
        }
        if self.email:
            params["mailto"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        response = self.session.get(
            f"{self.base_url}/works",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def iter_sri_lankan_work_pages(
        self,
        *,
        filters: list[str] | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        per_page: int = 200,
        start_cursor: str = "*",
    ) -> Iterator[OpenAlexWorkPage]:
        built_filters = build_filters(filters, from_year=from_year, to_year=to_year)
        cursor = start_cursor

        while cursor:
            response = self.fetch_works(
                filters=built_filters,
                cursor=cursor,
                per_page=per_page,
            )
            results = as_list(response.get("results"))
            if not results:
                break

            works: list[dict[str, Any]] = []
            skipped_count = 0
            for work in results:
                if not isinstance(work, dict) or not has_sri_lankan_author(work):
                    skipped_count += 1
                    continue
                works.append(work)

            next_cursor = response.get("meta", {}).get("next_cursor")
            yield OpenAlexWorkPage(
                cursor=cursor,
                next_cursor=next_cursor,
                filters=built_filters,
                works=works,
                skipped_count=skipped_count,
            )

            cursor = next_cursor

    def iter_sri_lankan_works(
        self,
        *,
        filters: list[str] | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        per_page: int = 200,
        max_records: int | None = None,
        start_cursor: str = "*",
        records_saved: int = 0,
    ) -> Iterator[dict[str, Any]]:
        saved = records_saved

        for page in self.iter_sri_lankan_work_pages(
            filters=filters,
            from_year=from_year,
            to_year=to_year,
            per_page=per_page,
            start_cursor=start_cursor,
        ):
            for work in page.works:
                if max_records is not None and saved >= max_records:
                    return
                saved += 1
                yield work
