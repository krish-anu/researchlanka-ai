"""Load ResearchLanka test secrets/URLs from .env without hardcoding them."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

_LOADED = False


def load_test_env() -> None:
    """Load repo-root and backend .env files once (secrets stay out of git)."""

    global _LOADED
    if _LOADED:
        return
    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(BACKEND_ROOT / ".env", override=False)
    load_dotenv(REPO_ROOT / "frontend" / ".env", override=False)
    _LOADED = True


def env_flag(name: str, default: bool = False) -> bool:
    load_test_env()
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_str(*names: str, default: str | None = None) -> str | None:
    load_test_env()
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return default
