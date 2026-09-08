"""Field-aware analytics that degrade gracefully when fields are missing."""

from __future__ import annotations

from collections import Counter
from typing import Any

from research_analytics.networks import (
    build_author_collaboration_network,
    build_country_collaboration_network,
    build_funder_collaboration_network,
)


def run_field_aware_analytics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Run available analytics and explain skipped analytics."""

    summary: dict[str, Any] = {
        "record_count": len(records),
        "skipped": [],
        "data_quality": data_quality_summary(records),
    }

    if _field_available(records, "publication_year"):
        summary["publications_by_year"] = dict(
            sorted(_counter(records, "publication_year").items())
        )
    else:
        summary["skipped"].append(
            "Trend analysis could not be generated because publication_year is missing."
        )

    if _field_available(records, "institutions"):
        summary["top_institutions"] = dict(_counter(records, "institutions").most_common(20))
    else:
        summary["skipped"].append(
            "Institution collaboration analysis could not be generated because institution metadata is missing."
        )

    if _field_available(records, "authors"):
        summary["top_authors"] = dict(_counter(records, "authors").most_common(20))
        author_network = build_author_collaboration_network(records)
        summary["author_collaboration_network"] = {
            "node_count": len(author_network["nodes"]),
            "edge_count": len(author_network["edges"]),
            "top_edges": author_network["edges"][:20],
        }
    else:
        summary["skipped"].append(
            "Author analysis could not be generated because author metadata is missing."
        )

    if _field_available(records, "citation_count"):
        citations = [_to_int(record.get("citation_count")) for record in records]
        citations = [value for value in citations if value is not None]
        summary["citation_total"] = sum(citations)
        summary["average_citations"] = round(sum(citations) / len(citations), 2) if citations else 0
        summary["highly_cited_publications"] = sorted(citations, reverse=True)[:10]
    else:
        summary["skipped"].append(
            "Citation analytics could not be generated because citation_count is missing."
        )

    if _field_available(records, "source_name"):
        summary["records_by_source"] = dict(_counter(records, "source_name").most_common())

    if _field_available(records, "publication_type"):
        summary["publications_by_type"] = dict(_counter(records, "publication_type").most_common())

    if _field_available(records, "national_institutions"):
        summary["publications_by_national_institution"] = dict(
            _counter(records, "national_institutions").most_common(50)
        )

    if _field_available(records, "collaboration_type"):
        summary["collaboration_types"] = dict(_counter(records, "collaboration_type").most_common())

    if _field_available(records, "countries"):
        country_network = build_country_collaboration_network(records)
        summary["country_collaboration_network"] = {
            "node_count": len(country_network["nodes"]),
            "edge_count": len(country_network["edges"]),
            "top_edges": country_network["edges"][:20],
        }

    if _field_available(records, "funder_name"):
        funder_network = build_funder_collaboration_network(records)
        summary["funder_collaboration_network"] = {
            "node_count": len(funder_network["nodes"]),
            "edge_count": len(funder_network["edges"]),
            "top_edges": funder_network["edges"][:20],
        }

    if _field_available(records, "categories"):
        summary["publications_by_category"] = dict(_counter(records, "categories").most_common(50))

    if _field_available(records, "keywords"):
        summary["top_keywords"] = dict(_counter(records, "keywords").most_common(50))

    return summary


def data_quality_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """National coverage and data-quality indicators."""

    total = len(records)
    return {
        "total_records": total,
        "missing_doi_percentage": _missing_percentage(records, "doi"),
        "missing_abstract_percentage": _missing_percentage(records, "abstract"),
        "missing_affiliation_percentage": _missing_percentage(records, "institutions"),
        "missing_publication_year_percentage": _missing_percentage(records, "publication_year"),
        "unresolved_institution_count": sum(
            len(record.get("unresolved_institutions") or []) for record in records
        ),
        "unresolved_author_count": 0,
        "nationally_associated_records": sum(
            1 for record in records if record.get("national_association")
        ),
    }


def _counter(records: list[dict[str, Any]], field: str) -> Counter:
    counter: Counter[str] = Counter()
    for record in records:
        value = record.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, list):
            for item in value:
                if item:
                    counter[str(item)] += 1
        else:
            counter[str(value)] += 1
    return counter


def _field_available(records: list[dict[str, Any]], field: str) -> bool:
    for record in records:
        value = record.get(field)
        if isinstance(value, list):
            if value:
                return True
            continue
        if value not in (None, ""):
            return True
    return False


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def _missing_percentage(records: list[dict[str, Any]], field: str) -> float:
    if not records:
        return 0.0
    missing = sum(1 for record in records if not _value_available(record.get(field)))
    return round(missing / len(records) * 100, 2)


def _value_available(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    return value not in (None, "")
