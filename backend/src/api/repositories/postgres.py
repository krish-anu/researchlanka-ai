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
    SemanticSearchIndex,
    default_semantic_embeddings_path,
    default_semantic_model_path,
    load_semantic_search_index,
)


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
        return self._semantic_search_index().search(
            query,
            filters=filters,
            limit=limit,
            min_score=min_score,
        )

    def related_publications(
        self,
        publication_key: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        return self._semantic_search_index().related_publications(
            publication_key,
            filters=filters,
            limit=limit,
            min_score=min_score,
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
