"""CLI wrapper for :mod:`src.pipeline.add_repository_records_to_final`."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.add_repository_records_to_final import *  # noqa: F401,F403
from src.pipeline.add_repository_records_to_final import main


if __name__ == "__main__":
    main()
