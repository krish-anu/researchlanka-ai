"""Phase 2 — live Postgres soak vs real CSV baseline (T-03).

Requires a reachable DATABASE_URL (gitignored .env). Compares:
  - connectivity / latency
  - final_publications row count vs common_publications_final.csv baseline
  - DOI overlap sample between DB and CSV
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import pytest

from tests.support.env_loader import BACKEND_ROOT, env_str, load_test_env
from tests.support.real_dataset import dataset_path


pytestmark = [pytest.mark.phase2, pytest.mark.database_integrity, pytest.mark.live]


def _database_url() -> str | None:
    load_test_env()
    return env_str("DATABASE_URL", "RESEARCHLANKA_DATABASE_URL")


def _csv_baseline_count() -> int:
    path = dataset_path()
    # Fast line count (header excluded) without loading the full frame.
    with path.open("rb") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


@pytest.fixture(scope="module")
def db_connection():
    """Connect to live Postgres for soak gates.

    - No DATABASE_URL → skip (not configured on this machine)
    - URL set but unreachable → fail (integrity gate must not look like a soft skip)
    - Connected with empty final_publications → individual tests fail (population)
    """
    url = _database_url()
    if not url:
        pytest.skip("Set DATABASE_URL in .env for live Postgres soak (T-03)")
    try:
        import psycopg
    except ImportError:
        pytest.fail("psycopg not installed — required for DB integrity soak")
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Postgres unreachable for soak (DATABASE_URL is set). "
            f"Start Docker DB or fix connectivity — do not treat as skip. ({exc})"
        )
    yield conn
    conn.close()


def test_postgres_connects_and_ping_is_fast(db_connection):
    started = time.perf_counter()
    with db_connection.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    # Soft soak budget for a local/staging ping.
    assert elapsed_ms < 2000.0, f"ping too slow: {elapsed_ms:.1f}ms"


def test_final_publications_table_exists(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'final_publications'
            """
        )
        assert cur.fetchone() is not None, "final_publications table missing"


def test_db_row_count_within_tolerance_of_csv_baseline(db_connection):
    csv_count = _csv_baseline_count()
    assert csv_count > 1000, f"CSV baseline unexpectedly small: {csv_count}"

    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM final_publications")
        db_count = int(cur.fetchone()[0])

    # Empty table is an integrity FAILURE (not skip): ask data owner to load CSV.
    assert db_count > 0, (
        "final_publications is empty — load data before soak sign-off "
        "(population/integrity failure, not a skipped test)"
    )
    ratio = db_count / csv_count
    assert 0.5 <= ratio <= 1.5, (
        f"DB count {db_count} vs CSV baseline {csv_count} (ratio={ratio:.3f}) "
        "outside 50%–150% soak tolerance"
    )


def test_db_doi_sample_overlaps_csv(db_connection):
    path = dataset_path()
    csv_dois = {
        str(v).strip().lower()
        for v in pd.read_csv(path, usecols=["doi"], nrows=500)["doi"].dropna().tolist()
        if str(v).strip()
    }
    assert csv_dois, "CSV sample has no DOIs"

    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT lower(trim(doi))
            FROM final_publications
            WHERE doi IS NOT NULL AND btrim(doi) <> ''
            LIMIT 500
            """
        )
        db_dois = {row[0] for row in cur.fetchall() if row[0]}

    if not db_dois:
        pytest.fail("No DOIs found in final_publications sample")

    overlap = csv_dois & db_dois
    # At least a few shared DOIs when both sides have data; if DB is a different
    # snapshot, still require non-zero overlap for the soak gate.
    assert len(overlap) >= 1, (
        f"No DOI overlap between CSV sample ({len(csv_dois)}) and DB sample ({len(db_dois)})"
    )


def test_hot_read_query_latency_budget(db_connection):
    started = time.perf_counter()
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT publication_key, title, publication_year
            FROM final_publications
            ORDER BY publication_year DESC NULLS LAST
            LIMIT 25
            """
        )
        rows = cur.fetchall()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert rows, "hot read returned no rows"
    assert elapsed_ms < 5000.0, f"hot read too slow: {elapsed_ms:.1f}ms"
