"""Database connection helpers."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

DEFAULT_DATABASE_URL = (
    "postgresql://researchlanka_user:change_me@localhost:5433/researchlanka"
)


def get_database_url(env_var: str = "DATABASE_URL") -> str:
    """Return the configured database URL from .env or the PostgreSQL default."""
    load_dotenv()
    return os.getenv(env_var, DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL


def get_connection(database_url: str | None = None) -> Any:
    """Create a PostgreSQL database connection for the configured URL."""
    url = (database_url or get_database_url()).strip()

    if url.startswith(("postgresql://", "postgres://")):
        return _connect_postgres(url)

    raise ValueError("Unsupported DATABASE_URL. Use postgresql:// or postgres://.")


def check_connection(connection: Any) -> bool:
    """Run a tiny query to confirm that the connection is usable."""
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    finally:
        cursor.close()
    return True


def _connect_postgres(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL connections require psycopg. Install project "
            "dependencies with pip install -r requirements.txt."
        ) from exc

    return psycopg.connect(database_url)
