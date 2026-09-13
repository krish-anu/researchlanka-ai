"""Persistent pipeline state stored in PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.database.connection import get_connection
from src.database.loader import ensure_database_schema


DEFAULT_INCREMENTAL_STATE_KEY = "openalex_incremental"


@dataclass(frozen=True)
class PipelineCheckpoint:
    last_successful_collection_date: date | None
    source: str


@dataclass(frozen=True)
class PipelineRunRecord:
    run_id: str
    state_key: str
    from_date: date
    to_date: date
    status: str
    records_collected: int
    records_selected_for_db: int
    records_loaded: int
    raw_output: Path
    csv_output: Path
    db_load_output: Path
    model_path: Path | None
    db_labels: tuple[str, ...]
    error: str | None = None
    finished_at: datetime | None = None


def read_pipeline_checkpoint(
    *,
    database_url: str | None = None,
    state_key: str = DEFAULT_INCREMENTAL_STATE_KEY,
    derive_from_final_publications: bool = True,
) -> PipelineCheckpoint:
    """Read the last successful incremental collection date from PostgreSQL."""

    connection = get_connection(database_url)
    try:
        ensure_database_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT last_successful_collection_date
                FROM pipeline_state
                WHERE state_key = %s
                """,
                (state_key,),
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                return PipelineCheckpoint(row[0], "pipeline_state")

            if derive_from_final_publications:
                cursor.execute(
                    """
                    SELECT max(publication_date)
                    FROM final_publications
                    WHERE publication_date IS NOT NULL
                    """
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return PipelineCheckpoint(row[0], "final_publications")

        return PipelineCheckpoint(None, "empty_database")
    finally:
        connection.close()


def record_successful_pipeline_run(
    *,
    run: PipelineRunRecord,
    database_url: str | None = None,
) -> None:
    """Record a completed run and advance the durable incremental checkpoint."""

    if run.status != "succeeded":
        raise ValueError("Only succeeded runs can advance pipeline_state.")

    connection = get_connection(database_url)
    try:
        ensure_database_schema(connection)
        with connection.cursor() as cursor:
            _insert_pipeline_run(cursor, run)
            cursor.execute(
                """
                INSERT INTO pipeline_state (
                    state_key,
                    last_successful_collection_date,
                    last_successful_run_id,
                    last_successful_run_at,
                    last_from_date,
                    last_records_collected,
                    last_records_selected_for_db,
                    last_records_loaded,
                    last_raw_output,
                    last_csv_output,
                    last_db_load_output,
                    last_model_path,
                    last_db_labels,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
                )
                ON CONFLICT (state_key) DO UPDATE SET
                    last_successful_collection_date = EXCLUDED.last_successful_collection_date,
                    last_successful_run_id = EXCLUDED.last_successful_run_id,
                    last_successful_run_at = EXCLUDED.last_successful_run_at,
                    last_from_date = EXCLUDED.last_from_date,
                    last_records_collected = EXCLUDED.last_records_collected,
                    last_records_selected_for_db = EXCLUDED.last_records_selected_for_db,
                    last_records_loaded = EXCLUDED.last_records_loaded,
                    last_raw_output = EXCLUDED.last_raw_output,
                    last_csv_output = EXCLUDED.last_csv_output,
                    last_db_load_output = EXCLUDED.last_db_load_output,
                    last_model_path = EXCLUDED.last_model_path,
                    last_db_labels = EXCLUDED.last_db_labels,
                    updated_at = now()
                WHERE pipeline_state.last_successful_collection_date IS NULL
                   OR EXCLUDED.last_successful_collection_date
                        >= pipeline_state.last_successful_collection_date
                """,
                (
                    run.state_key,
                    run.to_date,
                    run.run_id,
                    run.from_date,
                    run.records_collected,
                    run.records_selected_for_db,
                    run.records_loaded,
                    str(run.raw_output),
                    str(run.csv_output),
                    str(run.db_load_output),
                    str(run.model_path) if run.model_path else None,
                    list(run.db_labels),
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def record_failed_pipeline_run(
    *,
    run: PipelineRunRecord,
    database_url: str | None = None,
) -> None:
    """Record a failed run without advancing the durable checkpoint."""

    if run.status != "failed":
        raise ValueError("Failed run records must use status='failed'.")

    connection = get_connection(database_url)
    try:
        ensure_database_schema(connection)
        with connection.cursor() as cursor:
            _insert_pipeline_run(cursor, run)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _insert_pipeline_run(cursor: Any, run: PipelineRunRecord) -> None:
    cursor.execute(
        """
        INSERT INTO incremental_pipeline_runs (
            run_id,
            state_key,
            from_date,
            to_date,
            status,
            finished_at,
            records_collected,
            records_selected_for_db,
            records_loaded,
            raw_output,
            csv_output,
            db_load_output,
            model_path,
            db_labels,
            error
        )
        VALUES (
            %s, %s, %s, %s, %s, COALESCE(%s, now()), %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            finished_at = EXCLUDED.finished_at,
            records_collected = EXCLUDED.records_collected,
            records_selected_for_db = EXCLUDED.records_selected_for_db,
            records_loaded = EXCLUDED.records_loaded,
            raw_output = EXCLUDED.raw_output,
            csv_output = EXCLUDED.csv_output,
            db_load_output = EXCLUDED.db_load_output,
            model_path = EXCLUDED.model_path,
            db_labels = EXCLUDED.db_labels,
            error = EXCLUDED.error
        """,
        (
            run.run_id,
            run.state_key,
            run.from_date,
            run.to_date,
            run.status,
            run.finished_at,
            run.records_collected,
            run.records_selected_for_db,
            run.records_loaded,
            str(run.raw_output),
            str(run.csv_output),
            str(run.db_load_output),
            str(run.model_path) if run.model_path else None,
            list(run.db_labels),
            run.error,
        ),
    )
