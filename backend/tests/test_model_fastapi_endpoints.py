"""Tests for FastAPI model-serving endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

import httpx
import pytest
from fastapi import FastAPI

from src.api.fastapi_app import create_app
from src.api.model_service import ModelServingConfig, PublicationClassifierService
from src.api.service import ResearchLankaAPI


class FakePublicationClassifier:
    classes_ = ["Health Sciences", "Physical Sciences"]

    def predict(self, texts: Sequence[str]) -> list[str]:
        return [
            "Health Sciences" if "health" in text.casefold() else "Physical Sciences"
            for text in texts
        ]

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            [0.91, 0.09] if "health" in text.casefold() else [0.12, 0.88]
            for text in texts
        ]


class FakePublicationRepository:
    publication = {
        "publication_key": "doi:10.1000/test",
        "title": "Malaria surveillance in Sri Lanka",
        "doi": "10.1000/test",
        "publication_year": 2024,
        "type": "journal-article",
        "authors": "A. Author; B. Author",
        "institutions": "University of Colombo",
        "journal": "Ceylon Medical Journal",
        "publisher": "Example Publisher",
        "citation_count": 12,
        "reference_count": 30,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Medicine",
        "primary_subfield": "Public Health",
        "source_dataset": "openalex; crossref",
        "abstract": "A study abstract.",
    }

    def health(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        return {"publication_count": 1, "snapshot_date": "2026-07-20"}

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        return {
            "records": [self.publication],
            "total": 1,
            "facets": {"publication_year": {"2024": 1}} if include_facets else None,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key):
        if publication_key == self.publication["publication_key"]:
            return self.publication
        return None

    def get_references(self, publication_key):
        return [{"publication_key": publication_key, "reference_index": 1, "reference_title": "Ref"}]

    def get_count_audit(self, publication_key):
        return {"publication_key": publication_key, "citation_count": 12}

    def suggest(self, query, *, limit):
        return [{"type": "publication", "value": self.publication["title"], "key": self.publication["publication_key"]}]

    def semantic_search(self, query, *, filters, limit, min_score):
        return [{**self.publication, "semantic_score": 0.9, "semantic_rank": 1}]

    def related_publications(self, publication_key, *, filters, limit, min_score):
        return [{**self.publication, "semantic_score": 0.8, "semantic_rank": 1}]

    def researcher_profile(self, researcher_key):
        return {"key": researcher_key, "label": researcher_key, "publication_count": 1}

    def researcher_publications(self, researcher_key, *, page, page_size):
        return {"records": [self.publication], "total": 1}

    def researcher_coauthors(self, researcher_key, *, limit):
        return []

    def institution_profile(self, institution_key):
        return {"key": institution_key, "label": institution_key, "publication_count": 1}

    def institution_publications(self, institution_key, *, page, page_size):
        return {"records": [self.publication], "total": 1}

    def institution_collaborators(self, institution_key, *, limit):
        return []

    def compare_institutions(self, institution_keys):
        return [{"label": key, "publication_count": 1} for key in institution_keys]

    def topic_publications(self, topic_key, *, page, page_size):
        return {"records": [self.publication], "total": 1}

    def analytics_overview(self, filters):
        return {"publication_count": 1}

    def analytics_trends(self, filters, *, group_by, metric):
        return [{"key": 2024, "publication_count": 1}]

    def analytics_rankings(self, filters, *, dimension, metric, limit):
        return [{"key": "medicine", "label": "Medicine", "publication_count": 1}]

    def collaboration_network(self, filters, *, scope, min_weight, limit):
        return {"nodes": [], "edges": [], "summary": {"node_count": 0, "edge_count": 0}}

    def data_quality(self, filters, *, group_by):
        return {"record_count": 1}


def write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "config": {
                    "label_column": "primary_domain",
                    "model_family": "logistic_regression",
                    "text_columns": ["title", "abstract", "keywords"],
                },
                "result": {
                    "input_rows": 100,
                    "usable_rows": 90,
                    "class_count": 2,
                    "accuracy": 0.8,
                    "macro_f1": 0.78,
                },
                "label_counts": {
                    "Health Sciences": 45,
                    "Physical Sciences": 45,
                },
                "artifacts": {"model": {"sha256": "expected-sha256"}},
            }
        ),
        encoding="utf-8",
    )


def app_for_model(tmp_path: Path) -> FastAPI:
    model_path = tmp_path / "classifier.joblib"
    model_path.write_text("fake model artifact", encoding="utf-8")
    manifest_path = tmp_path / "classifier_manifest.json"
    write_manifest(manifest_path)

    service = PublicationClassifierService(
        ModelServingConfig(
            model_path=model_path,
            model_manifest_path=manifest_path,
            verify_checksum=False,
        ),
        model_loader=lambda _model_path, _manifest_path, _verify: (
            FakePublicationClassifier(),
            "loaded-sha256",
        ),
    )
    return create_app(model_service=service)


def app_for_publications() -> FastAPI:
    return create_app(publication_service=ResearchLankaAPI(FakePublicationRepository()))


async def asgi_request(app: FastAPI, method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def request(app: FastAPI, method: str, path: str, **kwargs: Any) -> httpx.Response:
    return asyncio.run(asgi_request(app, method, path, **kwargs))


def test_model_inventory_and_detail_endpoint(tmp_path: Path) -> None:
    app = app_for_model(tmp_path)

    list_response = request(app, "GET", "/api/v1/models")
    detail_response = request(app, "GET", "/api/v1/models/publication-classifier")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    model = list_response.json()["data"][0]
    assert model["id"] == "publication-classifier"
    assert model["status"] == "ready"
    assert model["available"] is True
    assert model["label_column"] == "primary_domain"
    assert model["text_columns"] == ["title", "abstract", "keywords"]
    assert model["labels"][0] == {"label": "Health Sciences", "count": 45}
    assert detail_response.json()["data"]["training"]["accuracy"] == 0.8


def test_single_prediction_combines_publication_text_and_echoes_metadata(tmp_path: Path) -> None:
    app = app_for_model(tmp_path)

    response = request(
        app,
        "POST",
        "/api/v1/models/publication-classifier/predict",
        json={
            "title": "Public health surveillance",
            "abstract": "Patient care evidence from Sri Lanka.",
            "keywords": ["medicine", "health"],
            "doi": "10.1000/demo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["predicted_label"] == "Health Sciences"
    assert payload["data"]["confidence"] == pytest.approx(0.91)
    assert payload["data"]["scores"]["Health Sciences"] == pytest.approx(0.91)
    assert payload["data"]["metadata"]["doi"] == "10.1000/demo"
    assert payload["meta"]["model_sha256"] == "loaded-sha256"


def test_batch_prediction_accepts_explicit_text_records(tmp_path: Path) -> None:
    app = app_for_model(tmp_path)

    response = request(
        app,
        "POST",
        "/api/v1/models/publication-classifier/predict-batch",
        json={
            "records": [
                {"text": "Bridge sensors and engineering materials.", "metadata": {"id": "1"}},
                {"text": "Health systems and clinical care.", "metadata": {"id": "2"}},
            ]
        },
    )

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["predicted_label"] for row in rows] == [
        "Physical Sciences",
        "Health Sciences",
    ]
    assert rows[0]["metadata"] == {"id": "1"}
    assert rows[1]["index"] == 1


def test_prediction_rejects_blank_text(tmp_path: Path) -> None:
    app = app_for_model(tmp_path)

    response = request(
        app,
        "POST",
        "/api/v1/models/publication-classifier/predict",
        json={"title": "  ", "abstract": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_prediction_input"


def test_batch_validation_uses_api_error_envelope(tmp_path: Path) -> None:
    app = app_for_model(tmp_path)

    response = request(
        app,
        "POST",
        "/api/v1/models/publication-classifier/predict-batch",
        json={"records": []},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_unknown_model_returns_not_found(tmp_path: Path) -> None:
    app = app_for_model(tmp_path)

    response = request(app, "GET", "/api/v1/models/unknown")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_fastapi_publication_endpoints_share_service_contract() -> None:
    app = app_for_publications()

    list_response = request(app, "GET", "/api/v1/publications?include_facets=true&page_size=1")
    detail_response = request(app, "GET", "/api/v1/publications/doi%3A10.1000%2Ftest")
    references_response = request(app, "GET", "/api/v1/publications/doi%3A10.1000%2Ftest/references")
    export_response = request(app, "GET", "/api/v1/exports/publications.csv?has_doi=true")

    assert list_response.status_code == 200
    assert list_response.json()["facets"]["publication_year"]["2024"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["publication_key"] == "doi:10.1000/test"
    assert references_response.status_code == 200
    assert references_response.json()["data"][0]["reference_title"] == "Ref"
    assert export_response.status_code == 200
    assert "Malaria surveillance in Sri Lanka" in export_response.text
