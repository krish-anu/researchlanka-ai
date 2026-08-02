"""Check that the configured database connection is reachable."""

import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import check_connection, get_connection, get_database_url


def main() -> None:
    database_url = get_database_url()
    try:
        connection = get_connection(database_url)
    except Exception as exc:
        safe_url = _hide_password(database_url)
        raise SystemExit(
            "Database connection failed.\n"
            f"URL: {safe_url}\n"
            "Make sure PostgreSQL is running, then try again:\n"
            "  docker compose up -d db\n"
            "  python scripts/database/check_database_connection.py\n"
            f"Error: {exc}"
        ) from exc

    try:
        check_connection(connection)
    finally:
        connection.close()

    print(f"Database connection OK: {_hide_password(database_url)}")


def _hide_password(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if not parsed.password:
        return database_url

    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    username = parsed.username or ""
    netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


if __name__ == "__main__":
    main()
