"""Real publication rows for Phase 2/3 API tests (no handmade dummy corpus)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from src.database.loader import build_publication_key
from tests.support.env_loader import BACKEND_ROOT, env_str, load_test_env


DEFAULT_DATASET = (
    BACKEND_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final.csv"
)


def dataset_path() -> Path:
    load_test_env()
    configured = env_str("RESEARCHLANKA_TEST_DATASET_PATH")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path
    return DEFAULT_DATASET


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            return value
    return value


def _row_to_publication(row: dict[str, Any], row_number: int) -> dict[str, Any]:
    cleaned = {key: _clean_cell(value) for key, value in row.items()}
    year = cleaned.get("publication_year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None
    doi = cleaned.get("doi")
    key = build_publication_key(
        {
            "doi": doi,
            "openalex_id": cleaned.get("openalex_id"),
            "source_dataset": cleaned.get("source_dataset"),
            "source_record_id": cleaned.get("source_record_id"),
            "title": cleaned.get("title"),
            "publication_year": year,
        },
        row_number,
    )
    return {
        "publication_key": key,
        "title": cleaned.get("title"),
        "doi": doi,
        "publication_year": year,
        "type": cleaned.get("type"),
        "authors": cleaned.get("authors"),
        "institutions": cleaned.get("institutions"),
        "sri_lankan_institutions": cleaned.get("sri_lankan_institutions"),
        "countries": cleaned.get("countries"),
        "journal": cleaned.get("journal"),
        "publisher": cleaned.get("publisher"),
        "citation_count": cleaned.get("citation_count") or 0,
        "reference_count": cleaned.get("reference_count"),
        "is_oa": cleaned.get("is_oa"),
        "oa_status": cleaned.get("oa_status"),
        "primary_field": cleaned.get("primary_field"),
        "primary_subfield": cleaned.get("primary_subfield"),
        "topics": cleaned.get("topics"),
        "concepts": cleaned.get("concepts"),
        "source_dataset": cleaned.get("source_dataset"),
        "source_record_id": cleaned.get("source_record_id"),
        "abstract": cleaned.get("abstract"),
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": False,
        "raw_record": {},
        "ai_classification_label": cleaned.get("ai_classification_label"),
        "ai_classification_confidence": cleaned.get("ai_classification_confidence"),
    }


@lru_cache(maxsize=2)
def load_real_publications(limit: int = 64) -> tuple[dict[str, Any], ...]:
    """Load a slice of the real common final dataset for in-process API tests."""

    path = dataset_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Real dataset missing at {path}. Set RESEARCHLANKA_TEST_DATASET_PATH "
            "or place common_publications_final.csv under data/processed/common/."
        )
    frame = pd.read_csv(path, nrows=max(limit, 8))
    rows = [
        _row_to_publication(record, index + 1)
        for index, record in enumerate(frame.to_dict(orient="records"))
    ]
    # Prefer rows that have a title so list/search assertions stay meaningful.
    titled = [row for row in rows if row.get("title")]
    selected = titled or rows
    if len(selected) < 2:
        raise RuntimeError(f"Need at least 2 real publication rows from {path}")
    return tuple(selected[:limit])


class RealPublicationRepository:
    """In-memory repository backed by real common-dataset rows (not dummy fixtures)."""

    fail_list = False
    fail_health = False

    def __init__(self, publications: list[dict[str, Any]] | None = None) -> None:
        self.publications = list(publications or load_real_publications())

    def health(self):
        if self.fail_health:
            raise RuntimeError("database unreachable")
        return True

    def metadata(self):
        years = [row["publication_year"] for row in self.publications if row.get("publication_year")]
        return {
            "publication_count": len(self.publications),
            "min_publication_year": min(years) if years else None,
            "max_publication_year": max(years) if years else None,
            "snapshot_date": "real-dataset",
        }

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        if self.fail_list:
            raise RuntimeError("connection refused: postgresql://user:secret@db:5432/app")
        rows = list(self.publications)
        if filters.get("year_min"):
            rows = [row for row in rows if (row.get("publication_year") or 0) >= filters["year_min"]]
        if filters.get("year_max"):
            rows = [row for row in rows if (row.get("publication_year") or 9999) <= filters["year_max"]]
        if filters.get("q"):
            needle = str(filters["q"]).casefold()
            rows = [row for row in rows if needle in (row.get("title") or "").casefold()]
        if filters.get("publication_keys") is not None:
            keys = set(filters["publication_keys"])
            rows = [row for row in rows if row["publication_key"] in keys]
        start = (page - 1) * page_size
        year_facets = {}
        for row in self.publications:
            year = row.get("publication_year")
            if year is not None:
                year_facets[str(year)] = year_facets.get(str(year), 0) + 1
        facets = {"publication_year": year_facets} if include_facets else None
        return {
            "records": rows[start : start + page_size],
            "total": len(rows),
            "facets": facets,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key):
        return next(
            (row for row in self.publications if row["publication_key"] == publication_key),
            None,
        )

    def get_references(self, publication_key):
        return [
            {
                "publication_key": publication_key,
                "reference_index": 1,
                "reference_title": "Ref",
            }
        ]

    def get_count_audit(self, publication_key):
        row = self.get_publication(publication_key)
        if row is None:
            return None
        return {
            "publication_key": publication_key,
            "citation_count": row.get("citation_count") or 0,
        }

    def suggest(self, query, *, limit, types=None):
        needle = (query or "").casefold()
        hits = [
            {
                "type": "publication",
                "value": row["title"],
                "key": row["publication_key"],
            }
            for row in self.publications
            if row.get("title") and needle in str(row["title"]).casefold()
        ]
        if not hits and self.publications:
            hits = [
                {
                    "type": "publication",
                    "value": self.publications[0]["title"],
                    "key": self.publications[0]["publication_key"],
                }
            ]
        return hits[:limit]

    def semantic_search(self, query, *, filters, limit, min_score):
        row = {
            **self.publications[0],
            "semantic_score": 0.925,
            "semantic_rank": 1,
            "similarity_score": 0.925,
            "similarity_rank": 1,
        }
        return [row][:limit]

    def related_publications(self, publication_key, *, filters, limit, min_score):
        if publication_key == "missing":
            raise KeyError(publication_key)
        other = next(
            (row for row in self.publications if row["publication_key"] != publication_key),
            self.publications[0],
        )
        row = {
            **other,
            "semantic_score": 0.81,
            "semantic_rank": 1,
            "similarity_score": 0.81,
            "similarity_rank": 1,
        }
        return [row][:limit]

    def researcher_profile(self, researcher_key):
        if researcher_key == "missing":
            return None
        return {"key": researcher_key, "label": researcher_key, "publication_count": 1}

    def researcher_publications(self, researcher_key, *, page, page_size):
        return {"records": [self.publications[0]], "total": 1}

    def researcher_coauthors(self, researcher_key, *, limit):
        authors = (self.publications[0].get("authors") or "Coauthor").split(";")
        name = authors[-1].strip() if authors else "Coauthor"
        return [{"name": name or "Coauthor", "publication_count": 1}][:limit]

    def institution_profile(self, institution_key):
        if institution_key == "missing":
            return None
        return {"key": institution_key, "label": institution_key, "publication_count": 1}

    def institution_publications(self, institution_key, *, page, page_size):
        return {"records": [self.publications[0]], "total": 1}

    def institution_collaborators(self, institution_key, *, limit):
        return [{"name": "Collaborating Institution", "publication_count": 1}][:limit]

    def compare_institutions(self, keys):
        return [{"key": key, "publication_count": max(1, len(self.publications) // max(len(keys), 1))} for key in keys]

    def topic_publications(self, topic_key, *, page, page_size):
        return {"records": [self.publications[0]], "total": 1}

    def analytics_overview(self, filters):
        citations = sum(int(row.get("citation_count") or 0) for row in self.publications)
        return {
            "publication_count": len(self.publications),
            "citation_total": citations,
        }

    def analytics_trends(self, filters, *, group_by, metric):
        years: dict[int, int] = {}
        for row in self.publications:
            year = row.get("publication_year")
            if year is None:
                continue
            years[int(year)] = years.get(int(year), 0) + 1
        return [
            {"key": year, "publication_count": count, "citation_total": count}
            for year, count in sorted(years.items())
        ] or [{"key": 2020, "publication_count": len(self.publications), "citation_total": 0}]

    def paginated_analytics_rankings(self, filters, *, dimension, metric, page, page_size):
        records = [
            {
                "key": "real-dataset",
                "label": dimension,
                "publication_count": len(self.publications),
                "citation_total": sum(int(row.get("citation_count") or 0) for row in self.publications),
            }
        ]
        start = (page - 1) * page_size
        return {"records": records[start : start + page_size], "total": len(records)}

    def analytics_rankings(self, filters, *, dimension, metric, limit):
        return self.paginated_analytics_rankings(
            filters, dimension=dimension, metric=metric, page=1, page_size=limit
        )["records"]

    def rankings(self, *, dimension, metric, filters, limit):
        return self.analytics_rankings(filters, dimension=dimension, metric=metric, limit=limit)

    def collaboration_network(self, filters, *, scope=None, min_weight=None, limit=None, limit_nodes=None, limit_edges=None):
        return {
            "nodes": [{"id": "real-1", "label": "Real Institution"}],
            "edges": [],
            "summary": {"node_count": 1, "edge_count": 0},
            "meta": {"node_count": 1, "edge_count": 0},
        }

    def timeseries(self, filters, *, group_by):
        return {"data": self.analytics_trends(filters, group_by=group_by, metric="publications")}

    def data_quality(self, filters, *, group_by):
        missing_doi = sum(1 for row in self.publications if not row.get("doi"))
        total = len(self.publications) or 1
        return {
            "record_count": len(self.publications),
            "missing_doi_percentage": round(missing_doi / total * 100.0, 2),
        }
