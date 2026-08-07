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
