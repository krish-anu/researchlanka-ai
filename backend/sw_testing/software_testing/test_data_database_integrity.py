"""Master Test Plan 3.1.1 — live / sample integrity checks only.

Core DOI/title/schema unit tests live in:
    tests/data_integrity/test_database_integrity.py

Run those with:
    pytest tests/data_integrity -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.database.final_schema import DATABASE_PUBLICATION_COLUMNS


pytestmark = [pytest.mark.sw_testing]


def test_processed_csv_sample_years_are_plausible(sample_publications):
    years = []
    for row in sample_publications:
        try:
            years.append(int(row["publication_year"]))
        except (TypeError, ValueError, KeyError):
            continue
    assert years
    assert all(1950 <= y <= 2100 for y in years)


def test_live_database_row_count_matches_csv_baseline_when_configured(
    database_url: str | None, csv_path: Path
):
    if not database_url:
        pytest.skip("DATABASE_URL not configured on this machine")
    try:
        import psycopg
    except ImportError:
        pytest.fail("psycopg required when DATABASE_URL is set")
    with csv_path.open("rb") as handle:
        csv_count = max(sum(1 for _ in handle) - 1, 0)
    try:
        conn = psycopg.connect(database_url, connect_timeout=5)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Postgres unreachable with DATABASE_URL set: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM final_publications")
            db_count = int(cur.fetchone()[0])
        assert db_count > 0, (
            "final_publications is EMPTY — population integrity failure "
            "(ask data owner to load processed CSV; not a skip)"
        )
        ratio = db_count / csv_count
        assert 0.5 <= ratio <= 1.5, (
            f"DB count {db_count} vs CSV {csv_count} outside 50%–150% tolerance"
        )
    finally:
        conn.close()


def test_ai_classification_columns_exist_on_database_contract():
    assert any(name.startswith("ai_classification") for name in DATABASE_PUBLICATION_COLUMNS)
