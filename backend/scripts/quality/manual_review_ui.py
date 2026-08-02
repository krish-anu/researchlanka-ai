"""CLI wrapper for :mod:`src.quality.manual_review_ui`."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.quality.manual_review_ui import *  # noqa: F401,F403
from src.quality.manual_review_ui import main


if __name__ == "__main__":
    main()
