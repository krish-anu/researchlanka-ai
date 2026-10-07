"""Finalize a dedicated CSE site database after loading its accepted AI CSV."""

from __future__ import annotations

from typing import Any


def prepare_site_database(connection: Any) -> dict[str, int]:
    """Publish already-resolved CSE AI records and restore their year field.

    The operation refuses mixed databases. The national review workflow must
    never be bypassed by this dedicated-site preparation step.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                count(*) AS total,
                count(*) FILTER (
                    WHERE upper(coalesce(raw_record->>'cse_affiliation_verified', '')) = 'TRUE'
                ) AS verified
            FROM final_publications
            """
        )
        total, verified = (int(value or 0) for value in cursor.fetchone())
        if total == 0:
            raise ValueError("The target database contains no publications.")
        if verified != total:
            raise ValueError(
                "Refusing to prepare a mixed/non-CSE database: "
                f"{verified} of {total} records contain verified CSE provenance."
            )

        cursor.execute(
            """
            UPDATE final_publications
            SET publication_year = (raw_record->>'publication_year')::integer
            WHERE publication_year IS NULL
              AND coalesce(raw_record->>'publication_year', '') ~ '^[0-9]{4}$'
            """
        )
        restored_years = cursor.rowcount

        cursor.execute(
            """
            UPDATE ai_review_records r
            SET review_status = CASE
                    WHEN p.raw_record->>'final_resolution_source' = 'finished_human_review'
                    THEN 'human_accepted'
                    ELSE 'auto_accepted'
                END,
                acceptance_method = CASE
                    WHEN p.raw_record->>'final_resolution_source' = 'finished_human_review'
                    THEN 'human'
                    ELSE 'auto'
                END,
                reviewer_notes = 'accepted_from_cse_uom_final_binary_resolved_ai_dataset',
                decision_timestamp = coalesce(r.decision_timestamp, now()),
                sync_status = 'not_queued',
                updated_at = now(),
                record_version = r.record_version + 1
            FROM final_publications p
            WHERE p.publication_key = r.publication_key
              AND upper(coalesce(p.ai_classification_label, '')) = 'AI'
              AND upper(coalesce(p.raw_record->>'cse_affiliation_verified', '')) = 'TRUE'
            """
        )
        accepted = cursor.rowcount

        cursor.execute("SELECT count(*) FROM public_eligible_publications")
        public_records = int(cursor.fetchone()[0])

    connection.commit()
    return {
        "database_records": total,
        "restored_years": restored_years,
        "accepted_records": accepted,
        "public_records": public_records,
    }
