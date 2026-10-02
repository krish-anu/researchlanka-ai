"""Admin monitoring metrics for public product reliability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from src.database.connection import get_connection
from src.api.services.ml_monitoring import compute_ml_monitoring
from src.pipeline.refresh_policy import load_ai_relevance_model_manifest


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
    model_contract = current_model_contract()
    ml_monitoring = compute_ml_monitoring(connection)
    drift = drift_summary(drift_rows, ml_monitoring=ml_monitoring)

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
        "model_version": model_contract.get("model_id") or public_row.get("model_version"),
        "model_contract": model_contract,
        "dataset_version": public_row.get("dataset_version"),
        "pipeline_version": public_row.get("pipeline_version"),
        "last_successful_pipeline_run": pipeline_row.get("last_successful_pipeline_run"),
        "avg_publications_collected_per_run": float(
            pipeline_row.get("avg_publications_collected_per_run") or 0
        ),
        "drift": drift,
        "ml_monitoring": ml_monitoring,
        "metric_notes": {
            "false_positive_rate": "Workflow proxy only; use model holdout FP for trained-model quality.",
            "duplicate_rate": "Proxy: active/resolved duplicate reports over public publications.",
            "auto_non_ai_rate": "System rejected NON_AI rows in the review workflow.",
            "human_disagreement_rate": "Workflow proxy only; not a frozen-test model metric.",
        },
    }


def current_model_contract() -> dict[str, Any]:
    """Return the deployed AI relevance model contract plus known holdout metrics."""

    manifest = load_ai_relevance_model_manifest()
    payload: dict[str, Any] = {
        "model_id": manifest.model_id,
        "model_type": manifest.model_type,
        "model_path": relative_path(manifest.model_path),
        "features": list(manifest.features),
        "training_dataset": manifest.training_dataset,
        "created_at": manifest.created_at,
        "sha256": manifest.sha256,
        "auto_ai_threshold": manifest.auto_ai_threshold,
        "auto_non_ai_threshold": manifest.auto_non_ai_threshold,
        "selected_binary_threshold": manifest.selected_binary_threshold,
    }
    summary_metrics = model_summary_metrics(manifest.model_path)
    if summary_metrics:
        payload["evaluation"] = summary_metrics
    return payload


def model_summary_metrics(model_path: Path | None) -> dict[str, Any] | None:
    if model_path is None:
        return None
    summary_path = model_path.with_name("metadata_ablation_summary.json")
    if not summary_path.is_file():
        return None
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = summary.get("rows")
    if not isinstance(rows, list):
        return None
    model_stem = model_path.stem
    selected = next(
        (
            row
            for row in rows
            if isinstance(row, dict)
            and (
                row.get("ablation") == model_stem
                or Path(str(row.get("model_path") or "")).name == model_path.name
            )
        ),
        None,
    )
    if not isinstance(selected, dict):
        return None
    confusion = selected.get("test_confusion_matrix")
    false_positives = None
    false_negatives = None
    if (
        isinstance(confusion, list)
        and len(confusion) >= 2
        and isinstance(confusion[0], list)
        and isinstance(confusion[1], list)
        and len(confusion[0]) >= 2
        and len(confusion[1]) >= 2
    ):
        # Matrix order is labels AI, NON_AI: [[TP, FN], [FP, TN]].
        false_negatives = int(confusion[0][1])
        false_positives = int(confusion[1][0])
    return {
        "source": "frozen_human_holdout",
        "ablation": selected.get("ablation"),
        "test_accuracy": selected.get("test_accuracy"),
        "test_macro_f1": selected.get("test_macro_f1"),
        "test_ai_precision": selected.get("test_ai_precision"),
        "test_ai_recall": selected.get("test_ai_recall"),
        "test_non_ai_recall": selected.get("test_non_ai_recall"),
        "test_false_positives": false_positives,
        "test_false_negatives": false_negatives,
        "test_confusion_matrix": confusion,
        "comparison_csv": summary.get("comparison_csv"),
    }


def relative_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(Path(__file__).resolve().parents[3]))
    except ValueError:
        return str(path)


def drift_summary(
    rows: list[dict[str, Any]],
    ml_monitoring: dict[str, Any] | None = None,
) -> dict[str, Any]:
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

    ml_report = ml_monitoring or {}
    overall_alert = alert or ml_report.get("overall_alert", False)

    return {
        "previous_month": previous,
        "current_month": current,
        "auto_ai_rate_delta_points": delta,
        "alert": overall_alert,
        "legacy_drift_alert": alert,
        "alert_threshold_points": DRIFT_ALERT_THRESHOLD_POINTS,
        "monthly": monthly,
        "ml_monitoring": ml_report,
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
