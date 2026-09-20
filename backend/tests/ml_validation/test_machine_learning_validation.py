"""Machine learning validation tests.

Run (from backend/):

    pytest tests/ml_validation -v
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.api.core.errors import APIError
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.modeling.hierarchical_linear_svm import (
    HierarchicalTrainingConfig,
    train_hierarchical_classifier,
)


FIELDNAMES = [
    "title",
    "abstract",
    "topics",
    "keywords",
    "concepts",
    "primary_field",
    "primary_subfield",
]


def _write_training_csv(path: Path) -> None:
    rows = [
        (
            "Bridge materials",
            "Concrete beam load testing",
            "civil",
            "bridge",
            "structures",
            "Physical Sciences",
            "Civil Engineering",
        ),
        (
            "Road pavement",
            "Asphalt durability traffic load",
            "civil",
            "road",
            "materials",
            "Physical Sciences",
            "Civil Engineering",
        ),
        (
            "Solar inverter",
            "Photovoltaic grid voltage control",
            "energy",
            "solar",
            "power",
            "Physical Sciences",
            "Electrical Engineering",
        ),
        (
            "Wind turbine",
            "Renewable generator power system",
            "energy",
            "wind",
            "electricity",
            "Physical Sciences",
            "Electrical Engineering",
        ),
        (
            "Hospital care",
            "Patient treatment clinical workflow",
            "medicine",
            "patient",
            "health",
            "Health Sciences",
            "Clinical Medicine",
        ),
        (
            "Cancer screening",
            "Diagnosis clinical oncology patient",
            "medicine",
            "screening",
            "health",
            "Health Sciences",
            "Clinical Medicine",
        ),
        (
            "Disease surveillance",
            "Community infection prevention",
            "public health",
            "disease",
            "population",
            "Health Sciences",
            "Public Health",
        ),
        (
            "Vaccination program",
            "Population immunity prevention",
            "public health",
            "vaccine",
            "community",
            "Health Sciences",
            "Public Health",
        ),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(FIELDNAMES, row, strict=True)))


def test_hierarchical_linear_svm_trains_and_writes_model_artifacts(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    _write_training_csv(input_csv)
    result = train_hierarchical_classifier(
        HierarchicalTrainingConfig(
            input_path=input_csv,
            taxonomy_path=tmp_path / "missing_taxonomy.json",
            field_model_output=tmp_path / "field.joblib",
            subfield_model_output=tmp_path / "subfields.joblib",
            metrics_output=tmp_path / "metrics.txt",
            label_counts_output=tmp_path / "labels.csv",
            manifest_output=tmp_path / "manifest.json",
            test_size=0.5,
            min_subfield_count=2,
            max_features=50,
            min_df=1,
            max_df=1.0,
            ngram_max=1,
            max_iter=1000,
        )
    )
    assert result.field_model_output.exists()
    assert result.subfield_model_output.exists()
    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == 1


def test_hierarchical_training_rejects_csv_without_label_columns(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("title,abstract\nhello,world\n", encoding="utf-8")
    with pytest.raises(Exception):
        train_hierarchical_classifier(
            HierarchicalTrainingConfig(
                input_path=path,
                taxonomy_path=tmp_path / "tax.json",
                field_model_output=tmp_path / "field.joblib",
                subfield_model_output=tmp_path / "subfields.joblib",
                metrics_output=tmp_path / "metrics.txt",
                label_counts_output=tmp_path / "labels.csv",
                manifest_output=tmp_path / "manifest.json",
                test_size=0.5,
                min_subfield_count=1,
                max_features=20,
                min_df=1,
                max_df=1.0,
                ngram_max=1,
                max_iter=200,
            )
        )


def test_nmf_fit_produces_topic_keywords_for_document_corpus():
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    from src.modeling.nmf_topic_modeling import get_topic_keywords

    docs = [
        "machine learning neural networks deep learning",
        "machine learning classification regression models",
        "public health malaria dengue surveillance",
        "hospital patients clinical treatment medicine",
        "climate water environmental science ecology",
        "soil agriculture crop yield farming",
    ] * 3
    vectorizer = TfidfVectorizer(min_df=1)
    matrix = vectorizer.fit_transform(docs)
    model = NMF(n_components=3, random_state=0, max_iter=400)
    model.fit(matrix)
    keywords = get_topic_keywords(model, vectorizer.get_feature_names_out(), n_words=5)
    assert len(keywords) == 3
    assert all(len(words) >= 1 for words in keywords)


def test_semantic_search_api_requires_query(api: ResearchLankaAPI):
    with pytest.raises(APIError):
        route_get(api, "/api/v1/search/semantic", {})


def test_semantic_search_api_returns_ranked_rows_for_query(api: ResearchLankaAPI):
    result = route_get(api, "/api/v1/search/semantic", {"q": ["malaria research"]})
    rows = result.get("data") or []
    assert isinstance(rows, list)
    assert rows
    assert "publication_key" in rows[0]


def test_related_publications_exclude_the_source_publication(api: ResearchLankaAPI):
    listing = route_get(api, "/api/v1/publications", {"page_size": ["1"]})
    key = listing["data"][0]["publication_key"]
    related = route_get(api, f"/api/v1/publications/{key}/related", {})
    rows = related.get("data") or []
    assert all(item.get("publication_key") != key for item in rows)
