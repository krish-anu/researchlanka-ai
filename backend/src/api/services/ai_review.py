"""Durable AI classification review workflow."""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Mapping

from psycopg.rows import dict_row

from src.api.core.errors import APIError
from src.database.connection import get_connection


ACCEPTED_STATUSES = {"auto_accepted", "human_accepted"}
COMPLETED_STATUSES = {"auto_accepted", "human_accepted", "human_rejected"}
MISSING_VALUE = ""
FORMULA_PREFIXES = ("=", "+", "-", "@")
MAX_SHEETS_CELL_CHARS = 50_000

FINAL_DATASET_COLUMNS = [
    "record_id",
    "source_dataset",
    "source_record_id",
    "openalex_id",
    "doi",
    "title",
    "abstract",
    "keywords",
    "authors",
    "author_affiliations",
    "affiliation_countries",
    "sri_lanka_eligibility_evidence",
    "publication_year",
    "publication_date",
    "publication_type",
    "journal_or_repository",
    "publisher",
    "volume",
    "issue",
    "page_range_or_article_number",
    "canonical_url",
    "language",
    "open_access_status",
    "license",
    "original_data_source",
    "retrieval_timestamp",
    "final_ai_decision",
    "acceptance_method",
    "decision_timestamp",
]


@dataclass(frozen=True)
class Reviewer:
    id: str
    email: str
    name: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_ai_label(value: Any) -> str:
    text = str(value or "").strip().casefold()
    compact = text.replace("_", " ").replace("-", " ")
    if compact in {"ai", "artificial intelligence", "ai related", "yes", "true", "1"}:
        return "AI"
    if compact in {"non ai", "nonai", "not ai", "not related", "no", "false", "0"}:
        return "NON_AI"
    if compact in {"review", "needs review", "uncertain", "unknown", ""}:
        return "REVIEW"
    return "UNRECOGNIZED"


def normalize_confidence(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if not text:
        return None
    if text in {"high", "h"}:
        return "HIGH"
    if text in {"medium", "med", "m"}:
        return "MEDIUM"
    if text in {"low", "l"}:
        return "LOW"
    return "UNRECOGNIZED"


def initial_review_status(label: Any, confidence: Any) -> tuple[str, str | None]:
    normalized_label = normalize_ai_label(label)
    normalized_confidence = normalize_confidence(confidence)
    if normalized_label == "AI" and normalized_confidence == "HIGH":
        return "auto_accepted", "auto"
    return "pending_review", None


def parse_reviewers(value: str | None = None) -> list[Reviewer]:
    raw = value if value is not None else os.getenv("AI_REVIEWER_ACCOUNTS", "")
    reviewers: list[Reviewer] = []
    for chunk in raw.split(","):
        parts = [part.strip() for part in chunk.split("|")]
        if not parts or not parts[0]:
            continue
        email = parts[0].lower()
        reviewers.append(
            Reviewer(
                id=parts[1] if len(parts) > 1 and parts[1] else email,
                email=email,
                name=parts[2] if len(parts) > 2 and parts[2] else email,
            )
        )
    return reviewers


def ensure_reviewers(reviewers: Iterable[Reviewer]) -> list[Reviewer]:
    prepared = list(reviewers)
    if not prepared:
        raise APIError(
            "reviewers_not_configured",
            "AI_REVIEWER_ACCOUNTS must list the three existing admin reviewer accounts.",
            status=503,
        )
    if len({item.email for item in prepared}) != len(prepared):
        raise APIError("duplicate_reviewers", "Configured reviewer emails must be unique.", status=400)
    return sorted(prepared, key=lambda item: (item.email, item.id))


def backfill_review_records(connection: Any) -> dict[str, int]:
    """Create missing review records from existing Gemini classification columns."""

    rows = _fetch_all(
        connection,
        """
        SELECT publication_key, ai_classification_label, ai_classification_confidence,
               ai_classification_model, ai_classification_reason
        FROM final_publications
        ORDER BY publication_key
        """,
    )
    created = 0
    auto = 0
    pending = 0
    with connection.cursor() as cursor:
        for row in rows:
            status, method = initial_review_status(
                row["ai_classification_label"],
                row["ai_classification_confidence"],
            )
            normalized_label = normalize_ai_label(row["ai_classification_label"])
            normalized_confidence = normalize_confidence(row["ai_classification_confidence"])
            cursor.execute(
                """
                INSERT INTO ai_review_records (
                    publication_key,
                    original_ai_label,
                    original_ai_confidence,
                    original_ai_model,
                    original_ai_reason,
                    normalized_ai_label,
                    normalized_ai_confidence,
                    review_status,
                    acceptance_method,
                    decision_timestamp,
                    sync_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s = 'auto_accepted' THEN now() ELSE NULL END,
                        CASE WHEN %s = 'auto_accepted' THEN 'pending' ELSE 'not_queued' END)
                ON CONFLICT (publication_key) DO NOTHING
                """,
                (
                    row["publication_key"],
                    row["ai_classification_label"],
                    row["ai_classification_confidence"],
                    row["ai_classification_model"],
                    row["ai_classification_reason"],
                    normalized_label,
                    normalized_confidence,
                    status,
                    method,
                    status,
                    status,
                ),
            )
            if cursor.rowcount:
                created += 1
                if status == "auto_accepted":
                    auto += 1
                    _enqueue_sync_job(cursor, row["publication_key"], 1, "auto-backfill")
                else:
                    pending += 1
    return {"created": created, "auto_accepted": auto, "pending_review": pending}


def assign_initial_pending(connection: Any, reviewers: Iterable[Reviewer]) -> dict[str, Any]:
    prepared = ensure_reviewers(reviewers)
    existing = _fetch_all(
        connection,
        """
        SELECT assigned_reviewer_email AS email, count(*) AS count
        FROM ai_review_records
        WHERE review_status = 'pending_review'
          AND assigned_reviewer_email IS NOT NULL
        GROUP BY assigned_reviewer_email
        """,
    )
    counts = {reviewer.email: 0 for reviewer in prepared}
    preserved_unknown = {}
    for row in existing:
        email = row["email"]
        if email in counts:
            counts[email] = int(row["count"] or 0)
        else:
            preserved_unknown[email] = int(row["count"] or 0)

    pending = _fetch_all(
        connection,
        """
        SELECT publication_key
        FROM ai_review_records
        WHERE review_status = 'pending_review'
          AND assigned_reviewer_email IS NULL
        ORDER BY publication_key
        """,
    )
    assigned = 0
    with connection.cursor() as cursor:
        for row in pending:
            reviewer = min(prepared, key=lambda item: (counts[item.email], item.email))
            cursor.execute(
                """
                UPDATE ai_review_records
                SET assigned_reviewer_id = %s,
                    assigned_reviewer_email = %s,
                    assigned_reviewer_name = %s,
                    assigned_at = now(),
                    updated_at = now()
                WHERE publication_key = %s
                  AND review_status = 'pending_review'
                  AND assigned_reviewer_email IS NULL
                """,
                (reviewer.id, reviewer.email, reviewer.name, row["publication_key"]),
            )
            if cursor.rowcount:
                assigned += 1
                counts[reviewer.email] += 1
                _insert_event(
                    cursor,
                    publication_key=row["publication_key"],
                    event_type="assigned",
                    actor=None,
                    to_reviewer=reviewer,
                    idempotency_key=f"assign:{row['publication_key']}:{reviewer.email}",
                )
    return {
        "assigned": assigned,
        "pending_counts": counts,
        "preserved_unknown_assignments": preserved_unknown,
        "imbalance": (max(counts.values()) - min(counts.values())) if counts else 0,
    }


def assign_future_pending(connection: Any, reviewers: Iterable[Reviewer]) -> dict[str, Any]:
    return assign_initial_pending(connection, reviewers)


def list_reviews(
    connection: Any,
    *,
    actor_email: str,
    all_reviews: bool,
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    confidence: str | None = None,
    reviewer: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []
    if not all_reviews:
        clauses.append("lower(r.assigned_reviewer_email) = lower(%s)")
        params.append(actor_email)
    if status:
        clauses.append("r.review_status = %s")
        params.append(status)
    if confidence:
        clauses.append("r.normalized_ai_confidence = %s")
        params.append(confidence)
    if reviewer:
        clauses.append("lower(r.assigned_reviewer_email) = lower(%s)")
        params.append(reviewer)
    if q:
        clauses.append("(p.title ILIKE %s OR p.abstract ILIKE %s OR p.doi ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    safe_page = max(int(page or 1), 1)
    safe_page_size = min(max(int(page_size or 25), 1), 100)
    total = _fetch_one(connection, f"SELECT count(*) AS count FROM ai_review_records r JOIN final_publications p USING (publication_key) {where}", params)["count"]
    rows = _fetch_all(
        connection,
        f"""
        SELECT r.*, p.title, p.abstract, p.keywords, p.authors, p.author_affiliations,
               p.institutions, p.sri_lankan_institutions, p.countries, p.publication_year,
               p.publication_date, p.type, p.journal, p.publisher, p.doi, p.url,
               p.openalex_id, p.source_dataset, p.source_record_id, p.source_datestamp,
               p.language, p.oa_status, p.license, p.volume, p.issue, p.first_page,
               p.last_page, p.article_number
        FROM ai_review_records r
        JOIN final_publications p USING (publication_key)
        {where}
        ORDER BY
          CASE r.review_status WHEN 'pending_review' THEN 0 ELSE 1 END,
          r.assigned_reviewer_email NULLS LAST,
          p.publication_year DESC NULLS LAST,
          r.publication_key
        LIMIT %s OFFSET %s
        """,
        [*params, safe_page_size, (safe_page - 1) * safe_page_size],
    )
    return {
        "data": [review_payload(row) for row in rows],
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total": int(total or 0),
            "total_pages": max((int(total or 0) + safe_page_size - 1) // safe_page_size, 1),
        },
        "stats": review_stats(connection),
    }


def review_stats(connection: Any) -> dict[str, Any]:
    statuses = _fetch_all(
        connection,
        """
        SELECT review_status, count(*) AS count
        FROM ai_review_records
        GROUP BY review_status
        """,
    )
    reviewers = _fetch_all(
        connection,
        """
        SELECT assigned_reviewer_email AS email,
               assigned_reviewer_name AS name,
               count(*) FILTER (WHERE review_status = 'pending_review') AS pending,
               count(*) FILTER (WHERE review_status <> 'pending_review') AS completed,
               count(*) AS total
        FROM ai_review_records
        WHERE assigned_reviewer_email IS NOT NULL
        GROUP BY assigned_reviewer_email, assigned_reviewer_name
        ORDER BY assigned_reviewer_email
        """,
    )
    failed = _fetch_one(
        connection,
        "SELECT count(*) AS count FROM ai_review_sync_jobs WHERE status = 'failed'",
    )
    return {
        "by_status": {row["review_status"]: int(row["count"] or 0) for row in statuses},
        "sync_failures": int((failed or {}).get("count") or 0),
        "reviewers": reviewers,
    }


def decide_review(
    connection: Any,
    *,
    publication_key: str,
    decision: str,
    notes: str,
    actor: Mapping[str, str],
    expected_version: int,
    allow_unassigned: bool = False,
) -> dict[str, Any]:
    decision = decision.strip()
    if decision not in {"human_accepted", "human_rejected"}:
        raise APIError("invalid_decision", "Decision must be human_accepted or human_rejected.", status=400)
    if decision == "human_rejected" and not notes.strip():
        raise APIError("reject_reason_required", "Rejecting a record requires reviewer notes.", status=400)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT * FROM ai_review_records WHERE publication_key = %s FOR UPDATE",
            (publication_key,),
        )
        record = cursor.fetchone()
        if record is None:
            raise APIError("not_found", "Review record not found.", status=404)
        if record["record_version"] != expected_version:
            raise APIError("stale_review", "This review was changed after the page loaded.", status=409)
        actor_email = str(actor.get("email") or "").lower()
        assigned_email = str(record.get("assigned_reviewer_email") or "").lower()
        if not allow_unassigned and assigned_email and actor_email != assigned_email:
            raise APIError("forbidden", "Only the assigned reviewer can decide this record.", status=403)
        if record["review_status"] != "pending_review":
            raise APIError("already_decided", "This review has already been completed.", status=409)

        next_version = int(record["record_version"]) + 1
        cursor.execute(
            """
            UPDATE ai_review_records
            SET review_status = %s,
                acceptance_method = CASE WHEN %s = 'human_accepted' THEN 'human' ELSE NULL END,
                decided_by_id = %s,
                decided_by_email = %s,
                decided_by_name = %s,
                reviewer_notes = %s,
                decision_timestamp = now(),
                record_version = %s,
                sync_status = 'pending',
                updated_at = now()
            WHERE publication_key = %s
            RETURNING *
            """,
            (
                decision,
                decision,
                actor.get("id"),
                actor.get("email"),
                actor.get("name"),
                notes.strip(),
                next_version,
                publication_key,
            ),
        )
        updated = cursor.fetchone()
        _insert_event(
            cursor,
            publication_key=publication_key,
            event_type="decision",
            actor=actor,
            from_status=record["review_status"],
            to_status=decision,
            notes=notes.strip(),
            record_version=next_version,
            idempotency_key=f"decision:{publication_key}:{next_version}",
        )
        _enqueue_sync_job(cursor, publication_key, next_version, f"decision:{publication_key}:{next_version}")
        return dict(updated)


def reopen_review(
    connection: Any,
    *,
    publication_key: str,
    actor: Mapping[str, str],
    notes: str,
) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT * FROM ai_review_records WHERE publication_key = %s FOR UPDATE", (publication_key,))
        record = cursor.fetchone()
        if record is None:
            raise APIError("not_found", "Review record not found.", status=404)
        next_version = int(record["record_version"]) + 1
        cursor.execute(
            """
            UPDATE ai_review_records
            SET review_status = 'pending_review',
                acceptance_method = NULL,
                decided_by_id = NULL,
                decided_by_email = NULL,
                decided_by_name = NULL,
                decision_timestamp = NULL,
                record_version = %s,
                sync_status = 'pending',
                updated_at = now()
            WHERE publication_key = %s
            RETURNING *
            """,
            (next_version, publication_key),
        )
        updated = cursor.fetchone()
        _insert_event(
            cursor,
            publication_key=publication_key,
            event_type="reopened",
            actor=actor,
            from_status=record["review_status"],
            to_status="pending_review",
            notes=notes,
            record_version=next_version,
            idempotency_key=f"reopen:{publication_key}:{next_version}",
        )
        _enqueue_sync_job(cursor, publication_key, next_version, f"reopen:{publication_key}:{next_version}")
        return dict(updated)


def reassign_review(
    connection: Any,
    *,
    publication_key: str,
    reviewer: Reviewer,
    actor: Mapping[str, str],
    notes: str = "",
) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT * FROM ai_review_records WHERE publication_key = %s FOR UPDATE", (publication_key,))
        record = cursor.fetchone()
        if record is None:
            raise APIError("not_found", "Review record not found.", status=404)
        next_version = int(record["record_version"]) + 1
        cursor.execute(
            """
            UPDATE ai_review_records
            SET assigned_reviewer_id = %s,
                assigned_reviewer_email = %s,
                assigned_reviewer_name = %s,
                assigned_at = now(),
                record_version = %s,
                updated_at = now()
            WHERE publication_key = %s
            RETURNING *
            """,
            (reviewer.id, reviewer.email, reviewer.name, next_version, publication_key),
        )
        updated = cursor.fetchone()
        _insert_event(
            cursor,
            publication_key=publication_key,
            event_type="reassigned",
            actor=actor,
            from_reviewer_email=record.get("assigned_reviewer_email"),
            to_reviewer=reviewer,
            notes=notes,
            record_version=next_version,
            idempotency_key=f"reassign:{publication_key}:{reviewer.email}:{next_version}",
        )
        return dict(updated)


def queue_retry(connection: Any, publication_key: str) -> dict[str, Any]:
    record = _fetch_one(
        connection,
        "SELECT record_version FROM ai_review_records WHERE publication_key = %s",
        [publication_key],
    )
    if record is None:
        raise APIError("not_found", "Review record not found.", status=404)
    with connection.cursor() as cursor:
        _enqueue_sync_job(cursor, publication_key, int(record["record_version"]), f"retry:{publication_key}:{record['record_version']}:{utc_now()}")
        cursor.execute(
            "UPDATE ai_review_records SET sync_status = 'pending', updated_at = now() WHERE publication_key = %s",
            (publication_key,),
        )
    return {"queued": True, "publication_key": publication_key}


def final_dataset_rows(connection: Any) -> list[dict[str, Any]]:
    rows = _fetch_all(
        connection,
        """
        SELECT p.*, r.review_status, r.acceptance_method, r.decision_timestamp
        FROM final_publications p
        JOIN ai_review_records r USING (publication_key)
        WHERE r.review_status IN ('auto_accepted', 'human_accepted')
        ORDER BY p.publication_key
        """,
    )
    return [final_dataset_row(row) for row in rows]


def final_dataset_row(row: Mapping[str, Any]) -> dict[str, str]:
    pages = page_range(row)
    return {
        "record_id": sheet_value(row.get("publication_key")),
        "source_dataset": sheet_value(row.get("source_dataset")),
        "source_record_id": sheet_value(row.get("source_record_id")),
        "openalex_id": sheet_value(row.get("openalex_id")),
        "doi": sheet_value(row.get("doi")),
        "title": sheet_value(row.get("title")),
        "abstract": sheet_value(row.get("abstract")),
        "keywords": sheet_value(row.get("keywords")),
        "authors": sheet_value(row.get("authors")),
        "author_affiliations": sheet_value(row.get("author_affiliations")),
        "affiliation_countries": sheet_value(row.get("countries")),
        "sri_lanka_eligibility_evidence": sheet_value(sri_lanka_evidence(row)),
        "publication_year": sheet_value(row.get("publication_year")),
        "publication_date": sheet_value(row.get("publication_date")),
        "publication_type": sheet_value(row.get("type")),
        "journal_or_repository": sheet_value(row.get("journal") or row.get("source_dataset")),
        "publisher": sheet_value(row.get("publisher")),
        "volume": sheet_value(row.get("volume")),
        "issue": sheet_value(row.get("issue")),
        "page_range_or_article_number": sheet_value(pages or row.get("article_number")),
        "canonical_url": sheet_value(row.get("url") or row.get("doi")),
        "language": sheet_value(row.get("language")),
        "open_access_status": sheet_value(row.get("oa_status")),
        "license": sheet_value(row.get("license")),
        "original_data_source": sheet_value(row.get("source_dataset")),
        "retrieval_timestamp": sheet_value(row.get("source_datestamp") or row.get("loaded_at")),
        "final_ai_decision": "AI",
        "acceptance_method": sheet_value(row.get("acceptance_method") or ("auto" if row.get("review_status") == "auto_accepted" else "human")),
        "decision_timestamp": sheet_value(row.get("decision_timestamp")),
    }


def review_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "publication_key": row["publication_key"],
        "record_version": row["record_version"],
        "review_status": row["review_status"],
        "acceptance_method": row.get("acceptance_method"),
        "assigned_reviewer": {
            "id": row.get("assigned_reviewer_id"),
            "email": row.get("assigned_reviewer_email"),
            "name": row.get("assigned_reviewer_name"),
        },
        "decided_by": {
            "id": row.get("decided_by_id"),
            "email": row.get("decided_by_email"),
            "name": row.get("decided_by_name"),
        },
        "reviewer_notes": row.get("reviewer_notes") or "",
        "decision_timestamp": row.get("decision_timestamp"),
        "sync_status": row.get("sync_status"),
        "sync_attempt_count": row.get("sync_attempt_count"),
        "last_sync_error": row.get("last_sync_error"),
        "last_synced_at": row.get("last_synced_at"),
        "gemini": {
            "label": row.get("original_ai_label"),
            "confidence": row.get("original_ai_confidence"),
            "normalized_label": row.get("normalized_ai_label"),
            "normalized_confidence": row.get("normalized_ai_confidence"),
            "model": row.get("original_ai_model"),
            "reason": row.get("original_ai_reason"),
        },
        "publication": {key: row.get(key) for key in (
            "title", "abstract", "keywords", "authors", "author_affiliations",
            "institutions", "sri_lankan_institutions", "countries", "publication_year",
            "publication_date", "type", "journal", "publisher", "doi", "url",
            "openalex_id", "source_dataset", "source_record_id", "source_datestamp",
            "language", "oa_status", "license", "volume", "issue", "first_page",
            "last_page", "article_number",
        )},
    }


def sheet_value(value: Any) -> str:
    if value is None:
        return MISSING_VALUE
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def overflow_chunks(record_id: str, field_name: str, value: str) -> list[dict[str, str]]:
    if len(value) <= MAX_SHEETS_CELL_CHARS:
        return []
    chunks = []
    for index in range(0, len(value), MAX_SHEETS_CELL_CHARS):
        chunks.append(
            {
                "record_id": record_id,
                "field_name": field_name,
                "chunk_number": str(index // MAX_SHEETS_CELL_CHARS + 1),
                "content": value[index : index + MAX_SHEETS_CELL_CHARS],
            }
        )
    return chunks


def write_csv_snapshot(connection: Any, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rows = final_dataset_rows(connection)
    final_path = output_dir / f"researchlanka_ai_final_dataset_{stamp}.csv"
    guide_path = output_dir / f"researchlanka_ai_dataset_guide_{stamp}.md"
    with final_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FINAL_DATASET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    guide_path.write_text(dataset_guide(connection, len(rows)), encoding="utf-8")
    return {"final_dataset": str(final_path), "dataset_guide": str(guide_path), "accepted_count": len(rows)}


def dataset_guide(connection: Any, accepted_count: int | None = None) -> str:
    stats = review_stats(connection)
    count = accepted_count
    if count is None:
        count = len(final_dataset_rows(connection))
    dictionary = "\n".join(f"- `{column}`: exported literal text; blank means unavailable in source data." for column in FINAL_DATASET_COLUMNS)
    return f"""# ResearchLanka AI Final Dataset Guide

Generated at: {utc_now()}

Scope: accepted AI-related publication records in `final_publications` after existing Sri Lanka eligibility loading rules.

Acceptance rules: explicit AI prediction with HIGH confidence is auto-accepted. All other confidence values, missing confidence, unrecognized confidence, and non-AI predictions require manual review. HIGH-confidence auto-accepted records have not necessarily undergone human review.

Missing values: blank cells indicate source metadata was unavailable. The export does not fabricate publication details.

Accepted record count: {count}

Status counts: {json.dumps(stats["by_status"], sort_keys=True)}

Data dictionary:
{dictionary}
"""


def validate_final_dataset(connection: Any) -> dict[str, Any]:
    rows = final_dataset_rows(connection)
    ids = [row["record_id"] for row in rows]
    missing_essential = [
        row["record_id"]
        for row in rows
        if not row.get("title") or (not row.get("doi") and not row.get("canonical_url"))
    ]
    return {
        "accepted_count": len(rows),
        "duplicate_record_ids": sorted({item for item in ids if ids.count(item) > 1}),
        "missing_essential_metadata": missing_essential,
        "ready": not missing_essential and len(ids) == len(set(ids)),
    }


def page_range(row: Mapping[str, Any]) -> str:
    first = str(row.get("first_page") or "").strip()
    last = str(row.get("last_page") or "").strip()
    if first and last:
        return f"{first}-{last}"
    return first or last


def sri_lanka_evidence(row: Mapping[str, Any]) -> str:
    evidence = []
    if row.get("sri_lankan_authors"):
        evidence.append(f"Sri Lankan authors: {row['sri_lankan_authors']}")
    if row.get("sri_lankan_institutions"):
        evidence.append(f"Sri Lankan institutions: {row['sri_lankan_institutions']}")
    if row.get("countries"):
        evidence.append(f"Countries: {row['countries']}")
    return "; ".join(evidence)


def _enqueue_sync_job(cursor: Any, publication_key: str, record_version: int, idempotency_key: str) -> None:
    cursor.execute(
        """
        INSERT INTO ai_review_sync_jobs (
            publication_key, target_record_version, idempotency_key
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (idempotency_key) DO NOTHING
        """,
        (publication_key, record_version, idempotency_key),
    )


def _insert_event(
    cursor: Any,
    *,
    publication_key: str,
    event_type: str,
    actor: Mapping[str, str] | None,
    from_status: str | None = None,
    to_status: str | None = None,
    from_reviewer_email: str | None = None,
    to_reviewer: Reviewer | None = None,
    notes: str = "",
    record_version: int | None = None,
    idempotency_key: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO ai_review_events (
            publication_key, event_type, actor_id, actor_email, actor_name,
            from_status, to_status, from_reviewer_email, to_reviewer_email,
            notes, record_version, idempotency_key
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (idempotency_key) DO NOTHING
        """,
        (
            publication_key,
            event_type,
            actor.get("id") if actor else None,
            actor.get("email") if actor else None,
            actor.get("name") if actor else None,
            from_status,
            to_status,
            from_reviewer_email,
            to_reviewer.email if to_reviewer else None,
            notes,
            record_version,
            idempotency_key,
        ),
    )


def _fetch_all(connection: Any, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params or [])
        return [dict(row) for row in cursor.fetchall()]


def _fetch_one(connection: Any, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
        return dict(row) if row else None


def with_connection(operation):
    connection = get_connection()
    try:
        result = operation(connection)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
