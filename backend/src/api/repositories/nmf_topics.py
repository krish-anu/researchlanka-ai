"""Load k=25 NMF topic-model artifacts for API serving."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from src.database.loader import build_publication_key
from src.modeling.nmf_trends import classify_trend, topic_trend_slopes, trend_time_series


BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_DIRS = (
    BACKEND_ROOT / "data/processed/common/nmf/k25",
    BACKEND_ROOT / "notebooks/outputs/NMF_K25/NMF_K25",
)

PUBLICATION_ASSIGNMENT_COLUMNS = (
    "doi",
    "openalex_id",
    "source_dataset",
    "source_record_id",
    "nmf_topic_id",
    "nmf_topic_name",
    "nmf_topic_weight",
)


def resolve_nmf_artifact_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"NMF artifact directory not found: {resolved}")
        return resolved

    env_path = os.environ.get("NMF_ARTIFACT_DIR")
    if env_path:
        resolved = Path(env_path).expanduser().resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"NMF artifact directory not found: {resolved}")
        return resolved

    for candidate in DEFAULT_ARTIFACT_DIRS:
        if candidate.is_dir() and (candidate / "nmf_topic_keywords.csv").exists():
            return candidate

    raise FileNotFoundError(
        "NMF artifact directory not found. Set NMF_ARTIFACT_DIR or place k=25 artifacts under "
        f"{DEFAULT_ARTIFACT_DIRS[0]}."
    )


def _publication_key_from_row(row: dict[str, Any], row_number: int) -> str:
    return build_publication_key(row, row_number)


class NmfTopicStore:
    """In-memory index over finalized k=25 NMF artifacts."""

    def __init__(self, artifact_dir: Path | str | None = None) -> None:
        self.artifact_dir = resolve_nmf_artifact_dir(artifact_dir)
        self.k = 25
        self._load()

    def _load(self) -> None:
        keywords_path = self.artifact_dir / "nmf_topic_keywords.csv"
        shares_path = self.artifact_dir / "nmf_topic_trend_shares.csv"
        counts_path = self.artifact_dir / "nmf_topic_trend_counts.csv"
        publications_path = self.artifact_dir / "nmf_publication_topics.csv"

        keywords_df = pd.read_csv(keywords_path)
        self.keywords_by_id = {
            int(row.topic_id): {
                "topic_id": int(row.topic_id),
                "topic_name": str(row.topic_name),
                "top_words": [word.strip() for word in str(row.top_words).split(",") if word.strip()],
            }
            for row in keywords_df.itertuples(index=False)
        }
        self.name_to_id = {
            record["topic_name"].casefold(): topic_id for topic_id, record in self.keywords_by_id.items()
        }

        self.trend_shares = pd.read_csv(shares_path, index_col=0)
        self.trend_shares.index = self.trend_shares.index.astype(int)
        self.trend_counts = pd.read_csv(counts_path, index_col=0)
        self.trend_counts.index = self.trend_counts.index.astype(int)

        slopes = topic_trend_slopes(self.trend_shares)
        classified = classify_trend(slopes)
        self.trend_by_name = {
            str(row.topic_name): row._asdict() for row in classified.itertuples(index=False)
        }

        assignments = pd.read_csv(publications_path, usecols=list(PUBLICATION_ASSIGNMENT_COLUMNS))
        self.publication_assignments: dict[str, dict[str, Any]] = {}
        self.keys_by_topic_id: dict[int, list[str]] = {topic_id: [] for topic_id in self.keywords_by_id}
        self.publication_count_by_topic_id: dict[int, int] = {
            topic_id: 0 for topic_id in self.keywords_by_id
        }

        for row_number, row in enumerate(assignments.itertuples(index=False), start=1):
            record = row._asdict()
            publication_key = _publication_key_from_row(record, row_number)
            topic_id = int(record["nmf_topic_id"])
            assignment = {
                "publication_key": publication_key,
                "nmf_topic_id": topic_id,
                "nmf_topic_name": str(record["nmf_topic_name"]),
                "nmf_topic_weight": float(record["nmf_topic_weight"]),
            }
            self.publication_assignments[publication_key] = assignment
            self.keys_by_topic_id.setdefault(topic_id, []).append(publication_key)
            self.publication_count_by_topic_id[topic_id] = (
                self.publication_count_by_topic_id.get(topic_id, 0) + 1
            )

    @property
    def topic_count(self) -> int:
        return len(self.keywords_by_id)

    @property
    def publication_count(self) -> int:
        return len(self.publication_assignments)

    def metadata(self) -> dict[str, Any]:
        return {
            "nmf_k": self.k,
            "nmf_artifact_dir": str(self.artifact_dir),
            "nmf_topic_count": self.topic_count,
            "nmf_publication_count": self.publication_count,
            "nmf_year_min": int(self.trend_shares.index.min()),
            "nmf_year_max": int(self.trend_shares.index.max()),
        }

    def get_topic(self, topic_id: int) -> dict[str, Any] | None:
        base = self.keywords_by_id.get(topic_id)
        if base is None:
            return None
        trend = self.trend_by_name.get(base["topic_name"], {})
        topic_name = base["topic_name"]
        return {
            **base,
            "publication_count": self.publication_count_by_topic_id.get(topic_id, 0),
            "trend": trend.get("trend", "stable"),
            "slope_per_year": trend.get("slope_per_year"),
            "p_value": trend.get("p_value"),
            "r_value": trend.get("r_value"),
            "mean_share": trend.get("mean_share"),
            "first_year_share": trend.get("first_year_share"),
            "last_year_share": trend.get("last_year_share"),
            "yearly_trends": trend_time_series(
                self.trend_counts,
                self.trend_shares,
                topic_names=[topic_name],
            ),
        }

    def list_topics(
        self,
        *,
        trend: str | None = None,
        sort: str = "topic_id",
    ) -> list[dict[str, Any]]:
        rows = [self.get_topic(topic_id) for topic_id in sorted(self.keywords_by_id)]
        rows = [row for row in rows if row is not None]
        if trend:
            rows = [row for row in rows if row.get("trend") == trend]
        if sort == "slope_desc":
            rows.sort(key=lambda row: float(row.get("slope_per_year") or 0.0), reverse=True)
        elif sort == "publications_desc":
            rows.sort(key=lambda row: int(row.get("publication_count") or 0), reverse=True)
        elif sort == "name_asc":
            rows.sort(key=lambda row: str(row.get("topic_name") or ""))
        else:
            rows.sort(key=lambda row: int(row.get("topic_id") or 0))
        return rows

    def resolve_topic_ids(
        self,
        *,
        topic_ids: list[int] | None = None,
        topic_names: list[str] | None = None,
    ) -> list[int]:
        resolved: list[int] = []
        if topic_ids:
            for topic_id in topic_ids:
                if topic_id in self.keywords_by_id:
                    resolved.append(topic_id)
        if topic_names:
            for topic_name in topic_names:
                topic_id = self.name_to_id.get(topic_name.casefold())
                if topic_id is not None:
                    resolved.append(topic_id)
        return sorted(set(resolved))

    def publication_keys_for_topics(self, topic_ids: list[int]) -> list[str]:
        keys: list[str] = []
        for topic_id in self.resolve_topic_ids(topic_ids=topic_ids):
            keys.extend(self.keys_by_topic_id.get(topic_id, []))
        return sorted(set(keys))

    def publication_keys_for_topic_names(self, topic_names: list[str]) -> list[str]:
        return self.publication_keys_for_topics(self.resolve_topic_ids(topic_names=topic_names))

    def assignment_for_publication(self, publication_key: str) -> dict[str, Any] | None:
        return self.publication_assignments.get(publication_key)

    def resolve_topic_key(self, topic_key: str) -> int | None:
        """Resolve a path/query topic key to an NMF topic id."""
        raw = topic_key.strip()
        if raw.lower().startswith("nmf:"):
            raw = raw.split(":", 1)[1].strip()
        if raw.isdigit():
            topic_id = int(raw)
            return topic_id if topic_id in self.keywords_by_id else None
        return self.name_to_id.get(raw.casefold())

    def ranking_entries(
        self,
        *,
        trend: str | None = None,
        sort: str = "publications_desc",
        topic_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.list_topics(trend=trend, sort=sort)
        if topic_ids:
            allowed = set(topic_ids)
            rows = [row for row in rows if row["topic_id"] in allowed]
        return [
            {
                "key": row["topic_name"],
                "label": row["topic_name"],
                "publication_count": row["publication_count"],
                "citation_total": 0,
                "topic_id": row["topic_id"],
                "source": "nmf",
                "trend": row.get("trend"),
                "top_words": row.get("top_words"),
                "slope_per_year": row.get("slope_per_year"),
                "p_value": row.get("p_value"),
                "mean_share": row.get("mean_share"),
            }
            for row in rows
        ]

    def topic_trends(
        self,
        *,
        topic_ids: list[int] | None = None,
        topic_names: list[str] | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> list[dict[str, object]]:
        selected_ids = self.resolve_topic_ids(topic_ids=topic_ids, topic_names=topic_names)
        selected_names = [self.keywords_by_id[topic_id]["topic_name"] for topic_id in selected_ids]
        if not selected_names:
            selected_names = list(self.trend_shares.columns)

        rows = trend_time_series(
            self.trend_counts,
            self.trend_shares,
            topic_names=selected_names,
            year_min=year_min,
            year_max=year_max,
        )
        for row in rows:
            topic_id = self.name_to_id.get(str(row["topic_name"]).casefold())
            row["topic_id"] = topic_id
        return rows


@lru_cache(maxsize=1)
def get_nmf_topic_store() -> NmfTopicStore:
    return NmfTopicStore()
