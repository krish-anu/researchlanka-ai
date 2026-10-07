"""Load department-tagging artifacts for API serving.

The artifacts come from :mod:`src.pipeline.build_department_tags`: one row per
tagged publication and department author, plus a JSON summary. Rows are keyed
by the same ``publication_key`` the database loader computes; DOI and OpenAlex
aliases are indexed as well so a row whose key was canonicalised differently
on load is still found.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_DIR = BACKEND_ROOT / "data/processed/common/departments"
PUBLICATION_AUTHORS_FILENAME = "department_publication_authors.csv"
SUMMARY_FILENAME = "department_tagging_summary.json"


def resolve_department_artifact_dir(path: Path | str | None = None) -> Path:
    candidate = path or os.environ.get("DEPARTMENT_ARTIFACT_DIR") or DEFAULT_ARTIFACT_DIR
    resolved = Path(candidate).expanduser().resolve()
    if not (resolved / SUMMARY_FILENAME).exists():
        raise FileNotFoundError(
            f"Department artifacts not found in {resolved}. Run `make department-tags` "
            "or set DEPARTMENT_ARTIFACT_DIR."
        )
    return resolved


def researcher_identity(name: str) -> str:
    return " ".join(str(name).split()).casefold()


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class DepartmentStore:
    """In-memory index over department-tagging artifacts."""

    def __init__(self, artifact_dir: Path | str | None = None) -> None:
        self.artifact_dir = resolve_department_artifact_dir(artifact_dir)
        self._load()

    def _load(self) -> None:
        summary = json.loads((self.artifact_dir / SUMMARY_FILENAME).read_text(encoding="utf-8"))
        self.generated_at: str | None = summary.get("generated_at")
        self.departments: dict[str, dict[str, Any]] = {
            str(entry["department_id"]).casefold(): entry for entry in summary.get("departments", [])
        }
        self.assignments: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in self.departments}
        self.aliases: dict[str, dict[str, str]] = {key: {} for key in self.departments}

        rows_path = self.artifact_dir / PUBLICATION_AUTHORS_FILENAME
        rows = (
            pd.read_csv(rows_path, dtype=str, keep_default_na=False)
            if rows_path.exists()
            else pd.DataFrame()
        )
        for record in rows.to_dict("records"):
            department_key = str(record.get("department_id", "")).casefold()
            if department_key not in self.departments:
                continue
            publication_key = record["publication_key"]
            assignment = self.assignments[department_key].setdefault(
                publication_key,
                {
                    "publication_key": publication_key,
                    "match": record.get("publication_match") or "explicit",
                    "authors": [],
                    "evidence": None,
                },
            )
            author = {
                "author_id": _clean(record.get("author_id")),
                "name": _clean(record.get("author_name")) or "",
                "match": record.get("author_match") or "explicit",
                "evidence": _clean(record.get("evidence")),
                "department_works": _int(record.get("author_department_works")),
                "other_unit_works": _int(record.get("author_other_unit_works")),
            }
            assignment["authors"].append(author)

            aliases = self.aliases[department_key]
            for alias in (
                publication_key,
                f"doi:{record['doi']}" if _clean(record.get("doi")) else None,
                f"openalex:{record['openalex_id']}" if _clean(record.get("openalex_id")) else None,
            ):
                if alias:
                    aliases.setdefault(alias, publication_key)

        for assignments in self.assignments.values():
            for assignment in assignments.values():
                authors = assignment["authors"]
                assignment["evidence"] = next(
                    (author["evidence"] for author in authors if author["match"] == "explicit" and author["evidence"]),
                    authors[0]["evidence"],
                )

    def resolve(self, department_key: str) -> dict[str, Any] | None:
        return self.departments.get(department_key.strip().casefold())

    def list_departments(self) -> list[dict[str, Any]]:
        return [self.describe(entry) for entry in self.departments.values()]

    def describe(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            key: entry.get(key)
            for key in (
                "department_id",
                "name",
                "short_name",
                "institution_id",
                "institution_name",
                "faculty",
                "url",
            )
        } | {"tagged_publication_count": len(self.assignments[entry["department_id"].casefold()])}

    def candidate_keys(
        self,
        department_id: str,
        *,
        match: str | None = None,
        researcher: str | None = None,
    ) -> list[str]:
        """Database keys that may hold the department's publications, filtered."""
        department_key = department_id.casefold()
        selected = {
            publication_key
            for publication_key, assignment in self.assignments[department_key].items()
            if (match is None or assignment["match"] == match)
            and (researcher is None or self._has_researcher(assignment, researcher))
        }
        return sorted(alias for alias, canonical in self.aliases[department_key].items() if canonical in selected)

    def assignment_for(self, department_id: str, publication_key: str) -> dict[str, Any] | None:
        department_key = department_id.casefold()
        canonical = self.aliases[department_key].get(publication_key)
        return self.assignments[department_key].get(canonical) if canonical else None

    @staticmethod
    def _has_researcher(assignment: dict[str, Any], researcher: str) -> bool:
        wanted = researcher_identity(researcher)
        return any(
            author["author_id"] == researcher or researcher_identity(author["name"]) == wanted
            for author in assignment["authors"]
        )


@lru_cache(maxsize=1)
def get_department_store() -> DepartmentStore:
    return DepartmentStore()
