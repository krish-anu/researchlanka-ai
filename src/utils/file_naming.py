"""Helpers for project dataset file-naming conventions."""

from __future__ import annotations

import re
from pathlib import Path


VALID_DATASET_EXTENSIONS = {"csv", "json", "jsonl", "log", "txt"}
DATASET_FILENAME_RE = re.compile(
    r"^[a-z0-9]+(?:_[a-z0-9]+){2,}\.(?:csv|json|jsonl|log|txt)$"
)


def slug_segment(value: str) -> str:
    """Convert one logical name segment to lower snake case."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        raise ValueError("Filename segments must contain at least one letter or digit.")
    return slug


def dataset_filename(
    source: str,
    scope: str,
    entity: str,
    extension: str,
    *,
    variant: str | None = None,
) -> str:
    """Build a standardized dataset filename.

    Dataset files use:
        source_scope_entity[_variant].extension
    """
    extension = extension.lower().lstrip(".")
    if extension not in VALID_DATASET_EXTENSIONS:
        allowed = ", ".join(sorted(VALID_DATASET_EXTENSIONS))
        raise ValueError(f"Unsupported dataset extension '{extension}'. Use one of: {allowed}.")

    parts = [source, scope, entity]
    if variant:
        parts.append(variant)

    stem = "_".join(slug_segment(part) for part in parts)
    return f"{stem}.{extension}"


def is_dataset_filename(value: str | Path) -> bool:
    """Return True when the basename follows the dataset filename convention."""
    return DATASET_FILENAME_RE.fullmatch(Path(value).name) is not None
