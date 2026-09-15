"""Shared helpers for Phase 3 overall application tests."""

from __future__ import annotations

from typing import Any

import pytest

from src.api.service import ResearchLankaAPI


PUBLICATIONS = [
    {
        "publication_key": "doi:10.1000/test",
        "title": "Malaria surveillance in Sri Lanka",
        "doi": "10.1000/test",
        "publication_year": 2024,
        "type": "journal-article",
        "authors": "A. Author; B. Author",
        "institutions": "University of Colombo; University of Peradeniya",
        "sri_lankan_institutions": "University of Colombo",
        "countries": "LK; GB",
        "journal": "Ceylon Medical Journal",
        "publisher": "Example Publisher",
        "citation_count": 12,
        "reference_count": 30,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Medicine",
        "primary_subfield": "Public Health",
        "topics": "Epidemiology; Malaria",
        "concepts": "public health",
        "source_dataset": "openalex; crossref",
        "source_record_id": "W1",
        "abstract": "A study abstract.",
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": True,
        "raw_record": {"id": "W1", "secret_token": "should-not-leak"},
        "ai_classification_label": "AI",
        "ai_classification_confidence": 0.91,
    },
    {
        "publication_key": "source:repositories_combined:thesis-1",
        "title": "Repository-only thesis",
        "doi": None,
        "publication_year": 2023,
        "type": "thesis",
        "authors": "C. Author",
        "institutions": "University of Ruhuna",
        "sri_lankan_institutions": "University of Ruhuna",
        "countries": "LK",
        "journal": None,
        "publisher": "University of Ruhuna",
        "citation_count": 0,
        "reference_count": None,
        "is_oa": None,
        "oa_status": None,
        "primary_field": None,
        "primary_subfield": None,
        "topics": None,
        "concepts": None,
        "source_dataset": "repositories_combined",
        "source_record_id": "thesis-1",
        "abstract": None,
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": False,
        "raw_record": {},
        "ai_classification_label": "AI",
        "ai_classification_confidence": 0.4,
    },
]


class FakeRepository:
    """In-memory repository for offline Phase 3 service tests."""

    fail_list = False
    fail_health = False

    def health(self):
        if self.fail_health:
            raise RuntimeError("database unreachable")
        return True

    def metadata(self):
        return {"publication_count": len(PUBLICATIONS), "snapshot_date": "2026-07-20"}

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        if self.fail_list:
            raise RuntimeError("connection refused: postgresql://user:secret@db:5432/app")
        rows = list(PUBLICATIONS)
        if filters.get("year_min"):
            rows = [row for row in rows if row["publication_year"] >= filters["year_min"]]
        if filters.get("year_max"):
            rows = [row for row in rows if row["publication_year"] <= filters["year_max"]]
        if filters.get("q"):
            needle = str(filters["q"]).casefold()
            rows = [row for row in rows if needle in (row["title"] or "").casefold()]
        if filters.get("publication_keys") is not None:
            keys = set(filters["publication_keys"])
            rows = [row for row in rows if row["publication_key"] in keys]
        start = (page - 1) * page_size
        facets = {"publication_year": {"2024": 1, "2023": 1}} if include_facets else None
        return {
            "records": rows[start : start + page_size],
            "total": len(rows),
            "facets": facets,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key):
        return next(
            (row for row in PUBLICATIONS if row["publication_key"] == publication_key),
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
        if publication_key == PUBLICATIONS[0]["publication_key"]:
            return {"publication_key": publication_key, "citation_count": 12}
        return None

    def suggest(self, query, *, limit, types=None):
        return [
            {
                "type": "publication",
                "value": PUBLICATIONS[0]["title"],
                "key": PUBLICATIONS[0]["publication_key"],
            }
        ][:limit]

    def semantic_search(self, query, *, filters, limit, min_score):
        row = {
            **PUBLICATIONS[0],
            "semantic_score": 0.925,
            "semantic_rank": 1,
            "similarity_score": 0.925,
            "similarity_rank": 1,
        }
        return [row][:limit]

    def related_publications(self, publication_key, *, filters, limit, min_score):
        if publication_key == "missing":
            raise KeyError(publication_key)
        row = {
            **PUBLICATIONS[1],
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
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def researcher_coauthors(self, researcher_key, *, limit):
        return [{"name": "B. Author", "publication_count": 1}]

    def institution_profile(self, institution_key):
        if institution_key == "missing":
            return None
        return {"key": institution_key, "label": institution_key, "publication_count": 1}

    def institution_publications(self, institution_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def institution_collaborators(self, institution_key, *, limit):
        return [{"institution": "University of Peradeniya", "publication_count": 1}]

    def compare_institutions(self, keys):
        return [{"key": key, "publication_count": 1} for key in keys]

    def topic_publications(self, topic_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def analytics_overview(self, filters):
        return {"publication_count": 2, "citation_total": 12}

    def analytics_trends(self, filters, *, group_by, metric):
        return [{"key": 2024, "publication_count": 1, "citation_total": 12}]

    def paginated_analytics_rankings(self, filters, *, dimension, metric, page, page_size):
        return {
            "records": [
                {
                    "key": "medicine",
                    "label": "Medicine",
                    "publication_count": 1,
                    "citation_total": 12,
                }
            ],
            "total": 1,
        }

    def analytics_rankings(self, filters, *, dimension, metric, limit):
        return self.paginated_analytics_rankings(
            filters, dimension=dimension, metric=metric, page=1, page_size=limit
        )["records"]

    def collaboration_network(self, filters, *, scope, min_weight, limit):
        return {
            "nodes": [{"id": "uoc", "label": "UOC"}],
            "edges": [],
            "summary": {"node_count": 1},
        }

    def data_quality(self, filters, *, group_by):
        return {"record_count": 2, "missing_doi_percentage": 50.0}


def make_api(**kwargs) -> ResearchLankaAPI:
    repo = FakeRepository()
    for key, value in kwargs.items():
        setattr(repo, key, value)
    return ResearchLankaAPI(repo)


def attach_security_case(
    request: pytest.FixtureRequest,
    *,
    test_id: str,
    endpoint: str,
    scenario: str,
    expected: str,
) -> dict[str, str]:
    case = {
        "test_id": test_id,
        "endpoint": endpoint,
        "scenario": scenario,
        "expected": expected,
    }
    request.node._phase3_security_case = case  # type: ignore[attr-defined]
    return case


def assert_no_secret_leak(payload: Any) -> None:
    text = str(payload).lower()
    forbidden = (
        "password=",
        "postgres://",
        "postgresql://",
        "auth_secret",
        "secret_token",
        "api_key=",
        "private_key",
    )
    for needle in forbidden:
        assert needle not in text, f"Possible secret leak containing {needle!r}"
