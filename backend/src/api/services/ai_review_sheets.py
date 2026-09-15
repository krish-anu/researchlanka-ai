"""Google Sheets export and durable sync jobs for AI review decisions."""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from src.api.services.ai_review import (
    FINAL_DATASET_COLUMNS,
    dataset_guide,
    final_dataset_rows,
    overflow_chunks,
    review_payload,
    sheet_value,
)


WORKSHEETS = ["Final Dataset", "Review Audit", "Dataset Guide", "Overflow"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsNotConfigured(RuntimeError):
    pass


def configured_spreadsheet_id() -> str:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise SheetsNotConfigured("GOOGLE_SHEETS_SPREADSHEET_ID is not configured.")
    return spreadsheet_id


def build_sheets_service() -> Any:
    credentials_path = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "").strip()
    if not credentials_path:
        raise SheetsNotConfigured("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE is not configured.")
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SheetsNotConfigured(
            "Google Sheets sync requires google-api-python-client and google-auth."
        ) from exc

    credentials = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False).spreadsheets()


def reconcile_sheet(connection: Any, *, service: Any | None = None, spreadsheet_id: str | None = None) -> dict[str, Any]:
    service = service or build_sheets_service()
    spreadsheet_id = spreadsheet_id or configured_spreadsheet_id()
    ensure_worksheets(service, spreadsheet_id)

    final_rows = final_dataset_rows(connection)
    overflow_rows: list[dict[str, str]] = []
    safe_final_rows = []
    for row in final_rows:
        safe_row = dict(row)
        for field in ("abstract", "keywords", "author_affiliations"):
            chunks = overflow_chunks(row["record_id"], field, row.get(field, ""))
            if chunks:
                overflow_rows.extend(chunks)
                safe_row[field] = f"[See Overflow worksheet: {field}]"
        safe_final_rows.append(safe_row)

    write_values(
        service,
        spreadsheet_id,
        "Final Dataset",
        [FINAL_DATASET_COLUMNS, *[[row.get(column, "") for column in FINAL_DATASET_COLUMNS] for row in safe_final_rows]],
    )
    write_values(
        service,
        spreadsheet_id,
        "Review Audit",
        review_audit_values(connection),
    )
    write_values(
        service,
        spreadsheet_id,
        "Dataset Guide",
        [["ResearchLanka AI Dataset Guide"], *[[line] for line in dataset_guide(connection, len(final_rows)).splitlines()]],
    )
    write_values(
        service,
        spreadsheet_id,
        "Overflow",
        [["record_id", "field_name", "chunk_number", "content"], *[
            [row["record_id"], row["field_name"], row["chunk_number"], row["content"]]
            for row in overflow_rows
        ]],
    )
    mark_current_records_synced(connection)
    return {
        "final_rows": len(final_rows),
        "audit_rows": len(review_audit_values(connection)) - 1,
        "overflow_rows": len(overflow_rows),
    }


def run_sync_worker_once(connection: Any, *, service: Any | None = None, spreadsheet_id: str | None = None, limit: int = 10) -> dict[str, Any]:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    jobs = claim_jobs(connection, worker_id, limit=limit)
    if not jobs:
        return {"claimed": 0, "succeeded": 0, "failed": 0}
    succeeded = 0
    failed = 0
    for job in jobs:
        try:
            reconcile_sheet(connection, service=service, spreadsheet_id=spreadsheet_id)
        except Exception as exc:
            failed += 1
            mark_job_failed(connection, job, str(exc))
        else:
            succeeded += 1
            mark_job_succeeded(connection, job)
    return {"claimed": len(jobs), "succeeded": succeeded, "failed": failed}


def claim_jobs(connection: Any, worker_id: str, *, limit: int) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT job_id
            FROM ai_review_sync_jobs
            WHERE status IN ('pending', 'failed')
              AND next_attempt_at <= now()
            ORDER BY created_at, job_id
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (limit,),
        )
        job_ids = [row["job_id"] for row in cursor.fetchall()]
        if not job_ids:
            return []
        cursor.execute(
            """
            UPDATE ai_review_sync_jobs
            SET status = 'running',
                locked_at = now(),
                locked_by = %s,
                attempts = attempts + 1,
                updated_at = now()
            WHERE job_id = ANY(%s)
            RETURNING *
            """,
            (worker_id, job_ids),
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_job_succeeded(connection: Any, job: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ai_review_sync_jobs
            SET status = 'succeeded',
                locked_at = NULL,
                locked_by = NULL,
                last_error = NULL,
                updated_at = now()
            WHERE job_id = %s
            """,
            (job["job_id"],),
        )


def mark_job_failed(connection: Any, job: dict[str, Any], error: str) -> None:
    attempts = int(job.get("attempts") or 1)
    delay = min(60 * (2 ** max(attempts - 1, 0)), 3600)
    next_attempt = datetime.now(UTC) + timedelta(seconds=delay)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ai_review_sync_jobs
            SET status = 'failed',
                locked_at = NULL,
                locked_by = NULL,
                last_error = %s,
                next_attempt_at = %s,
                updated_at = now()
            WHERE job_id = %s
            """,
            (error[:2000], next_attempt, job["job_id"]),
        )
        cursor.execute(
            """
            UPDATE ai_review_records
            SET sync_status = 'failed',
                sync_attempt_count = sync_attempt_count + 1,
                last_sync_error = %s,
                updated_at = now()
            WHERE publication_key = %s
            """,
            (error[:2000], job["publication_key"]),
        )


def mark_current_records_synced(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ai_review_records
            SET sync_status = 'succeeded',
                last_sync_error = NULL,
                last_synced_at = now(),
                sync_attempt_count = sync_attempt_count + 1,
                updated_at = now()
            WHERE sync_status IN ('pending', 'failed')
            """
        )


def ensure_worksheets(service: Any, spreadsheet_id: str) -> None:
    meta = service.get(spreadsheetId=spreadsheet_id).execute()
    existing = {
        sheet.get("properties", {}).get("title")
        for sheet in meta.get("sheets", [])
    }
    requests = [
        {"addSheet": {"properties": {"title": title}}}
        for title in WORKSHEETS
        if title not in existing
    ]
    if requests:
        service.batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()


def write_values(service: Any, spreadsheet_id: str, worksheet: str, values: list[list[Any]]) -> None:
    safe_values = [[sheet_value(cell) for cell in row] for row in values]
    service.values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"'{worksheet}'!A:ZZ",
        body={},
    ).execute()
    service.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{worksheet}'!A1",
        valueInputOption="RAW",
        body={"values": safe_values},
    ).execute()


def review_audit_values(connection: Any) -> list[list[str]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT r.*, p.title
            FROM ai_review_records r
            JOIN final_publications p USING (publication_key)
            ORDER BY r.publication_key
            """
        )
        records = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT *
            FROM ai_review_events
            ORDER BY created_at, event_id
            """
        )
        events = [dict(row) for row in cursor.fetchall()]
    header = [
        "event_id",
        "record_id",
        "event_type",
        "original_gemini_prediction",
        "original_gemini_confidence",
        "original_gemini_reasoning",
        "final_review_status",
        "acceptance_method",
        "reviewer_identifier",
        "reviewer_display_name",
        "reviewer_notes",
        "assigned_reviewer",
        "decision_timestamp",
        "sync_timestamp",
        "event_timestamp",
    ]
    record_by_id = {row["publication_key"]: row for row in records}
    values = [header]
    for event in events:
        record = record_by_id.get(event["publication_key"], {})
        values.append(
            [
                str(event["event_id"]),
                event["publication_key"],
                event["event_type"],
                record.get("original_ai_label") or "",
                record.get("original_ai_confidence") or "",
                record.get("original_ai_reason") or "",
                record.get("review_status") or "",
                record.get("acceptance_method") or "",
                record.get("decided_by_email") or "",
                record.get("decided_by_name") or "",
                record.get("reviewer_notes") or "",
                record.get("assigned_reviewer_email") or "",
                str(record.get("decision_timestamp") or ""),
                str(record.get("last_synced_at") or ""),
                str(event.get("created_at") or ""),
            ]
        )
    return values
