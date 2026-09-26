"""Database connection helpers."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

DEFAULT_DATABASE_URL = (
    "postgresql://researchlanka_user:change_me@localhost:5433/researchlanka"
)
_POOL: Any | None = None


def get_database_url(env_var: str = "DATABASE_URL") -> str:
    """Return the configured database URL from .env or the PostgreSQL default."""
    load_dotenv()
    return os.getenv(env_var, DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL


def get_connection(database_url: str | None = None) -> Any:
    """Create a PostgreSQL database connection for the configured URL."""
    if database_url is None and not os.getenv("DATABASE_URL") and os.getenv("DATABASE_HOST"):
        return _connect_postgres_params()

    if pool_enabled() and database_url is None:
        return get_pooled_connection()

    url = (database_url or get_database_url()).strip()

    if url.startswith(("postgresql://", "postgres://")):
        return _connect_postgres(url)

    raise ValueError("Unsupported DATABASE_URL. Use postgresql:// or postgres://.")


def pool_enabled() -> bool:
    return os.getenv("RESEARCHLANKA_DB_POOL_ENABLED", "1").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }


def get_pooled_connection() -> Any:
    global _POOL
    if _POOL is None:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError:
            return _connect_postgres(get_database_url())
        _POOL = ConnectionPool(
            conninfo=get_database_url(),
            min_size=int(os.getenv("RESEARCHLANKA_DB_POOL_MIN_SIZE", "1")),
            max_size=int(os.getenv("RESEARCHLANKA_DB_POOL_MAX_SIZE", "10")),
            timeout=float(os.getenv("RESEARCHLANKA_DB_POOL_TIMEOUT_SECONDS", "5")),
            open=True,
        )
    return _PooledConnection(_POOL)


class _PooledConnection:
    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self._connection = pool.getconn()
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def close(self) -> None:
        if not self._closed:
            self._pool.putconn(self._connection)
            self._closed = True

    def __enter__(self) -> Any:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


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


def _connect_postgres_params() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL connections require psycopg. Install project "
            "dependencies with pip install -r requirements.txt."
        ) from exc

    return psycopg.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "researchlanka"),
        user=os.getenv("POSTGRES_USER", "researchlanka_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
