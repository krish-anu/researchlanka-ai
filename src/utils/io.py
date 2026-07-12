"""Shared I/O utilities for printing and formatting."""

import json
from typing import Any


def print_json(title: str, value: Any) -> None:
    """Print a JSON value with a title header."""
    print(f"\n## {title}")
    print(json.dumps(value, indent=2, ensure_ascii=False))
