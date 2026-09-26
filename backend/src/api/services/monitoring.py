"""Admin monitoring metrics for public product reliability."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from src.database.connection import get_connection


DRIFT_ALERT_THRESHOLD_POINTS = 20.0


def monitoring_dashboard(connection: Any) -> dict[str, Any]:
    public_row = fetch_one(
        connection,
        """
        SELECT count(*) AS public_publications,
               count(*) FILTER (WHERE NULLIF(btrim(coalesce(doi::text, '')), '') IS NULL)
                    AS missing_doi,
               count(*) FILTER (WHERE NULLIF(btrim(coalesce(abstract::text, '')), '') IS NULL)
                    AS missing_abstract,
               max(dataset_version) AS dataset_version,
               max(pipeline_version) AS pipeline_version,
               max(classifier_version) AS model_version
        FROM public_eligible_publications
        """,
    )
    review_row = fetch_one(
        connection,
        """
        SELECT count(*) AS review_records,
               count(*) FILTER (WHERE review_status = 'pending_review') AS pending_reviews,
               count(*) FILTER (WHERE review_status IN ('auto_accepted', 'human_accepted')) AS accepted,
               count(*) FILTER (WHERE review_status = 'auto_accepted') AS auto_ai,
               count(*) FILTER (
                   WHERE review_status = 'human_rejected'
                     AND normalized_ai_label = 'NON_AI'
               ) AS auto_non_ai,
               count(*) FILTER (
                   WHERE review_status = 'human_rejected'
                     AND normalized_ai_label = 'AI'
               ) AS false_positive_proxy,
               count(*) FILTER (
                   WHERE review_status IN ('human_accepted', 'human_rejected')
               ) AS human_decisions,
               count(*) FILTER (
                   WHERE review_status = 'human_rejected'
               ) AS human_disagreements
        FROM ai_review_records
        """,
    )
    ownership_row = fetch_one(
        connection,
        """
        SELECT count(*) AS ownership_review_count
        FROM final_publications
        WHERE lower(coalesce(needs_manual_review::text, 'false')) IN ('true', '1', 'yes')
           OR upper(coalesce(ownership_decision, '')) = 'REVIEW'
           OR upper(coalesce(ownership_confidence, '')) IN ('LOW', 'CONFLICT')
        """,
    )
    pipeline_row = fetch_one(
        connection,
        """
        SELECT
            max(finished_at) FILTER (WHERE status = 'succeeded') AS last_successful_pipeline_run,
            count(*) FILTER (WHERE status = 'failed') AS failed_ingestion_jobs,
            avg(records_collected) FILTER (
                WHERE started_at >= now() - interval '30 days'
            ) AS avg_publications_collected_per_run
        FROM incremental_pipeline_runs
        """,
    )
    daily_row = fetch_one(
        connection,
        """
        SELECT round(avg(day_count)::numeric, 2) AS publications_collected_per_day
        FROM (
            SELECT date_trunc('day', loaded_at)::date AS day, count(*) AS day_count
            FROM final_publications
            WHERE loaded_at >= now() - interval '30 days'
            GROUP BY 1
        ) daily
        """,
    )
    duplicate_row = fetch_one(
        connection,
        """
        SELECT count(*) AS duplicate_reports
        FROM user_feedback_reports
        WHERE report_type = 'duplicate_publication'
          AND status IN ('open', 'in_review', 'resolved')
        """,
    )
    drift_rows = fetch_all(
        connection,
        """
        SELECT to_char(date_trunc('month', created_at), 'YYYY-MM') AS month,
               count(*) AS total,
               count(*) FILTER (WHERE review_status = 'auto_accepted') AS auto_ai
        FROM ai_review_records
        WHERE created_at >= date_trunc('month', now()) - interval '1 month'
        GROUP BY date_trunc('month', created_at)
        ORDER BY date_trunc('month', created_at)
        """,
    )

    total_public = int(public_row.get("public_publications") or 0)
    total_reviews = int(review_row.get("review_records") or 0)
    human_decisions = int(review_row.get("human_decisions") or 0)
    duplicate_reports = int(duplicate_row.get("duplicate_reports") or 0)
    drift = drift_summary(drift_rows)

    return {
        "public_publications": total_public,
        "pending_reviews": int(review_row.get("pending_reviews") or 0),
        "ai_acceptance_rate": percent(review_row.get("accepted"), total_reviews),
        "auto_ai_rate": percent(review_row.get("auto_ai"), total_reviews),
        "auto_non_ai_rate": percent(review_row.get("auto_non_ai"), total_reviews),
        "false_positive_rate": percent(review_row.get("false_positive_proxy"), total_reviews),
        "human_disagreement_rate": percent(
            review_row.get("human_disagreements"),
            human_decisions,
        ),
        "publications_collected_per_day": float(
            daily_row.get("publications_collected_per_day") or 0
        ),
        "failed_ingestion_jobs": int(pipeline_row.get("failed_ingestion_jobs") or 0),
        "duplicate_rate": percent(duplicate_reports, max(total_public, 1)),
        "missing_abstract_percentage": percent(public_row.get("missing_abstract"), total_public),
        "missing_doi_percentage": percent(public_row.get("missing_doi"), total_public),
        "ownership_review_count": int(ownership_row.get("ownership_review_count") or 0),
        "model_version": public_row.get("model_version"),
        "dataset_version": public_row.get("dataset_version"),
        "pipeline_version": public_row.get("pipeline_version"),
        "last_successful_pipeline_run": pipeline_row.get("last_successful_pipeline_run"),
        "avg_publications_collected_per_run": float(
            pipeline_row.get("avg_publications_collected_per_run") or 0
        ),
        "drift": drift,
        "metric_notes": {
            "false_positive_rate": "Proxy: AI-labelled records later human-rejected.",
            "duplicate_rate": "Proxy: active/resolved duplicate reports over public publications.",
            "auto_non_ai_rate": "System rejected NON_AI rows in the review workflow.",
        },
    }


def drift_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    monthly = [
        {
            "month": row["month"],
            "auto_ai_rate": percent(row.get("auto_ai"), row.get("total")),
            "auto_ai_count": int(row.get("auto_ai") or 0),
            "total": int(row.get("total") or 0),
        }
        for row in rows
    ]
    previous = monthly[-2] if len(monthly) >= 2 else None
    current = monthly[-1] if monthly else None
    delta = None
    alert = False
    if previous and current:
        delta = round(current["auto_ai_rate"] - previous["auto_ai_rate"], 2)
        alert = abs(delta) >= DRIFT_ALERT_THRESHOLD_POINTS
    return {
        "previous_month": previous,
        "current_month": current,
        "auto_ai_rate_delta_points": delta,
        "alert": alert,
        "alert_threshold_points": DRIFT_ALERT_THRESHOLD_POINTS,
        "monthly": monthly,
    }


def percent(numerator: Any, denominator: Any) -> float:
    try:
        den = float(denominator or 0)
        if den <= 0:
            return 0.0
        return round((float(numerator or 0) / den) * 100, 2)
    except (TypeError, ValueError):
        return 0.0


def fetch_one(connection: Any, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
    return dict(row or {})


def fetch_all(connection: Any, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params or [])
        return [dict(row) for row in cursor.fetchall()]


def with_connection(callback: Any) -> Any:
    connection = get_connection()
    try:
        return callback(connection)
    finally:
        connection.close()
