#!/usr/bin/env python3
"""Prepare a dedicated CSE database after loading the final accepted AI CSV."""

from __future__ import annotations

import argparse
import json
import os

from src.cse_uom.site_database import prepare_site_database
from src.database.connection import get_connection


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize publication years and accepted statuses in a dedicated CSE database."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("CSE_UOM_DATABASE_URL"),
        help="Dedicated CSE PostgreSQL URL. Defaults to CSE_UOM_DATABASE_URL.",
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("Set CSE_UOM_DATABASE_URL or pass --database-url.")

    connection = get_connection(args.database_url)
    try:
        summary = prepare_site_database(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
