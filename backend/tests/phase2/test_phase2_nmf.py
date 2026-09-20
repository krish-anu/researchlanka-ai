"""Phase 2 — NMF topic modeling (k=25 trends + API integration)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.api.repositories.nmf_topics import NmfTopicStore
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.api.services.nmf_topics import NmfTopicService
from src.modeling.nmf_topic_modeling import assign_dominant_topic, get_topic_keywords
from src.modeling.nmf_trends import classify_trend, topic_trend_slopes
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer


pytestmark = [pytest.mark.phase2, pytest.mark.nmf_topic_modeling]

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "nmf_k25"


@pytest.fixture
def store() -> NmfTopicStore:
    return NmfTopicStore(FIXTURE_DIR)


def test_nmf_fit_and_keyword_extraction_smoke():
    docs = [
        "machine learning neural networks deep learning",
        "machine learning classification regression models",
        "public health malaria dengue surveillance",
        "hospital patients clinical treatment medicine",
        "climate water environmental science ecology",
        "soil agriculture crop yield farming",
    ] * 3
    vectorizer = TfidfVectorizer(min_df=1)
    X = vectorizer.fit_transform(docs)
    model = NMF(n_components=3, random_state=42, max_iter=400)
    W = model.fit_transform(X)
    keywords = get_topic_keywords(model, vectorizer.get_feature_names_out(), n_words=5)
    dominant, weight = assign_dominant_topic(W)
    assert len(keywords) == 3
    assert all(len(words) == 5 for words in keywords)
    assert len(dominant) == len(docs)
    assert np.all(weight >= 0)


def test_emerging_declining_classification_from_shares(store: NmfTopicStore):
    slopes = topic_trend_slopes(store.trend_shares)
    classified = classify_trend(slopes)
    trends = set(classified["trend"])
    assert {"emerging", "declining", "stable"} & trends
    assert (classified["trend"] == "emerging").any()
    assert (classified["trend"] == "declining").any()


def test_nmf_store_lists_k25_style_topics(store: NmfTopicStore):
    topics = store.list_topics()
    assert len(topics) == 3  # fixture uses 3 topics for speed
    detail = store.get_topic(1)
    assert detail is not None
    assert detail["top_words"]
    assert "yearly_trends" in detail


def test_nmf_topics_api_emerging_filter(store: NmfTopicStore):
    class FakeRepo:
        def health(self):
            return True

        def metadata(self):
            return {"publication_count": 0, "snapshot_date": "2026-01-01"}

        def list_publications(self, filters, *, page, page_size, sort, include_facets):
            return {"records": [], "total": 0, "facets": None, "meta": self.metadata()}

    api = ResearchLankaAPI(FakeRepo(), nmf_service=NmfTopicService(store))
    emerging = route_get(api, "/api/v1/topics", {"trend": ["emerging"]})
    assert emerging["pagination"]["total"] >= 1
    assert all(row["trend"] == "emerging" for row in emerging["data"])


def test_analytics_trends_group_by_nmf_topic(store: NmfTopicStore):
    class FakeRepo:
        def health(self):
            return True

        def metadata(self):
            return {"publication_count": 0}

        def analytics_trends(self, filters, *, group_by, metric):
            return []

    api = ResearchLankaAPI(FakeRepo(), nmf_service=NmfTopicService(store))
    payload = route_get(
        api,
        "/api/v1/analytics/trends",
        {"group_by": ["nmf_topic"], "topic_id": ["1"]},
    )
    assert payload["data"]
    assert all(row.get("topic_id") == 1 for row in payload["data"])
