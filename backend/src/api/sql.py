"""SQL fragments and helpers for publication API queries."""

from __future__ import annotations

from typing import Any

TEXT_FILTER_COLUMNS = {
    "type": "type",
    "journal": "journal",
    "field": "primary_field",
    "subfield": "primary_subfield",
}

MULTIVALUE_FILTER_COLUMNS = {
    "institution": ("institutions", "sri_lankan_institutions"),
    "country": ("countries",),
    "topic": ("topics", "concepts", "primary_topic"),
    "source_dataset": ("source_dataset",),
}

SORT_SQL = {
    "relevance": "publication_year DESC NULLS LAST, title ASC NULLS LAST",
    "year_desc": "publication_year DESC NULLS LAST, title ASC NULLS LAST",
    "year_asc": "publication_year ASC NULLS LAST, title ASC NULLS LAST",
    "citations_desc": "citation_count DESC NULLS LAST, publication_year DESC NULLS LAST",
    "title_asc": "title ASC NULLS LAST, publication_year DESC NULLS LAST",
}

BASE_COLUMNS = [
    "publication_key",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "openalex_id",
    "doi",
    "url",
    "pdf_url",
    "title",
    "abstract",
    "keywords",
    "publication_year",
    "publication_date",
    "type",
    "authors",
    "author_count",
    "author_affiliations",
    "author_orcids",
    "sri_lankan_authors",
    "contributors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "publisher",
    "journal",
    "source_type",
    "issn",
    "issn_l",
    "volume",
    "issue",
    "first_page",
    "last_page",
    "article_number",
    "language",
    "license",
    "license_url",
    "oa_status",
    "is_oa",
    "citation_count",
    "reference_count",
    "concepts",
    "topics",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "source_set_specs",
    "raw_identifiers",
    "citation_count_difference_oa_minus_crossref",
    "citation_count_divergence_flag",
    "reference_count_difference_oa_minus_crossref",
    "reference_count_divergence_flag",
    "raw_record",
    "loaded_at",
    "updated_at",
]


def build_where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("q"):
        clauses.append(
            "to_tsvector('english', concat_ws(' ', title, abstract, authors, keywords, journal, publisher, doi, openalex_id)) "
            "@@ plainto_tsquery('english', %s)"
        )
        params.append(filters["q"])
    if filters.get("year_min") is not None:
        clauses.append("publication_year >= %s")
        params.append(filters["year_min"])
    if filters.get("year_max") is not None:
        clauses.append("publication_year <= %s")
        params.append(filters["year_max"])
    for key, column in TEXT_FILTER_COLUMNS.items():
        values = filters.get(key)
        if values:
            clauses.append(f"{quote_identifier(column)} = ANY(%s)")
            params.append(values)
    for key, columns in MULTIVALUE_FILTER_COLUMNS.items():
        values = filters.get(key)
        if values:
            per_value = []
            for value in values:
                per_column = []
                for column in columns:
                    per_column.append(f"{quote_identifier(column)} ILIKE %s")
                    params.append(f"%{value}%")
                per_value.append("(" + " OR ".join(per_column) + ")")
            clauses.append("(" + " OR ".join(per_value) + ")")
    if filters.get("is_oa") is not None:
        clauses.append("is_oa IS %s" % ("TRUE" if filters["is_oa"] else "FALSE"))
    if filters.get("has_doi") is not None:
        clauses.append("doi IS %s NULL" % ("NOT" if filters["has_doi"] else ""))
    if filters.get("has_abstract") is not None:
        clauses.append("abstract IS %s NULL" % ("NOT" if filters["has_abstract"] else ""))
    quality_values = filters.get("quality_flag")
    if quality_values:
        flag_clauses = []
        for flag in quality_values:
            if flag == "citation_count_divergence":
                flag_clauses.append("citation_count_divergence_flag IS TRUE")
            elif flag == "reference_count_divergence":
                flag_clauses.append("reference_count_divergence_flag IS TRUE")
            elif flag == "missing_doi":
                flag_clauses.append("doi IS NULL")
            elif flag == "missing_abstract":
                flag_clauses.append("abstract IS NULL")
        if flag_clauses:
            clauses.append("(" + " OR ".join(flag_clauses) + ")")
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def select_columns(columns: list[str]) -> str:
    return ", ".join(quote_identifier(column) for column in columns)


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
