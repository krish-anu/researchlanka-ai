"""CLI wrapper for :mod:`src.database.check_database_connection`."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.check_database_connection import *  # noqa: F401,F403
from src.database.check_database_connection import main


if __name__ == "__main__":
    main()
