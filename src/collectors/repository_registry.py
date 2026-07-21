"""Loader for the Sri Lankan academic repository target inventory.

The inventory itself lives in ``data/config/repositories.json`` and is
hand-curated (see the project's repository-target research deliverable).
This module only knows how to read and filter it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "config" / "repositories.json"

# Statuses that mean "no live OAI endpoint to harvest right now".
# Includes both by-design exclusions (no repository, pilot platform, ...)
# and statuses assigned after live validation (scripts/validate_repositories.py)
# found the endpoint unreachable or blocked -- see data/config/repositories.json
# notes on each entry for specifics and re-check dates.
NON_HARVESTABLE_STATUSES = {
    "no_repository_found",
    "no_own_repository",
    "skip",
    "pilot_do_not_harvest",
    "unreachable",
    "blocked_for_automated_requests",
}


@dataclass
class RepositoryTarget:
    """A single institution/platform entry from the repository inventory."""

    id: str
    name: str
    group: str
    status: str
    phase: str
    repository_url: str | None = None
    software: str | None = None
    oai_endpoint: str | None = None
    rest_api_endpoint: str | None = None
    on_dspace_ac_lk: bool = False
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_harvestable(self) -> bool:
        """Whether this target has an OAI endpoint worth harvesting."""

        return bool(self.oai_endpoint) and self.status not in NON_HARVESTABLE_STATUSES

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepositoryTarget":
        known_fields = {
            "id",
            "name",
            "group",
            "status",
            "phase",
            "repository_url",
            "software",
            "oai_endpoint",
            "rest_api_endpoint",
            "on_dspace_ac_lk",
            "notes",
        }
        extra = {key: value for key, value in data.items() if key not in known_fields}
        return cls(
            id=data["id"],
            name=data["name"],
            group=data["group"],
            status=data["status"],
            phase=data.get("phase", "not_applicable"),
            repository_url=data.get("repository_url"),
            software=data.get("software"),
            oai_endpoint=data.get("oai_endpoint"),
            rest_api_endpoint=data.get("rest_api_endpoint"),
            on_dspace_ac_lk=bool(data.get("on_dspace_ac_lk", False)),
            notes=data.get("notes"),
            extra=extra,
        )


def load_registry(path: Path | str = DEFAULT_REGISTRY_PATH) -> list[RepositoryTarget]:
    """Load all repository targets from the inventory file."""

    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [RepositoryTarget.from_dict(entry) for entry in data["repositories"]]


def harvestable_targets(
    targets: list[RepositoryTarget] | None = None,
    *,
    phase: str | None = None,
) -> list[RepositoryTarget]:
    """Return targets that have an OAI endpoint worth validating/harvesting.

    Args:
        targets: Pre-loaded targets, or ``None`` to load the default registry.
        phase: Optional phase filter, e.g. ``"phase_1"``.
    """

    if targets is None:
        targets = load_registry()

    return [
        target
        for target in targets
        if target.is_harvestable and (phase is None or target.phase == phase)
    ]


def get_target(target_id: str, targets: list[RepositoryTarget] | None = None) -> RepositoryTarget:
    """Look up a single target by its ``id``."""

    if targets is None:
        targets = load_registry()

    for target in targets:
        if target.id == target_id:
            return target

    raise KeyError(f"No repository target with id={target_id!r}")
