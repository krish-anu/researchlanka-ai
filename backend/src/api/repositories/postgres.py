"""PostgreSQL repository for the read-only ResearchLanka API."""

from __future__ import annotations

import os
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from src.api.core.constants import (
    PUBLICATION_COVERAGE_END_YEAR,
    PUBLICATION_COVERAGE_START_YEAR,
)
from src.api.core.serializers import quality_flags, split_semicolon_value
from src.api.repositories.aggregates import aggregate_profile, normalized_key, percentage, ratio
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
LOCAL_SOURCE_DATASETS = ["local", "repositories", "repositories_combined", "sljol"]
GLOBAL_SOURCE_DATASETS = ["openalex", "crossref"]
MULTIVALUE_ANALYTICS_COLUMNS = {
    "authors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "topics",
    "concepts",
    "source_dataset",
}


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


def column_ref(column: str, *, alias: str | None = None) -> str:
    reference = quote_identifier(column)
    return f"{alias}.{reference}" if alias else reference


def nonempty_text_condition(expression: str) -> str:
    return f"NULLIF(btrim(coalesce({expression}::text, '')), '') IS NOT NULL"


def _network_node_id(node_key: Any, label: Any) -> str:
    key = str(node_key or "").strip()
    if key and key != str(label or "").strip():
        return key
    return normalized_key(str(label or key))


def split_value_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        str(row["value"]): int(row.get("count") or 0)
        for row in rows
        if row.get("value") not in (None, "")
    }


def metric_count(value: Any) -> int:
    return int(value or 0)


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
            WHERE publication_year >= %s
              AND publication_year <= %s
            """,
            [PUBLICATION_COVERAGE_START_YEAR, PUBLICATION_COVERAGE_END_YEAR],
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
              AND publication_year >= %s
              AND publication_year <= %s
            UNION ALL
            SELECT journal AS value, 'journal' AS type, journal AS key
            FROM final_publications
            WHERE journal ILIKE %s
              AND publication_year >= %s
              AND publication_year <= %s
            LIMIT %s
            """,
            [
                pattern,
                PUBLICATION_COVERAGE_START_YEAR,
                PUBLICATION_COVERAGE_END_YEAR,
                pattern,
                PUBLICATION_COVERAGE_START_YEAR,
                PUBLICATION_COVERAGE_END_YEAR,
                limit,
            ],
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
        cte_sql, params = self._filtered_cte(
            filters,
            ["citation_count", "is_oa", "doi", "abstract", "source_dataset"],
        )
        row = self._fetch_one(
            f"""
            {cte_sql}
            SELECT
                count(*) AS publication_count,
                coalesce(sum(coalesce(citation_count, 0)), 0) AS citation_total,
                count(*) FILTER (WHERE is_oa IS TRUE) AS open_access_count,
                count(*) FILTER (WHERE {nonempty_text_condition(column_ref('doi'))}) AS doi_count,
                count(*) FILTER (WHERE {nonempty_text_condition(column_ref('abstract'))}) AS abstract_count
            FROM filtered
            """,
            params,
        ) or {}
        total = metric_count(row.get("publication_count"))
        citation_total = metric_count(row.get("citation_total"))
        return {
            "publication_count": total,
            "citation_total": citation_total,
            "average_citations": round(citation_total / total, 2) if total else 0,
            "open_access_share": ratio(metric_count(row.get("open_access_count")), total),
            "doi_coverage": ratio(metric_count(row.get("doi_count")), total),
            "abstract_coverage": ratio(metric_count(row.get("abstract_count")), total),
            "source_count": self._count_distinct_multivalue(filters, "source_dataset"),
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
        return self._grouped_metrics(
            filters,
            dimension,
            multivalue=dimension == "institutions",
            order_by_key=True,
        )

    def analytics_rankings(
        self,
        filters: dict[str, Any],
        *,
        dimension: str,
        metric: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if dimension not in BASE_COLUMNS:
            return []
        label_ref = column_ref(dimension)
        cte_sql, params = self._filtered_cte(filters, [dimension, "citation_count"])
        order_metric = "citation_total" if metric == "citations" else "publication_count"
        if dimension in MULTIVALUE_ANALYTICS_COLUMNS:
            rows = self._fetch_all(
                f"""
                {cte_sql}
                SELECT
                    btrim(split.value) AS label,
                    count(*) AS publication_count,
                    coalesce(sum(coalesce(citation_count, 0)), 0) AS citation_total
                FROM filtered
                CROSS JOIN LATERAL regexp_split_to_table(coalesce({label_ref}::text, ''), ';') AS split(value)
                WHERE btrim(split.value) <> ''
                GROUP BY 1
                ORDER BY {order_metric} DESC, label ASC
                LIMIT %s
                """,
                [*params, limit],
            )
        else:
            rows = self._fetch_all(
                f"""
                {cte_sql}
                SELECT
                    {label_ref}::text AS label,
                    count(*) AS publication_count,
                    coalesce(sum(coalesce(citation_count, 0)), 0) AS citation_total
                FROM filtered
                WHERE {nonempty_text_condition(label_ref)}
                GROUP BY 1
                ORDER BY {order_metric} DESC, label ASC
                LIMIT %s
                """,
                [*params, limit],
            )
        return [
            {
                "key": normalized_key(row["label"]),
                "label": row["label"],
                "publication_count": metric_count(row.get("publication_count")),
                "citation_total": metric_count(row.get("citation_total")),
            }
            for row in rows
        ]

    def collaboration_network(
        self,
        filters: dict[str, Any],
        *,
        scope: str,
        min_weight: int,
        limit: int,
    ) -> dict[str, Any]:
        if scope == "researcher":
            return self._author_collaboration_network(filters, min_weight=min_weight, limit=limit)

        fields = {
            "institution": ["institutions", "sri_lankan_institutions"],
            "country": ["countries"],
        }[scope]
        cte_sql, params = self._filtered_cte(
            filters,
            ["publication_key", "publication_year", *fields],
        )
        value_sources = "\nUNION ALL\n".join(
            f"""
                SELECT publication_key, btrim(split.value) AS label, publication_year
                FROM filtered
                CROSS JOIN LATERAL regexp_split_to_table(coalesce({column_ref(field)}::text, ''), ';') AS split(value)
                WHERE publication_key IS NOT NULL AND btrim(split.value) <> ''
            """
            for field in fields
        )
        edge_rows = self._fetch_all(
            f"""
            {cte_sql},
            publication_values AS (
                SELECT publication_key, label, publication_year
                FROM (
                    {value_sources}
                ) values_union
                GROUP BY publication_key, label, publication_year
            )
            SELECT
                source.label AS source_label,
                target.label AS target_label,
                count(*) AS weight,
                min(source.publication_year) AS first_year,
                max(source.publication_year) AS last_year
            FROM publication_values source
            JOIN publication_values target
                ON source.publication_key = target.publication_key
                AND source.label < target.label
            GROUP BY source.label, target.label
            HAVING count(*) >= %s
            ORDER BY weight DESC, source.label ASC, target.label ASC
            LIMIT %s
            """,
            [*params, min_weight, limit],
        )
        edges = [
            {
                "source": normalized_key(row["source_label"]),
                "target": normalized_key(row["target_label"]),
                "source_label": row["source_label"],
                "target_label": row["target_label"],
                "weight": metric_count(row.get("weight")),
                "edge_type": f"{scope}_collaboration",
                "first_year": row.get("first_year"),
                "last_year": row.get("last_year"),
            }
            for row in edge_rows
        ]
        active_labels = sorted(
            {
                str(label)
                for row in edge_rows
                for label in (row.get("source_label"), row.get("target_label"))
                if label not in (None, "")
            }
        )
        if not active_labels:
            return {"nodes": [], "edges": edges}
        node_rows = self._fetch_all(
            f"""
            {cte_sql},
            publication_values AS (
                SELECT publication_key, label, publication_year
                FROM (
                    {value_sources}
                ) values_union
                GROUP BY publication_key, label, publication_year
            )
            SELECT
                label,
                count(*) AS publication_count,
                min(publication_year) AS first_year,
                max(publication_year) AS last_year
            FROM publication_values
            WHERE label = ANY(%s::text[])
            GROUP BY label
            ORDER BY publication_count DESC, label ASC
            """,
            [*params, active_labels],
        )
        nodes = [
            {
                "id": normalized_key(row["label"]),
                "label": row["label"],
                "type": scope,
                "publication_count": metric_count(row.get("publication_count")),
                "first_year": row.get("first_year"),
                "last_year": row.get("last_year"),
            }
            for row in node_rows
        ]
        return {"nodes": nodes, "edges": edges}

    def _author_collaboration_network(
        self,
        filters: dict[str, Any],
        *,
        min_weight: int,
        limit: int,
    ) -> dict[str, Any]:
        cte_sql, params = self._filtered_cte(
            filters,
            ["publication_key", "authors", "author_ids", "publication_year"],
        )
        edge_rows = self._fetch_all(
            f"""
            {cte_sql},
            author_values AS (
                SELECT
                    publication_key,
                    coalesce(nullif(btrim(author_id.value), ''), btrim(author_name.value)) AS node_key,
                    btrim(author_name.value) AS label,
                    publication_year
                FROM filtered
                CROSS JOIN LATERAL unnest(string_to_array(coalesce(authors::text, ''), ';'))
                    WITH ORDINALITY AS author_name(value, position)
                LEFT JOIN LATERAL unnest(string_to_array(coalesce(author_ids::text, ''), ';'))
                    WITH ORDINALITY AS author_id(value, position)
                    ON author_id.position = author_name.position
                WHERE publication_key IS NOT NULL AND btrim(author_name.value) <> ''
            ),
            publication_author_values AS (
                SELECT
                    publication_key,
                    node_key,
                    min(label) AS label,
                    publication_year
                FROM author_values
                GROUP BY publication_key, node_key, publication_year
            )
            SELECT
                source.node_key AS source_key,
                target.node_key AS target_key,
                source.label AS source_label,
                target.label AS target_label,
                count(*) AS weight,
                min(source.publication_year) AS first_year,
                max(source.publication_year) AS last_year
            FROM publication_author_values source
            JOIN publication_author_values target
                ON source.publication_key = target.publication_key
                AND source.node_key < target.node_key
            GROUP BY source.node_key, target.node_key, source.label, target.label
            HAVING count(*) >= %s
            ORDER BY weight DESC, source.label ASC, target.label ASC
            LIMIT %s
            """,
            [*params, min_weight, limit],
        )
        edges = [
            {
                "source": _network_node_id(row["source_key"], row["source_label"]),
                "target": _network_node_id(row["target_key"], row["target_label"]),
                "source_label": row["source_label"],
                "target_label": row["target_label"],
                "weight": metric_count(row.get("weight")),
                "edge_type": "author_collaboration",
                "first_year": row.get("first_year"),
                "last_year": row.get("last_year"),
            }
            for row in edge_rows
        ]
        active_keys = sorted(
            {
                str(key)
                for row in edge_rows
                for key in (row.get("source_key"), row.get("target_key"))
                if key not in (None, "")
            }
        )
        if not active_keys:
            return {"nodes": [], "edges": edges}
        node_rows = self._fetch_all(
            f"""
            {cte_sql},
            author_values AS (
                SELECT
                    publication_key,
                    coalesce(nullif(btrim(author_id.value), ''), btrim(author_name.value)) AS node_key,
                    btrim(author_name.value) AS label,
                    publication_year
                FROM filtered
                CROSS JOIN LATERAL unnest(string_to_array(coalesce(authors::text, ''), ';'))
                    WITH ORDINALITY AS author_name(value, position)
                LEFT JOIN LATERAL unnest(string_to_array(coalesce(author_ids::text, ''), ';'))
                    WITH ORDINALITY AS author_id(value, position)
                    ON author_id.position = author_name.position
                WHERE publication_key IS NOT NULL AND btrim(author_name.value) <> ''
            ),
            publication_author_values AS (
                SELECT
                    publication_key,
                    node_key,
                    min(label) AS label,
                    publication_year
                FROM author_values
                GROUP BY publication_key, node_key, publication_year
            )
            SELECT
                node_key,
                min(label) AS label,
                count(*) AS publication_count,
                min(publication_year) AS first_year,
                max(publication_year) AS last_year
            FROM publication_author_values
            WHERE node_key = ANY(%s::text[])
            GROUP BY node_key
            ORDER BY publication_count DESC, label ASC
            """,
            [*params, active_keys],
        )
        nodes = [
            {
                "id": _network_node_id(row["node_key"], row["label"]),
                "label": row["label"],
                "type": "researcher",
                "publication_count": metric_count(row.get("publication_count")),
                "first_year": row.get("first_year"),
                "last_year": row.get("last_year"),
            }
            for row in node_rows
        ]
        return {"nodes": nodes, "edges": edges}

    def data_quality(self, filters: dict[str, Any], *, group_by: str | None) -> dict[str, Any]:
        cte_sql, params = self._filtered_cte(
            filters,
            [
                "doi",
                "abstract",
                "institutions",
                "sri_lankan_institutions",
                "citation_count_divergence_flag",
                "reference_count_divergence_flag",
            ],
        )
        empty_doi = f"NOT ({nonempty_text_condition(column_ref('doi'))})"
        empty_abstract = f"NOT ({nonempty_text_condition(column_ref('abstract'))})"
        missing_institutions = (
            f"NOT ({nonempty_text_condition(column_ref('institutions'))}) "
            f"AND NOT ({nonempty_text_condition(column_ref('sri_lankan_institutions'))})"
        )
        row = self._fetch_one(
            f"""
            {cte_sql}
            SELECT
                count(*) AS record_count,
                count(*) FILTER (WHERE {empty_doi}) AS missing_doi_count,
                count(*) FILTER (WHERE {empty_abstract}) AS missing_abstract_count,
                count(*) FILTER (WHERE {missing_institutions}) AS missing_institutions_count,
                count(*) FILTER (WHERE citation_count_divergence_flag IS TRUE) AS citation_divergence_count,
                count(*) FILTER (WHERE reference_count_divergence_flag IS TRUE) AS reference_divergence_count
            FROM filtered
            """,
            params,
        ) or {}
        total = metric_count(row.get("record_count"))
        summary = {
            "record_count": total,
            "missing_doi_percentage": percentage(metric_count(row.get("missing_doi_count")), total),
            "missing_abstract_percentage": percentage(metric_count(row.get("missing_abstract_count")), total),
            "missing_institutions_percentage": percentage(metric_count(row.get("missing_institutions_count")), total),
            "citation_divergence_count": metric_count(row.get("citation_divergence_count")),
            "reference_divergence_count": metric_count(row.get("reference_divergence_count")),
        }
        if not group_by:
            return summary
        dimension = {"source_dataset": "source_dataset", "type": "type", "institution": "institutions", "year": "publication_year"}.get(group_by)
        if not dimension:
            return summary
        summary["groups"] = self._data_quality_groups(
            filters,
            dimension,
            multivalue=dimension in {"source_dataset", "institutions"},
        )
        return summary

    def _facets(self, filters: dict[str, Any]) -> dict[str, Any]:
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
            if column in {"source_dataset", "sri_lankan_institutions", "countries", "topics"}:
                facets[name] = self._multivalue_counts(filters, column, limit=25)
            else:
                facets[name] = self._single_value_counts(filters, column, limit=25)
        facets["quality_flags"] = self._quality_flag_counts(filters, limit=25)
        return facets

    def _filtered_cte(self, filters: dict[str, Any], columns: list[str]) -> tuple[str, list[Any]]:
        where_sql, params = build_where(filters)
        selected_columns = select_columns(list(dict.fromkeys(columns)))
        return (
            f"""
            WITH filtered AS (
                SELECT {selected_columns}
                FROM {quote_identifier(FINAL_PUBLICATION_TABLE)}
                {where_sql}
            )
            """,
            list(params),
        )

    def _single_value_counts(
        self,
        filters: dict[str, Any],
        column: str,
        *,
        limit: int,
    ) -> dict[str, int]:
        value_ref = column_ref(column)
        if column == "is_oa":
            value_expression = (
                "CASE "
                "WHEN is_oa IS TRUE THEN 'True' "
                "WHEN is_oa IS FALSE THEN 'False' "
                "ELSE NULL END"
            )
            value_filter = f"{value_expression} IS NOT NULL"
        else:
            value_expression = f"{value_ref}::text"
            value_filter = nonempty_text_condition(value_ref)
        cte_sql, params = self._filtered_cte(filters, [column])
        rows = self._fetch_all(
            f"""
            {cte_sql}
            SELECT {value_expression} AS value, count(*) AS count
            FROM filtered
            WHERE {value_filter}
            GROUP BY 1
            ORDER BY count DESC, value ASC
            LIMIT %s
            """,
            [*params, limit],
        )
        return split_value_counts(rows)

    def _multivalue_counts(
        self,
        filters: dict[str, Any],
        column: str,
        *,
        limit: int,
    ) -> dict[str, int]:
        value_ref = column_ref(column)
        cte_sql, params = self._filtered_cte(filters, [column])
        rows = self._fetch_all(
            f"""
            {cte_sql}
            SELECT btrim(split.value) AS value, count(*) AS count
            FROM filtered
            CROSS JOIN LATERAL regexp_split_to_table(coalesce({value_ref}::text, ''), ';') AS split(value)
            WHERE btrim(split.value) <> ''
            GROUP BY 1
            ORDER BY count DESC, value ASC
            LIMIT %s
            """,
            [*params, limit],
        )
        return split_value_counts(rows)

    def _count_distinct_multivalue(self, filters: dict[str, Any], column: str) -> int:
        value_ref = column_ref(column)
        cte_sql, params = self._filtered_cte(filters, [column])
        row = self._fetch_one(
            f"""
            {cte_sql}
            SELECT count(DISTINCT btrim(split.value)) AS total
            FROM filtered
            CROSS JOIN LATERAL regexp_split_to_table(coalesce({value_ref}::text, ''), ';') AS split(value)
            WHERE btrim(split.value) <> ''
            """,
            params,
        )
        return metric_count((row or {}).get("total"))

    def _grouped_metrics(
        self,
        filters: dict[str, Any],
        column: str,
        *,
        multivalue: bool,
        order_by_key: bool,
    ) -> list[dict[str, Any]]:
        value_ref = column_ref(column)
        cte_sql, params = self._filtered_cte(filters, [column, "citation_count"])
        order_sql = "key ASC" if order_by_key else "publication_count DESC, key ASC"
        if multivalue:
            rows = self._fetch_all(
                f"""
                {cte_sql}
                SELECT
                    btrim(split.value) AS key,
                    count(*) AS publication_count,
                    coalesce(sum(coalesce(citation_count, 0)), 0) AS citation_total
                FROM filtered
                CROSS JOIN LATERAL regexp_split_to_table(coalesce({value_ref}::text, ''), ';') AS split(value)
                WHERE btrim(split.value) <> ''
                GROUP BY 1
                ORDER BY {order_sql}
                """,
                params,
            )
        else:
            rows = self._fetch_all(
                f"""
                {cte_sql}
                SELECT
                    {value_ref} AS key,
                    count(*) AS publication_count,
                    coalesce(sum(coalesce(citation_count, 0)), 0) AS citation_total
                FROM filtered
                WHERE {nonempty_text_condition(value_ref)}
                GROUP BY 1
                ORDER BY {order_sql}
                """,
                params,
            )
        return [
            {
                "key": row["key"],
                "publication_count": metric_count(row.get("publication_count")),
                "citation_total": metric_count(row.get("citation_total")),
            }
            for row in rows
        ]

    def _data_quality_groups(
        self,
        filters: dict[str, Any],
        column: str,
        *,
        multivalue: bool,
    ) -> dict[str, dict[str, int]]:
        value_ref = column_ref(column)
        cte_sql, params = self._filtered_cte(filters, [column, "doi", "abstract"])
        empty_doi = f"NOT ({nonempty_text_condition(column_ref('doi'))})"
        empty_abstract = f"NOT ({nonempty_text_condition(column_ref('abstract'))})"
        if multivalue:
            rows = self._fetch_all(
                f"""
                {cte_sql}
                SELECT
                    btrim(split.value) AS key,
                    count(*) AS record_count,
                    count(*) FILTER (WHERE {empty_doi}) AS missing_doi_count,
                    count(*) FILTER (WHERE {empty_abstract}) AS missing_abstract_count
                FROM filtered
                CROSS JOIN LATERAL regexp_split_to_table(coalesce({value_ref}::text, ''), ';') AS split(value)
                WHERE btrim(split.value) <> ''
                GROUP BY 1
                ORDER BY record_count DESC, key ASC
                """,
                params,
            )
        else:
            rows = self._fetch_all(
                f"""
                {cte_sql}
                SELECT
                    {value_ref}::text AS key,
                    count(*) AS record_count,
                    count(*) FILTER (WHERE {empty_doi}) AS missing_doi_count,
                    count(*) FILTER (WHERE {empty_abstract}) AS missing_abstract_count
                FROM filtered
                WHERE {nonempty_text_condition(value_ref)}
                GROUP BY 1
                ORDER BY record_count DESC, key ASC
                """,
                params,
            )
        return {
            str(row["key"]): {
                "record_count": metric_count(row.get("record_count")),
                "missing_doi_count": metric_count(row.get("missing_doi_count")),
                "missing_abstract_count": metric_count(row.get("missing_abstract_count")),
            }
            for row in rows
        }

    def _quality_flag_counts(self, filters: dict[str, Any], *, limit: int) -> dict[str, int]:
        cte_sql, params = self._filtered_cte(
            filters,
            [
                "doi",
                "abstract",
                "institutions",
                "sri_lankan_institutions",
                "citation_count_divergence_flag",
                "reference_count_divergence_flag",
                "source_dataset",
                "topics",
                "concepts",
            ],
        )
        source_ref = column_ref("source_dataset")
        has_local_source = (
            "EXISTS ("
            f"SELECT 1 FROM regexp_split_to_table(coalesce({source_ref}::text, ''), ';') AS source(value) "
            "WHERE lower(btrim(source.value)) = ANY(%s::text[])"
            ")"
        )
        has_global_source = (
            "EXISTS ("
            f"SELECT 1 FROM regexp_split_to_table(coalesce({source_ref}::text, ''), ';') AS source(value) "
            "WHERE lower(btrim(source.value)) = ANY(%s::text[])"
            ")"
        )
        missing_doi = f"NOT ({nonempty_text_condition(column_ref('doi'))})"
        missing_abstract = f"NOT ({nonempty_text_condition(column_ref('abstract'))})"
        missing_institutions = (
            f"NOT ({nonempty_text_condition(column_ref('institutions'))}) "
            f"AND NOT ({nonempty_text_condition(column_ref('sri_lankan_institutions'))})"
        )
        has_topics = (
            f"{nonempty_text_condition(column_ref('topics'))} "
            f"OR {nonempty_text_condition(column_ref('concepts'))}"
        )
        rows = self._fetch_all(
            f"""
            {cte_sql},
            flagged AS (
                SELECT 'missing_doi' AS value FROM filtered WHERE {missing_doi}
                UNION ALL
                SELECT 'missing_abstract' AS value FROM filtered WHERE {missing_abstract}
                UNION ALL
                SELECT 'missing_institutions' AS value FROM filtered WHERE {missing_institutions}
                UNION ALL
                SELECT 'citation_count_divergence' AS value FROM filtered WHERE citation_count_divergence_flag IS TRUE
                UNION ALL
                SELECT 'reference_count_divergence' AS value FROM filtered WHERE reference_count_divergence_flag IS TRUE
                UNION ALL
                SELECT 'repository_only' AS value FROM filtered WHERE {has_local_source} AND NOT ({has_global_source})
                UNION ALL
                SELECT 'no_doi_local_record' AS value FROM filtered WHERE {missing_doi} AND {has_local_source}
                UNION ALL
                SELECT 'topic_model_source' AS value FROM filtered WHERE {has_topics}
            )
            SELECT value, count(*) AS count
            FROM flagged
            GROUP BY 1
            ORDER BY count DESC, value ASC
            LIMIT %s
            """,
            [
                *params,
                LOCAL_SOURCE_DATASETS,
                GLOBAL_SOURCE_DATASETS,
                LOCAL_SOURCE_DATASETS,
                limit,
            ],
        )
        return split_value_counts(rows)

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
            WHERE ({" OR ".join(clauses)})
              AND publication_year >= %s
              AND publication_year <= %s
            ORDER BY publication_year DESC NULLS LAST, title ASC NULLS LAST
            """,
            [*params, PUBLICATION_COVERAGE_START_YEAR, PUBLICATION_COVERAGE_END_YEAR],
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
