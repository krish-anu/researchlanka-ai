"""Public user feedback loop for publication corrections."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.rows import dict_row

from src.api.core.errors import APIError
from src.database.connection import get_connection


FEEDBACK_TYPES = {
    "incorrect_ai_classification",
    "incorrect_author",
    "incorrect_institution",
    "duplicate_publication",
    "missing_publication",
}

FEEDBACK_STATUSES = {"open", "in_review", "resolved", "rejected"}


def submit_feedback(
    connection: Any,
    payload: Mapping[str, Any],
    *,
    user_agent: str | None = None,
) -> dict[str, Any]:
    report_type = clean_text(payload.get("report_type"))
    publication_key = clean_text(payload.get("publication_key")) or None
    detail = clean_text(payload.get("detail"))
    title = clean_text(payload.get("title")) or None

    if report_type not in FEEDBACK_TYPES:
        raise APIError(
            "invalid_feedback_type",
            "Choose a supported report type.",
            status=400,
            details={"supported": sorted(FEEDBACK_TYPES)},
        )
    if len(detail) < 10:
        raise APIError(
            "feedback_detail_required",
            "Add a sentence or two so an administrator knows what to check.",
            status=400,
        )
    if report_type != "missing_publication" and not publication_key:
        raise APIError(
            "publication_required",
            "A publication report must include publication_key.",
            status=400,
        )

    trace = publication_trace(connection, publication_key) if publication_key else {}
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            INSERT INTO user_feedback_reports (
                publication_key,
                report_type,
                title,
                detail,
                reporter_name,
                reporter_email,
                page_url,
                user_agent,
                dataset_version,
                classifier_version,
                classifier_decision,
                classifier_probability
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                publication_key,
                report_type,
                title,
                detail,
                clean_text(payload.get("reporter_name")) or None,
                clean_text(payload.get("reporter_email")) or None,
                clean_text(payload.get("page_url")) or None,
                user_agent,
                trace.get("dataset_version") or clean_text(payload.get("dataset_version")) or None,
                trace.get("classifier_version")
                or clean_text(payload.get("classifier_version"))
                or None,
                trace.get("classifier_decision")
                or clean_text(payload.get("classifier_decision"))
                or None,
                trace.get("classifier_probability")
                or clean_text(payload.get("classifier_probability"))
                or None,
            ),
        )
        report = dict(cursor.fetchone())
        cursor.execute(
            """
            INSERT INTO user_feedback_events (
                report_id,
                event_type,
                actor,
                to_status,
                notes
            )
            VALUES (%s, 'report.submitted', 'public_user', %s, %s)
            """,
            (report["report_id"], report["status"], detail[:1000]),
        )
    return feedback_payload(report)


def list_feedback_reports(
    connection: Any,
    *,
    status: str | None = None,
    report_type: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    page = max(1, int(page))
    page_size = min(100, max(1, int(page_size)))
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status not in FEEDBACK_STATUSES:
            raise APIError("invalid_status", "Unsupported feedback status.", status=400)
        clauses.append("status = %s")
        params.append(status)
    if report_type:
        if report_type not in FEEDBACK_TYPES:
            raise APIError("invalid_feedback_type", "Unsupported feedback type.", status=400)
        clauses.append("report_type = %s")
        params.append(report_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * page_size
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"""
            SELECT *, count(*) OVER () AS total
            FROM user_feedback_reports
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            [*params, page_size, offset],
        )
        rows = [dict(row) for row in cursor.fetchall()]
    total = int(rows[0].get("total") or 0) if rows else 0
    for row in rows:
        row.pop("total", None)
    return {
        "records": [feedback_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def feedback_hard_training_examples(connection: Any) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT f.*, p.title, p.abstract, p.keywords
            FROM user_feedback_reports f
            LEFT JOIN final_publications p USING (publication_key)
            WHERE f.report_type = 'incorrect_ai_classification'
              AND f.status IN ('resolved', 'in_review', 'open')
            ORDER BY f.created_at DESC
            """
        )
        rows = [dict(row) for row in cursor.fetchall()]
    return [
        {
            "publication_key": row.get("publication_key"),
            "title": row.get("title"),
            "abstract": row.get("abstract"),
            "keywords": row.get("keywords"),
            "reported_classifier_decision": row.get("classifier_decision"),
            "reported_classifier_probability": row.get("classifier_probability"),
            "feedback_detail": row.get("detail"),
            "feedback_status": row.get("status"),
            "label_source": "public_feedback",
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def publication_trace(connection: Any, publication_key: str) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT dataset_version,
                   classifier_version,
                   classifier_decision,
                   classifier_probability
            FROM public_eligible_publications
            WHERE publication_key = %s
            """,
            (publication_key,),
        )
        row = cursor.fetchone()
    if row is None:
        raise APIError("not_found", "Publication not found.", status=404)
    return dict(row)


def feedback_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "report_id": row.get("report_id"),
        "publication_key": row.get("publication_key"),
        "report_type": row.get("report_type"),
        "status": row.get("status"),
        "title": row.get("title"),
        "detail": row.get("detail"),
        "reporter_name": row.get("reporter_name"),
        "reporter_email": row.get("reporter_email"),
        "page_url": row.get("page_url"),
        "dataset_version": row.get("dataset_version"),
        "classifier_version": row.get("classifier_version"),
        "classifier_decision": row.get("classifier_decision"),
        "classifier_probability": row.get("classifier_probability"),
        "hard_training_example": row.get("hard_training_example"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "resolved_at": row.get("resolved_at"),
        "resolved_by": row.get("resolved_by"),
        "resolution_note": row.get("resolution_note"),
    }


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def with_connection(callback: Any) -> Any:
    connection = get_connection()
    try:
        result = callback(connection)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
