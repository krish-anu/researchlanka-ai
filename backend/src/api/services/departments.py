"""Department research portfolios over tagged final publications.

The department sidecar (see :mod:`src.api.repositories.departments`) says which
publications belong to a department and through which authors. Everything
else -- years, venues, topics, partners, citations -- is read from the served
publication rows, so a portfolio only ever counts publications the public API
also serves.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any

from src.api.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, SORT_OPTIONS
from src.api.core.errors import APIError
from src.api.core.query import first, parse_filters, parse_positive_int
from src.api.core.serializers import list_response, normalize_row, normalize_value, publication_summary
from src.api.repositories.departments import DepartmentStore, get_department_store, researcher_identity


MATCH_TYPES = ("explicit", "inferred")
RESEARCHER_SORTS = {"publications_desc", "citations_desc", "recent_desc", "name_asc"}
HOME_COUNTRY_CODE = "LK"
EXPORT_FIELDS = [
    "publication_key",
    "title",
    "publication_year",
    "doi",
    "type",
    "journal",
    "publisher",
    "authors",
    "citation_count",
    "is_oa",
    "primary_field",
    "primary_subfield",
    "department_match",
    "department_authors",
    "department_evidence",
]


class DepartmentService:
    """Read-only department portfolio operations."""

    def __init__(self, store: DepartmentStore | None = None) -> None:
        self.store = store

    def _require_store(self) -> DepartmentStore:
        if self.store is None:
            try:
                self.store = get_department_store()
            except FileNotFoundError as exc:
                raise APIError(
                    "service_unavailable",
                    "Department artifacts are not available.",
                    details={"reason": str(exc)},
                    status=503,
                ) from exc
        return self.store

    def _department(self, department_key: str) -> dict[str, Any]:
        entry = self._require_store().resolve(department_key)
        if entry is None:
            raise APIError("not_found", "Department not found.", status=404)
        return entry

    def list_departments(self, *, meta: dict[str, Any]) -> dict[str, Any]:
        rows = self._require_store().list_departments()
        return list_response(rows, page=1, page_size=max(len(rows), 1), total=len(rows), meta=meta)

    def department_profile(
        self,
        department_key: str,
        query: dict[str, list[str]],
        *,
        repository: Any,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        store = self._require_store()
        entry = self._department(department_key)
        tagged = self._tagged_rows(entry, repository, filters=publication_filters(query, search=False))
        records = [(normalize_row(row), assignment) for row, assignment in tagged]
        researchers = aggregate_researchers(records)
        institution_name = str(entry.get("institution_name") or "").casefold()

        citations = [row.get("citation_count") for row, _ in records if row.get("citation_count") is not None]
        years = [int(row["publication_year"]) for row, _ in records if row.get("publication_year")]
        oa_known = [row.get("is_oa") for row, _ in records if row.get("is_oa") is not None]
        countries = [set(row.get("countries") or []) for row, _ in records]
        partner_institutions = Counter(
            institution
            for row, _ in records
            for institution in set(row.get("institutions") or [])
            if institution_name and institution_name not in str(institution).casefold()
        )
        top_cited = sorted(
            (pair for pair in tagged if pair[0].get("citation_count") is not None),
            key=lambda pair: int(pair[0].get("citation_count") or 0),
            reverse=True,
        )[:5]

        data = {
            **store.describe(entry),
            "publication_count": len(records),
            "explicit_count": sum(1 for _, assignment in records if assignment["match"] == "explicit"),
            "inferred_count": sum(1 for _, assignment in records if assignment["match"] == "inferred"),
            "researcher_count": len(researchers),
            "citation_total": sum(int(value) for value in citations) if citations else None,
            "h_index": h_index([int(value) for value in citations]) if citations else None,
            "open_access_share": ratio(sum(1 for value in oa_known if value), len(oa_known)),
            "international_share": ratio(
                sum(1 for codes in countries if codes - {HOME_COUNTRY_CODE}),
                sum(1 for codes in countries if codes),
            ),
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "yearly": yearly_counts(records),
            "research_areas": ranked(Counter(row.get("primary_topic") for row, _ in records), 12),
            "subfields": ranked(Counter(row.get("primary_subfield") for row, _ in records), 8),
            "venues": ranked(Counter(row.get("journal") for row, _ in records), 10),
            "partner_institutions": ranked(partner_institutions, 15),
            "partner_countries": ranked(
                Counter(code for codes in countries for code in codes if code != HOME_COUNTRY_CODE),
                10,
            ),
            "top_researchers": researchers[:10],
            "top_cited": [department_summary(row, assignment) for row, assignment in top_cited],
            "method": {
                "generated_at": store.generated_at,
                "rules": entry.get("rules", {}),
                "coverage": entry.get("counts", {}),
            },
        }
        return {"data": normalize_value(data), "meta": meta}

    def department_publications(
        self,
        department_key: str,
        query: dict[str, list[str]],
        *,
        repository: Any,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        store = self._require_store()
        entry = self._department(department_key)
        filters = publication_filters(query, search=True)
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        sort = first(query, "sort") or ("relevance" if filters.get("q") else "year_desc")
        if sort not in SORT_OPTIONS:
            raise APIError("invalid_sort", f"Unsupported sort: {sort}.", details={"field": "sort"})

        keys = store.candidate_keys(
            entry["department_id"],
            match=parse_match(query),
            researcher=first(query, "researcher"),
        )
        if not keys:
            return list_response([], page=page, page_size=page_size, total=0, meta=meta)
        result = repository.list_publications(
            {**filters, "publication_keys": keys},
            page=page,
            page_size=page_size,
            sort=sort,
            include_facets=False,
        )
        rows = []
        for row in result.get("records", []):
            assignment = store.assignment_for(entry["department_id"], str(row.get("publication_key")))
            if assignment is not None:
                rows.append(department_summary(row, assignment))
        return list_response(
            rows,
            page=page,
            page_size=page_size,
            total=int(result.get("total", len(rows))),
            meta=meta,
        )

    def department_researchers(
        self,
        department_key: str,
        query: dict[str, list[str]],
        *,
        repository: Any,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        entry = self._department(department_key)
        tagged = self._tagged_rows(entry, repository, filters=publication_filters(query, search=False))
        researchers = aggregate_researchers([(normalize_row(row), assignment) for row, assignment in tagged])

        name_filter = (first(query, "q") or "").strip().casefold()
        if name_filter:
            researchers = [row for row in researchers if name_filter in row["label"].casefold()]
        sort = first(query, "sort") or "publications_desc"
        if sort not in RESEARCHER_SORTS:
            raise APIError(
                "invalid_sort",
                f"Unsupported sort: {sort}.",
                details={"field": "sort", "allowed": sorted(RESEARCHER_SORTS)},
            )
        if sort == "citations_desc":
            researchers.sort(key=lambda row: (-(row["citation_total"] or 0), -row["publication_count"]))
        elif sort == "recent_desc":
            researchers.sort(key=lambda row: (-(row["last_year"] or 0), -row["publication_count"]))
        elif sort == "name_asc":
            researchers.sort(key=lambda row: row["label"].casefold())

        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        start = (page - 1) * page_size
        return list_response(
            researchers[start : start + page_size],
            page=page,
            page_size=page_size,
            total=len(researchers),
            meta=meta,
        )

    def export_publications(
        self,
        department_key: str,
        query: dict[str, list[str]],
        *,
        repository: Any,
    ) -> tuple[bytes, str]:
        entry = self._department(department_key)
        tagged = self._tagged_rows(
            entry,
            repository,
            filters=publication_filters(query, search=True),
            match=parse_match(query),
            researcher=first(query, "researcher"),
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for row, assignment in tagged:
            summary = department_summary(row, assignment)
            department = summary.pop("department")
            writer.writerow(
                {
                    **{
                        key: "; ".join(str(item) for item in value) if isinstance(value, list) else value
                        for key, value in summary.items()
                        if key in EXPORT_FIELDS
                    },
                    "department_match": department["match"],
                    "department_authors": "; ".join(author["name"] for author in department["authors"]),
                    "department_evidence": department["evidence"],
                }
            )
        return buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8"

    def _tagged_rows(
        self,
        entry: dict[str, Any],
        repository: Any,
        *,
        filters: dict[str, Any],
        match: str | None = None,
        researcher: str | None = None,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Every served row of the department, newest first, with its assignment."""
        store = self._require_store()
        keys = store.candidate_keys(entry["department_id"], match=match, researcher=researcher)
        if not keys:
            return []
        result = repository.list_publications(
            {**filters, "publication_keys": keys},
            page=1,
            page_size=len(keys),
            sort="year_desc",
            include_facets=False,
        )
        tagged: list[tuple[dict[str, Any], dict[str, Any]]] = []
        seen: set[str] = set()
        for row in result.get("records", []):
            assignment = store.assignment_for(entry["department_id"], str(row.get("publication_key")))
            if assignment is None or assignment["publication_key"] in seen:
                continue
            seen.add(assignment["publication_key"])
            tagged.append((row, assignment))
        return tagged


def publication_filters(query: dict[str, list[str]], *, search: bool) -> dict[str, Any]:
    allowed = {"year_min", "year_max", "q"} if search else {"year_min", "year_max"}
    return parse_filters({key: values for key, values in query.items() if key in allowed})


def parse_match(query: dict[str, list[str]]) -> str | None:
    match = first(query, "match")
    if match in (None, ""):
        return None
    if match not in MATCH_TYPES:
        raise APIError(
            "invalid_filter",
            "match must be explicit or inferred.",
            details={"field": "match", "allowed": list(MATCH_TYPES)},
        )
    return match


def department_summary(row: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        **publication_summary(row),
        "department": {
            "match": assignment["match"],
            "evidence": assignment["evidence"],
            "authors": [
                {"name": author["name"], "author_id": author["author_id"], "match": author["match"]}
                for author in assignment["authors"]
            ],
        },
    }


def aggregate_researchers(
    records: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    """One row per department author across normalised publication rows.

    Authors are grouped by name rather than OpenAlex id, which splits some
    people across several ids.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row, assignment in records:
        year = row.get("publication_year")
        citations = row.get("citation_count")
        seen: set[str] = set()
        for author in assignment["authors"]:
            identity = researcher_identity(author["name"])
            if not identity or identity in seen:
                continue
            seen.add(identity)
            entry = grouped.setdefault(
                identity,
                {
                    "names": Counter(),
                    "author_ids": set(),
                    "publication_count": 0,
                    "explicit_count": 0,
                    "inferred_count": 0,
                    "citation_total": None,
                    "years": [],
                    "areas": Counter(),
                    "department_works": 0,
                },
            )
            entry["names"][author["name"]] += 1
            if author["author_id"]:
                entry["author_ids"].add(author["author_id"])
            entry["publication_count"] += 1
            entry["explicit_count" if author["match"] == "explicit" else "inferred_count"] += 1
            if citations is not None:
                entry["citation_total"] = (entry["citation_total"] or 0) + int(citations)
            if year:
                entry["years"].append(int(year))
            if row.get("primary_topic"):
                entry["areas"][row["primary_topic"]] += 1
            entry["department_works"] = max(entry["department_works"], int(author.get("department_works") or 0))

    researchers = []
    for entry in grouped.values():
        name = entry["names"].most_common(1)[0][0]
        researchers.append(
            {
                "key": name,
                "label": name,
                "author_ids": sorted(entry["author_ids"]),
                "publication_count": entry["publication_count"],
                "explicit_count": entry["explicit_count"],
                "inferred_count": entry["inferred_count"],
                "citation_total": entry["citation_total"],
                "first_year": min(entry["years"]) if entry["years"] else None,
                "last_year": max(entry["years"]) if entry["years"] else None,
                "top_areas": [area for area, _ in entry["areas"].most_common(3)],
                "department_works": entry["department_works"],
            }
        )
    researchers.sort(
        key=lambda row: (-row["publication_count"], -(row["citation_total"] or 0), row["label"].casefold())
    )
    return researchers


def yearly_counts(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, Any]] = {}
    for row, assignment in records:
        if not row.get("publication_year"):
            continue
        year = int(row["publication_year"])
        bucket = buckets.setdefault(
            year,
            {"year": year, "publication_count": 0, "explicit_count": 0, "inferred_count": 0},
        )
        bucket["publication_count"] += 1
        bucket[f"{assignment['match']}_count"] += 1
    return [buckets[year] for year in sorted(buckets)]


def ranked(counter: Counter[Any], limit: int) -> list[dict[str, Any]]:
    return [
        {"label": label, "publication_count": count}
        for label, count in counter.most_common()
        if label not in (None, "")
    ][:limit]


def h_index(citations: list[int]) -> int:
    ordered = sorted(citations, reverse=True)
    return sum(1 for rank, value in enumerate(ordered, start=1) if value >= rank)


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
