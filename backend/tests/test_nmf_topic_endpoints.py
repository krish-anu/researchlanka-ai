"""Tests for NMF topic modeling integrated into existing API routes."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.core.errors import APIError
from src.api.repositories.nmf_topics import NmfTopicStore
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.api.services.nmf_topics import NmfTopicService
from src.modeling.nmf_trends import classify_trend, topic_trend_slopes


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "nmf_k25"


PUBLICATIONS = [
    {
        "publication_key": "doi:10.1000/test",
        "title": "Malaria surveillance in Sri Lanka",
        "doi": "10.1000/test",
        "publication_year": 2024,
        "type": "journal-article",
        "authors": "A. Author",
        "institutions": "University of Colombo",
        "journal": "Ceylon Medical Journal",
        "publisher": "Example Publisher",
        "citation_count": 12,
        "reference_count": 30,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Medicine",
        "primary_subfield": "Public Health",
        "source_dataset": "openalex",
    },
    {
        "publication_key": "source:repositories_combined:thesis-1",
        "title": "Repository-only thesis",
        "doi": None,
        "publication_year": 2023,
        "type": "thesis",
        "authors": "C. Author",
        "institutions": "University of Ruhuna",
        "journal": None,
        "publisher": "University of Ruhuna",
        "citation_count": 0,
        "reference_count": None,
        "is_oa": None,
        "oa_status": None,
        "primary_field": None,
        "primary_subfield": None,
        "source_dataset": "repositories_combined",
    },
    {
        "publication_key": "doi:10.1000/env",
        "title": "Water quality in wetlands",
        "doi": "10.1000/env",
        "publication_year": 2022,
        "type": "journal-article",
        "authors": "D. Author",
        "institutions": "University of Peradeniya",
        "journal": "Env Journal",
        "publisher": "Example Publisher",
        "citation_count": 4,
        "reference_count": 18,
        "is_oa": False,
        "oa_status": "closed",
        "primary_field": "Environmental Science",
        "primary_subfield": "Ecology",
        "source_dataset": "openalex",
    },
]


class FakeRepository:
    def health(self):
        return True

    def metadata(self):
        return {"publication_count": len(PUBLICATIONS), "snapshot_date": "2026-07-20"}

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        rows = PUBLICATIONS
        keys = filters.get("publication_keys")
        if keys is not None:
            rows = [row for row in rows if row["publication_key"] in keys]
        start = (page - 1) * page_size
        return {"records": rows[start : start + page_size], "total": len(rows), "facets": None, "meta": self.metadata()}

    def get_publication(self, publication_key):
        return next((row for row in PUBLICATIONS if row["publication_key"] == publication_key), None)

    def semantic_search(self, query, *, filters, limit, min_score):
        rows = PUBLICATIONS
        keys = filters.get("publication_keys")
        if keys is not None:
            rows = [row for row in rows if row["publication_key"] in keys]
        return rows[:limit]

    def analytics_trends(self, filters, *, group_by, metric):
        return [{"key": 2024, "publication_count": 1, "citation_total": 0}]


@pytest.fixture
def store() -> NmfTopicStore:
    return NmfTopicStore(FIXTURE_DIR)


@pytest.fixture
def api(store: NmfTopicStore) -> ResearchLankaAPI:
    return ResearchLankaAPI(FakeRepository(), nmf_service=NmfTopicService(store))


def test_topic_trend_slopes_and_classification(store: NmfTopicStore):
    slopes = topic_trend_slopes(store.trend_shares)
    classified = classify_trend(slopes)
    by_name = {row["topic_name"]: row["trend"] for row in classified.to_dict("records")}
    assert by_name["patients / age / hospital"] == "emerging"
    assert by_name["medicine / internal_medicine / internal"] == "declining"
    assert by_name["environmental / water / environmental_science"] == "emerging"


def test_topics_directory_uses_existing_endpoint(api: ResearchLankaAPI):
    result = route_get(api, "/api/v1/topics", {})
    assert result["pagination"]["total"] == 3
    assert result["data"][0]["source"] == "nmf"
    assert "topic_id" in result["data"][0]


def test_emerging_and_declining_via_topics_filter(api: ResearchLankaAPI):
    emerging = route_get(api, "/api/v1/topics", {"trend": ["emerging"]})
    declining = route_get(api, "/api/v1/topics", {"trend": ["declining"]})
    assert all(row["trend"] == "emerging" for row in emerging["data"])
    assert all(row["trend"] == "declining" for row in declining["data"])
    assert len(emerging["data"]) == 2
    assert len(declining["data"]) == 1


def test_analytics_trends_group_by_nmf_topic(api: ResearchLankaAPI):
    result = route_get(
        api,
        "/api/v1/analytics/trends",
        {"group_by": ["nmf_topic"], "topic_id": ["1"]},
    )
    assert result["data"]
    assert all(row["topic_id"] == 1 for row in result["data"])


def test_publication_search_by_nmf_topic_id(api: ResearchLankaAPI):
    result = api.list_publications({"nmf_topic_id": ["1"]})
    assert result["pagination"]["total"] == 1
    assert result["data"][0]["publication_key"] == "doi:10.1000/test"
    assert result["data"][0]["nmf_topic_name"] == "patients / age / hospital"


def test_publication_search_by_nmf_topic_name(api: ResearchLankaAPI):
    result = api.list_publications(
        {"nmf_topic": ["environmental / water / environmental_science"]}
    )
    assert result["pagination"]["total"] == 1
    assert result["data"][0]["publication_key"] == "doi:10.1000/env"


def test_topic_publications_existing_endpoint(api: ResearchLankaAPI):
    topic_name = "medicine / internal_medicine / internal"
    result = route_get(
        api,
        f"/api/v1/topics/{topic_name}/publications",
        {},
    )
    assert result["pagination"]["total"] == 1
    assert result["data"][0]["publication_key"] == "source:repositories_combined:thesis-1"


def test_topic_publications_by_numeric_id(api: ResearchLankaAPI):
    result = route_get(api, "/api/v1/topics/1/publications", {})
    assert result["pagination"]["total"] == 1


def test_publication_detail_includes_nmf_assignment(api: ResearchLankaAPI):
    detail = api.publication_detail("doi:10.1000/test")
    assert detail["data"]["nmf_topic_id"] == 1


def test_unknown_nmf_topic_publications_returns_not_found(api: ResearchLankaAPI):
    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/topics/not-a-real-topic/publications", {})
    assert exc.value.status == 404


def test_openalex_topic_source_still_available():
    class OpenAlexRepository(FakeRepository):
        def topic_publications(self, topic_key, *, page, page_size):
            return {"records": [PUBLICATIONS[0]], "total": 1}

    service = ResearchLankaAPI(
        OpenAlexRepository(),
        nmf_service=NmfTopicService(NmfTopicStore(FIXTURE_DIR)),
    )
    result = route_get(service, "/api/v1/topics/Epidemiology/publications", {"source": ["openalex"]})
    assert result["pagination"]["total"] == 1
