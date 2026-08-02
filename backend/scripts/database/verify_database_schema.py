"""CLI wrapper for :mod:`src.database.verify_database_schema`."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.verify_database_schema import *  # noqa: F401,F403
from src.database.verify_database_schema import main


if __name__ == "__main__":
    main()
