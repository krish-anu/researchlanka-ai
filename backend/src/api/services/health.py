"""Health and readiness checks for the public API."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from src.api.core.constants import API_VERSION
from src.database.connection import get_connection


def health_payload() -> dict[str, Any]:
    """Liveness check: process is serving requests."""

    return {
        "status": "healthy",
        "api_version": API_VERSION,
    }


def readiness_payload() -> dict[str, Any]:
    """Readiness check: process can query the public corpus metadata."""

    try:
        connection = get_connection()
        try:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT count(*) AS public_publications,
                           max(dataset_version) AS dataset_version,
                           max(classifier_version) AS model_version,
                           max(pipeline_version) AS pipeline_version
                    FROM public_eligible_publications
                    """
                )
                row = dict(cursor.fetchone() or {})
            database = "healthy"
            status = "healthy"
        finally:
            connection.close()
    except Exception as exc:
        row = {}
        database = "unhealthy"
        status = "unhealthy"
        row["error"] = str(exc)

    return {
        "status": status,
        "database": database,
        "api_version": API_VERSION,
        "dataset_version": row.get("dataset_version"),
        "model_version": row.get("model_version"),
        "pipeline_version": row.get("pipeline_version"),
        "public_publications": int(row.get("public_publications") or 0),
        **({"error": row["error"]} if row.get("error") else {}),
    }
