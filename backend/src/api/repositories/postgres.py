"""PostgreSQL repository for the read-only ResearchLanka API."""

from __future__ import annotations

import os
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from src.api.repositories.aggregates import aggregate_profile, normalized_key, percentage, ratio
from src.api.core.serializers import quality_flags, split_semicolon_value
from src.api.repositories.sql import (
    BASE_COLUMNS,
    PUBLICATION_SEARCH_VECTOR_SQL,
    SORT_SQL,
    build_where,
    quote_identifier,
    select_columns,
)
from src.database.connection import get_connection
from src.database.final_schema import FINAL_PUBLICATION_TABLE
from src.modeling.embeddings import (
    EMBEDDING_MODEL_PATH_ENV,
    EMBEDDINGS_PATH_ENV,
    SEMANTIC_RANK_FIELD,
    SEMANTIC_SCORE_FIELD,
    SIMILARITY_RANK_FIELD,
    SIMILARITY_SCORE_FIELD,
    SemanticSearchIndex,
    default_semantic_embeddings_path,
    default_semantic_model_path,
    load_semantic_search_index,
)


SIMILARITY_RESULT_FIELDS = (
    SEMANTIC_SCORE_FIELD,
    SEMANTIC_RANK_FIELD,
    SIMILARITY_SCORE_FIELD,
    SIMILARITY_RANK_FIELD,
)
MAX_SEMANTIC_CANDIDATES = 500


def configured_semantic_path(
    explicit_path: Path | None,
    *,
    env_name: str,
    default_path: Path,
) -> Path:
    if explicit_path is not None:
        return explicit_path
    configured = os.environ.get(env_name)
    if configured:
        return Path(configured)
    return default_path


class PostgresPublicationRepository:
    """Query publication API data from PostgreSQL."""

    def __init__(
        self,
        connection_factory: Callable[[str | None], Any] = get_connection,
        *,
        semantic_index: SemanticSearchIndex | None = None,
        semantic_embeddings_path: Path | None = None,
        semantic_model_path: Path | None = None,
    ) -> None:
        self.connection_factory = connection_factory
        self._semantic_index = semantic_index
        self.semantic_embeddings_path = configured_semantic_path(
            semantic_embeddings_path,
            env_name=EMBEDDINGS_PATH_ENV,
            default_path=default_semantic_embeddings_path(),
        )
        self.semantic_model_path = configured_semantic_path(
            semantic_model_path,
            env_name=EMBEDDING_MODEL_PATH_ENV,
            default_path=default_semantic_model_path(self.semantic_embeddings_path),
        )

    def health(self) -> bool:
        with closing(self.connection_factory(None)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True

    def metadata(self) -> dict[str, Any]:
        row = self._fetch_one(
            f"""
            SELECT
                count(*) AS publication_count,
                min(publication_year) AS min_publication_year,
                max(publication_year) AS max_publication_year,
                max(loaded_at) AS max_loaded_at,
                max(updated_at) AS max_updated_at
            FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
            """,
            [],
        )
        return row or {}

    def list_publications(
        self,
        filters: dict[str, Any],
        *,
        page: int,
        page_size: int,
        sort: str,
        include_facets: bool,
    ) -> dict[str, Any]:
        where_sql, params = build_where(filters)
        total_row = self._fetch_one(
            f"SELECT count(*) AS total FROM {quote_identifier(FINAL_PUBLICATION_TABLE)} {where_sql}",
            params,
        )
        total = int((total_row or {}).get("total") or 0)
        order_sql = SORT_SQL.get(sort, SORT_SQL["year_desc"])
        if sort == "relevance" and filters.get("q"):
            order_sql = """
                ts_rank_cd(
                    {search_vector},
                    plainto_tsquery('english', %s)
                ) DESC,
                publication_year DESC NULLS LAST
            """.format(search_vector=PUBLICATION_SEARCH_VECTOR_SQL)
            where_clause_for_select, select_params = build_where(filters)
            # WHERE parameters appear before the ORDER BY rank parameter.
            rows = self._fetch_all(
                f"""
                SELECT {select_columns(BASE_COLUMNS)}
                FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
                {where_clause_for_select}
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                [*select_params, filters["q"], page_size, (page - 1) * page_size],
            )
        else:
            rows = self._fetch_all(
                f"""
                SELECT {select_columns(BASE_COLUMNS)}
                FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
                {where_sql}
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, (page - 1) * page_size],
            )
        return {
            "records": rows,
            "total": total,
            "facets": self._facets(filters) if include_facets else None,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key: str) -> dict[str, Any] | None:
        return self._fetch_one(
            f"""
            SELECT {select_columns(BASE_COLUMNS)}
            FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
            WHERE publication_key = %s
            """,
            [publication_key],
        )

    def get_references(self, publication_key: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT
                reference_id,
                publication_key,
                publication_row_number,
                source_dataset,
                source_record_id,
                doi,
                reference_index,
                reference_doi,
                reference_title,
                reference_author,
                reference_year,
                raw_reference_json
            FROM final_publication_references
            WHERE publication_key = %s
            ORDER BY reference_index
            """,
            [publication_key],
        )

    def get_count_audit(self, publication_key: str) -> dict[str, Any] | None:
        return self._fetch_one(
            "SELECT * FROM final_publication_count_audit WHERE publication_key = %s",
            [publication_key],
        )

    def suggest(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if not query:
            return []
        pattern = f"%{query}%"
        rows = self._fetch_all(
            """
            SELECT title AS value, 'publication' AS type, publication_key AS key
            FROM final_publications
            WHERE title ILIKE %s
            UNION ALL
            SELECT journal AS value, 'journal' AS type, journal AS key
            FROM final_publications
            WHERE journal ILIKE %s
            LIMIT %s
            """,
            [pattern, pattern, limit],
        )
        seen = set()
        suggestions = []
        for row in rows:
            value = row.get("value")
            if not value or value in seen:
                continue
            seen.add(value)
            suggestions.append(row)
        return suggestions[:limit]

    def semantic_search(
        self,
        query: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        hits = self._semantic_search_index().search(
            query,
            filters=filters,
            limit=semantic_candidate_limit(limit),
            min_score=min_score,
        )
        return self._database_records_for_similarity_hits(
            hits,
            filters=filters,
            limit=limit,
        )

    def related_publications(
        self,
        publication_key: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        hits = self._semantic_search_index().related_publications(
            publication_key,
            filters=filters,
            limit=semantic_candidate_limit(limit),
            min_score=min_score,
        )
        return self._database_records_for_similarity_hits(
            hits,
            filters=filters,
            limit=limit,
        )

    def researcher_profile(self, researcher_key: str) -> dict[str, Any] | None:
        rows = self._rows_for_multivalue("authors", researcher_key)
        if not rows:
            return None
        return aggregate_profile(researcher_key, rows, kind="researcher")

    def researcher_publications(
        self,
        researcher_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self._list_by_multivalue("authors", researcher_key, page=page, page_size=page_size)

    def researcher_coauthors(self, researcher_key: str, *, limit: int) -> list[dict[str, Any]]:
        rows = self._rows_for_multivalue("authors", researcher_key)
        counter: Counter[str] = Counter()
        for row in rows:
            for author in split_semicolon_value(row.get("authors")):
                if author and normalized_key(author) != normalized_key(researcher_key):
                    counter[author] += 1
        return [{"name": name, "publication_count": count} for name, count in counter.most_common(limit)]

    def institution_profile(self, institution_key: str) -> dict[str, Any] | None:
        rows = self._rows_for_multivalue("institutions", institution_key, extra_column="sri_lankan_institutions")
        if not rows:
            return None
        return aggregate_profile(institution_key, rows, kind="institution")

    def institution_publications(
        self,
        institution_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self._list_by_multivalue(
            "institutions",
            institution_key,
            page=page,
            page_size=page_size,
            extra_column="sri_lankan_institutions",
        )

    def institution_collaborators(self, institution_key: str, *, limit: int) -> list[dict[str, Any]]:
        rows = self._rows_for_multivalue("institutions", institution_key, extra_column="sri_lankan_institutions")
        counter: Counter[str] = Counter()
        for row in rows:
            institutions = split_semicolon_value(row.get("sri_lankan_institutions")) or split_semicolon_value(row.get("institutions"))
            for institution in institutions:
                if institution and normalized_key(institution) != normalized_key(institution_key):
                    counter[institution] += 1
        return [{"institution": name, "publication_count": count} for name, count in counter.most_common(limit)]

    def compare_institutions(self, institution_keys: list[str]) -> list[dict[str, Any]]:
        profiles = []
        for institution_key in institution_keys:
            profile = self.institution_profile(institution_key)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def topic_publications(
        self,
        topic_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self._list_by_multivalue("topics", topic_key, page=page, page_size=page_size, extra_column="concepts")

    def analytics_overview(self, filters: dict[str, Any]) -> dict[str, Any]:
        result = self.list_publications(filters, page=1, page_size=1_000_000, sort="year_desc", include_facets=False)
        rows = result["records"]
        total = result["total"]
        citation_values = [row.get("citation_count") or 0 for row in rows]
        return {
            "publication_count": total,
            "citation_total": sum(citation_values),
            "average_citations": round(sum(citation_values) / len(citation_values), 2) if citation_values else 0,
            "open_access_share": ratio(sum(1 for row in rows if row.get("is_oa")), len(rows)),
            "doi_coverage": ratio(sum(1 for row in rows if row.get("doi")), len(rows)),
            "abstract_coverage": ratio(sum(1 for row in rows if row.get("abstract")), len(rows)),
            "source_count": len({source for row in rows for source in split_semicolon_value(row.get("source_dataset"))}),
            "limitations": ["observed_records_not_national_totals"],
        }

    def analytics_trends(self, filters: dict[str, Any], *, group_by: str, metric: str) -> list[dict[str, Any]]:
        dimension = {
            "year": "publication_year",
            "type": "type",
            "field": "primary_field",
            "institution": "institutions",
        }.get(group_by)
        if dimension is None:
            dimension = "publication_year"
        rows = self.list_publications(filters, page=1, page_size=1_000_000, sort="year_asc", include_facets=False)["records"]
        counter: dict[str, dict[str, Any]] = {}
        for row in rows:
            values = split_semicolon_value(row.get(dimension)) if dimension in {"institutions"} else [row.get(dimension)]
            for value in values:
                if value in (None, ""):
                    continue
                key = str(value)
                counter.setdefault(key, {"key": value, "publication_count": 0, "citation_total": 0})
                counter[key]["publication_count"] += 1
                counter[key]["citation_total"] += row.get("citation_count") or 0
        return list(counter.values())

    def analytics_rankings(
        self,
        filters: dict[str, Any],
        *,
        dimension: str,
        metric: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.list_publications(filters, page=1, page_size=1_000_000, sort="year_desc", include_facets=False)["records"]
        counter: Counter[str] = Counter()
        citations: Counter[str] = Counter()
        for row in rows:
            values = split_semicolon_value(row.get(dimension))
            if not values and dimension in row:
                values = [row.get(dimension)]
            for value in values:
                if value in (None, ""):
                    continue
                counter[str(value)] += 1
                citations[str(value)] += row.get("citation_count") or 0
        ranked = []
        for key, publication_count in counter.most_common(limit):
            ranked.append(
                {
                    "key": normalized_key(key),
                    "label": key,
                    "publication_count": publication_count,
                    "citation_total": citations[key],
                }
            )
        return ranked

    def collaboration_network(
        self,
        filters: dict[str, Any],
        *,
        scope: str,
        min_weight: int,
        limit: int,
    ) -> dict[str, Any]:
        field = {"institution": "institutions", "country": "countries", "researcher": "authors"}[scope]
        rows = self.list_publications(filters, page=1, page_size=1_000_000, sort="year_desc", include_facets=False)["records"]
        node_counts: Counter[str] = Counter()
        edge_counts: Counter[tuple[str, str]] = Counter()
        for row in rows:
            values = sorted(set(split_semicolon_value(row.get(field))))
            for value in values:
                node_counts[value] += 1
            for index, source in enumerate(values):
                for target in values[index + 1 :]:
                    edge_counts[(source, target)] += 1
        edges = [
            {"source": normalized_key(source), "target": normalized_key(target), "weight": weight}
            for (source, target), weight in edge_counts.most_common(limit)
            if weight >= min_weight
        ]
        active_node_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
        nodes = [
            {
                "id": normalized_key(label),
                "label": label,
                "type": scope,
                "publication_count": count,
            }
            for label, count in node_counts.most_common(limit)
            if normalized_key(label) in active_node_ids
        ]
        return {"nodes": nodes, "edges": edges}

    def data_quality(self, filters: dict[str, Any], *, group_by: str | None) -> dict[str, Any]:
        rows = self.list_publications(filters, page=1, page_size=1_000_000, sort="year_desc", include_facets=False)["records"]
        total = len(rows)
        summary = {
            "record_count": total,
            "missing_doi_percentage": percentage(sum(1 for row in rows if not row.get("doi")), total),
            "missing_abstract_percentage": percentage(sum(1 for row in rows if not row.get("abstract")), total),
            "missing_institutions_percentage": percentage(
                sum(1 for row in rows if not row.get("institutions") and not row.get("sri_lankan_institutions")),
                total,
            ),
            "citation_divergence_count": sum(1 for row in rows if row.get("citation_count_divergence_flag")),
            "reference_divergence_count": sum(1 for row in rows if row.get("reference_count_divergence_flag")),
        }
        if not group_by:
            return summary
        grouped: dict[str, dict[str, Any]] = {}
        dimension = {"source_dataset": "source_dataset", "type": "type", "institution": "institutions", "year": "publication_year"}.get(group_by)
        if not dimension:
            return summary
        for row in rows:
            values = split_semicolon_value(row.get(dimension)) if dimension in {"source_dataset", "institutions"} else [row.get(dimension)]
            for value in values:
                if value in (None, ""):
                    continue
                key = str(value)
                grouped.setdefault(key, {"record_count": 0, "missing_doi_count": 0, "missing_abstract_count": 0})
                grouped[key]["record_count"] += 1
                grouped[key]["missing_doi_count"] += 0 if row.get("doi") else 1
                grouped[key]["missing_abstract_count"] += 0 if row.get("abstract") else 1
        summary["groups"] = grouped
        return summary

    def _facets(self, filters: dict[str, Any]) -> dict[str, Any]:
        rows = self.list_publications(filters, page=1, page_size=1_000_000, sort="year_desc", include_facets=False)["records"]
        facets: dict[str, dict[str, int]] = {}
        for name, column in {
            "publication_year": "publication_year",
            "type": "type",
            "source_dataset": "source_dataset",
            "sri_lankan_institutions": "sri_lankan_institutions",
            "countries": "countries",
            "primary_field": "primary_field",
            "primary_subfield": "primary_subfield",
            "topics": "topics",
            "journal": "journal",
            "is_oa": "is_oa",
        }.items():
            counter: Counter[str] = Counter()
            for row in rows:
                values = split_semicolon_value(row.get(column)) if column in {"source_dataset", "sri_lankan_institutions", "countries", "topics"} else [row.get(column)]
                for value in values:
                    if value not in (None, ""):
                        counter[str(value)] += 1
            facets[name] = dict(counter.most_common(25))
        quality_counter: Counter[str] = Counter()
        for row in rows:
            quality_counter.update(quality_flags(row))
        facets["quality_flags"] = dict(quality_counter.most_common(25))
        return facets

    def _list_by_multivalue(
        self,
        column: str,
        value: str,
        *,
        page: int,
        page_size: int,
        extra_column: str | None = None,
    ) -> dict[str, Any]:
        rows = self._rows_for_multivalue(column, value, extra_column=extra_column)
        start = (page - 1) * page_size
        return {"records": rows[start : start + page_size], "total": len(rows)}

    def _rows_for_multivalue(
        self,
        column: str,
        value: str,
        *,
        extra_column: str | None = None,
    ) -> list[dict[str, Any]]:
        columns = [column]
        if extra_column:
            columns.append(extra_column)
        clauses = [f"{quote_identifier(item)} ILIKE %s" for item in columns]
        params = [f"%{value}%" for _ in columns]
        return self._fetch_all(
            f"""
            SELECT {select_columns(BASE_COLUMNS)}
            FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
            WHERE {" OR ".join(clauses)}
            ORDER BY publication_year DESC NULLS LAST, title ASC NULLS LAST
            """,
            params,
        )

    def _fetch_one(self, sql: str, params: list[Any]) -> dict[str, Any] | None:
        rows = self._fetch_all(sql, params)
        return rows[0] if rows else None

    def _semantic_search_index(self) -> SemanticSearchIndex:
        if self._semantic_index is None:
            self._semantic_index = load_semantic_search_index(
                embeddings_path=self.semantic_embeddings_path,
                model_path=self.semantic_model_path,
            )
        return self._semantic_index

    def _database_records_for_similarity_hits(
        self,
        hits: list[dict[str, Any]],
        *,
        filters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not hits:
            return []
        records = self._fetch_similarity_candidate_records(hits, filters=filters)
        return merge_similarity_hits_with_database_records(
            hits,
            records,
            limit=limit,
        )

    def _fetch_similarity_candidate_records(
        self,
        hits: list[dict[str, Any]],
        *,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        identifier_sql, identifier_params = similarity_identifier_where(hits)
        if not identifier_sql:
            return []

        where_parts = [f"({identifier_sql})"]
        params = list(identifier_params)
        filter_sql, filter_params = build_where(filters)
        if filter_sql:
            where_parts.append(f"({filter_sql.removeprefix('WHERE ').strip()})")
            params.extend(filter_params)

        return self._fetch_all(
            f"""
            SELECT {select_columns(BASE_COLUMNS)}
            FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
            WHERE {" AND ".join(where_parts)}
            """,
            params,
        )

    def _fetch_all(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        with closing(self.connection_factory(None)) as connection:
            try:
                from psycopg.rows import dict_row

                cursor_context = connection.cursor(row_factory=dict_row)
            except (ImportError, TypeError):
                cursor_context = connection.cursor()
            with cursor_context as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                if not rows:
                    return []
                if isinstance(rows[0], dict):
                    return [dict(row) for row in rows]
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in rows]


def semantic_candidate_limit(requested_limit: int) -> int:
    """Fetch extra vector hits so DB-side hydration/filtering can still fill results."""

    if requested_limit < 1:
        return requested_limit
    return min(max(requested_limit * 5, requested_limit + 25), MAX_SEMANTIC_CANDIDATES)


def similarity_identifier_where(hits: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    publication_keys = unique_nonblank(hit.get("publication_key") for hit in hits)
    dois = unique_nonblank(hit.get("doi") for hit in hits)
    openalex_ids = unique_nonblank(hit.get("openalex_id") for hit in hits)
    source_record_ids = unique_nonblank(hit.get("source_record_id") for hit in hits)
    source_pairs = unique_pairs(
        (source, hit.get("source_record_id"))
        for hit in hits
        for source in source_values(hit.get("source_dataset"))
    )
    institution_pairs = unique_pairs(
        (hit.get("source_institution_id"), hit.get("source_record_id"))
        for hit in hits
    )

    clauses: list[str] = []
    params: list[Any] = []
    if publication_keys:
        clauses.append("publication_key = ANY(%s)")
        params.append(publication_keys)
    if dois:
        clauses.append("doi = ANY(%s)")
        params.append(dois)
    if openalex_ids:
        clauses.append("openalex_id = ANY(%s)")
        params.append(openalex_ids)
    if source_record_ids:
        clauses.append("source_record_id = ANY(%s)")
        params.append(source_record_ids)
    for source_dataset, source_record_id in source_pairs:
        clauses.append("(source_dataset ILIKE %s AND source_record_id = %s)")
        params.extend([f"%{source_dataset}%", source_record_id])
    for source_institution_id, source_record_id in institution_pairs:
        clauses.append("(source_institution_id = %s AND source_record_id = %s)")
        params.extend([source_institution_id, source_record_id])

    return " OR ".join(clauses), params


def merge_similarity_hits_with_database_records(
    hits: list[dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    indexes = database_record_indexes(records)
    merged: list[dict[str, Any]] = []
    seen_publication_keys: set[str] = set()

    for hit in hits:
        record = match_similarity_hit(hit, indexes)
        if record is None:
            continue
        publication_key = nonblank_string(record.get("publication_key"))
        if publication_key and publication_key.casefold() in seen_publication_keys:
            continue
        if publication_key:
            seen_publication_keys.add(publication_key.casefold())

        row = dict(record)
        for field in SIMILARITY_RESULT_FIELDS:
            if field in hit:
                row[field] = hit[field]
        merged.append(row)
        if len(merged) >= limit:
            break

    return merged


def database_record_indexes(records: list[dict[str, Any]]) -> dict[str, dict[Any, dict[str, Any]]]:
    source_record_counts: Counter[str] = Counter()
    for record in records:
        source_record_id = normalized_identifier(record.get("source_record_id"))
        if source_record_id:
            source_record_counts[source_record_id] += 1

    indexes: dict[str, dict[Any, dict[str, Any]]] = {
        "publication_key": {},
        "doi": {},
        "openalex_id": {},
        "source_pair": {},
        "institution_pair": {},
        "source_record_id": {},
    }

    for record in records:
        add_identifier_index(indexes["publication_key"], record.get("publication_key"), record)
        add_identifier_index(indexes["doi"], record.get("doi"), record)
        add_identifier_index(indexes["openalex_id"], record.get("openalex_id"), record)

        source_record_id = normalized_identifier(record.get("source_record_id"))
        if source_record_id and source_record_counts[source_record_id] == 1:
            indexes["source_record_id"][source_record_id] = record

        for source_dataset in source_values(record.get("source_dataset")):
            if source_record_id:
                indexes["source_pair"][(normalized_identifier(source_dataset), source_record_id)] = record

        source_institution_id = normalized_identifier(record.get("source_institution_id"))
        if source_institution_id and source_record_id:
            indexes["institution_pair"][(source_institution_id, source_record_id)] = record

    return indexes


def match_similarity_hit(
    hit: dict[str, Any],
    indexes: dict[str, dict[Any, dict[str, Any]]],
) -> dict[str, Any] | None:
    for field in ("publication_key", "doi", "openalex_id"):
        key = normalized_identifier(hit.get(field))
        if key and key in indexes[field]:
            return indexes[field][key]

    source_record_id = normalized_identifier(hit.get("source_record_id"))
    if source_record_id:
        for source_dataset in source_values(hit.get("source_dataset")):
            key = (normalized_identifier(source_dataset), source_record_id)
            if key in indexes["source_pair"]:
                return indexes["source_pair"][key]

        source_institution_id = normalized_identifier(hit.get("source_institution_id"))
        institution_key = (source_institution_id, source_record_id)
        if source_institution_id and institution_key in indexes["institution_pair"]:
            return indexes["institution_pair"][institution_key]

        if source_record_id in indexes["source_record_id"]:
            return indexes["source_record_id"][source_record_id]

    return None


def add_identifier_index(
    index: dict[Any, dict[str, Any]],
    value: Any,
    record: dict[str, Any],
) -> None:
    key = normalized_identifier(value)
    if key:
        index[key] = record


def source_values(value: Any) -> list[str]:
    values = split_semicolon_value(value)
    if not values and nonblank_string(value):
        values = [str(value)]
    return [str(item) for item in values if nonblank_string(item)]


def unique_nonblank(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = nonblank_string(value)
        if text is None:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def unique_pairs(values: Any) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    output: list[tuple[str, str]] = []
    for left, right in values:
        left_text = nonblank_string(left)
        right_text = nonblank_string(right)
        if left_text is None or right_text is None:
            continue
        key = (left_text.casefold(), right_text.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append((left_text, right_text))
    return output


def normalized_identifier(value: Any) -> str | None:
    text = nonblank_string(value)
    return text.casefold() if text is not None else None


def nonblank_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return None
    return text
