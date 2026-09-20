"""Database connection helpers."""

from __future__ import annotations

import os
import threading
from queue import Empty, Full, Queue
from typing import Any

from dotenv import load_dotenv

DEFAULT_DATABASE_URL = (
    "postgresql://researchlanka_user:change_me@localhost:5433/researchlanka"
)

# Cap concurrent DB connections used by the threaded HTTP API under Locust/load.
_DEFAULT_POOL_SIZE = 16
_pool_lock = threading.Lock()
_pools: dict[str, "SimpleConnectionPool"] = {}


def get_database_url(env_var: str = "DATABASE_URL") -> str:
    """Return the configured database URL from .env or the PostgreSQL default."""
    load_dotenv()
    return os.getenv(env_var, DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL


def get_connection(database_url: str | None = None) -> Any:
    """Create a PostgreSQL database connection for the configured URL."""
    if database_url is None and not os.getenv("DATABASE_URL") and os.getenv("DATABASE_HOST"):
        return _connect_postgres_params()

    url = (database_url or get_database_url()).strip()

    if url.startswith(("postgresql://", "postgres://")):
        return _connect_postgres(url)

    raise ValueError("Unsupported DATABASE_URL. Use postgresql:// or postgres://.")


def get_pooled_connection(database_url: str | None = None) -> Any:
    """Borrow a pooled connection; ``close()`` returns it to the pool.

    Used by the read-only API so threaded request handlers do not open one
    fresh Postgres connection per request (which exhausts ``max_connections``
    under Locust / concurrent load).
    """
    url = (database_url or get_database_url()).strip()
    pool = _get_pool(url)
    return pool.borrow()


def check_connection(connection: Any) -> bool:
    """Run a tiny query to confirm that the connection is usable."""
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    finally:
        cursor.close()
    return True


def _pool_size() -> int:
    raw = (os.getenv("RESEARCHLANKA_DB_POOL_SIZE") or "").strip()
    if raw.isdigit():
        return max(1, min(int(raw), 64))
    return _DEFAULT_POOL_SIZE


def _get_pool(database_url: str) -> "SimpleConnectionPool":
    with _pool_lock:
        pool = _pools.get(database_url)
        if pool is None:
            pool = SimpleConnectionPool(database_url, size=_pool_size())
            _pools[database_url] = pool
        return pool


class SimpleConnectionPool:
    """Small thread-safe pool of psycopg connections."""

    def __init__(self, database_url: str, *, size: int) -> None:
        self.database_url = database_url
        self.size = size
        self._available: Queue[Any] = Queue(maxsize=size)
        self._created = 0
        self._lock = threading.Lock()

    def borrow(self) -> "_PooledConnection":
        try:
            conn = self._available.get_nowait()
        except Empty:
            conn = None

        if conn is not None:
            if self._connection_is_alive(conn):
                return _PooledConnection(self, conn)
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._created = max(0, self._created - 1)

        with self._lock:
            if self._created < self.size:
                self._created += 1
                create = True
            else:
                create = False

        if create:
            try:
                return _PooledConnection(self, _connect_postgres(self.database_url))
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise

        # Wait for a free connection rather than opening past the pool cap.
        conn = self._available.get(timeout=30)
        if not self._connection_is_alive(conn):
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._created = max(0, self._created - 1)
            return self.borrow()
        return _PooledConnection(self, conn)

    def release(self, conn: Any) -> None:
        if conn is None:
            return
        if not self._connection_is_alive(conn):
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._created = max(0, self._created - 1)
            return
        try:
            # Clear any aborted transaction so the next borrower starts clean.
            conn.rollback()
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._created = max(0, self._created - 1)
            return
        try:
            self._available.put_nowait(conn)
        except Full:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._created = max(0, self._created - 1)

    @staticmethod
    def _connection_is_alive(conn: Any) -> bool:
        try:
            if getattr(conn, "closed", False):
                return False
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return True
        except Exception:  # noqa: BLE001
            return False


class _PooledConnection:
    """Proxy whose ``close()`` returns the underlying connection to the pool."""

    def __init__(self, pool: SimpleConnectionPool, conn: Any) -> None:
        self._pool = pool
        self._conn = conn
        self._released = False

    def close(self) -> None:
        if self._released:
            return
        self._released = True
        self._pool.release(self._conn)

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


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
