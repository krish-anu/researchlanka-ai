"""Version identifiers for public dataset lineage."""

from __future__ import annotations

import os
from datetime import UTC, datetime


DEFAULT_PIPELINE_VERSION = "pipeline-v1.4.2"


def current_dataset_version() -> str:
    return os.getenv(
        "RESEARCHLANKA_DATASET_VERSION",
        f"researchlanka-{datetime.now(UTC).date().isoformat()}",
    )


def current_pipeline_version() -> str:
    return os.getenv("RESEARCHLANKA_PIPELINE_VERSION", DEFAULT_PIPELINE_VERSION)
