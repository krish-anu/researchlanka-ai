"""Tests for the local AI relevance SVM training and prediction flow."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from src.ai_relevance.svm_model import (
    AIRelevanceSVMPredictionConfig,
    AIRelevanceSVMTrainingConfig,
    predict_rest_with_ai_relevance_svm,
    train_ai_relevance_svm,
)


FIELDNAMES = [
    "publication_id",
    "ai_llm_status",
    "ai_llm_label",
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
]


def write_labelled_csv(path: Path) -> None:
    rows = [
        {
            "publication_id": "p1",
            "ai_llm_status": "success",
            "ai_llm_label": "AI",
            "title": "Deep learning for crop disease detection",
            "abstract": "A neural network classifies plant disease images.",
            "keywords": "deep learning; computer vision",
        },
        {
            "publication_id": "p2",
            "ai_llm_status": "success",
            "ai_llm_label": "AI",
            "title": "Machine learning for rainfall prediction",
            "abstract": "Random forest and support vector machines forecast rainfall.",
            "keywords": "machine learning",
        },
        {
            "publication_id": "p3",
            "ai_llm_status": "success",
            "ai_llm_label": "AI",
            "title": "ChatGPT adoption in higher education",
            "abstract": "Students report perceptions of generative AI tools.",
            "keywords": "ChatGPT; generative AI",
        },
        {
            "publication_id": "p4",
            "ai_llm_status": "success",
            "ai_llm_label": "AI",
            "title": "Convolutional neural network for tea leaf images",
            "abstract": "Computer vision model evaluates disease severity.",
            "keywords": "CNN; image classification",
        },
        {
            "publication_id": "p5",
            "ai_llm_status": "success",
            "ai_llm_label": "NON_AI",
            "title": "Bridge concrete strength assessment",
            "abstract": "Materials testing is conducted using laboratory methods.",
            "keywords": "civil engineering",
        },
        {
            "publication_id": "p6",
            "ai_llm_status": "success",
            "ai_llm_label": "NON_AI",
            "title": "Public health survey of dengue cases",
            "abstract": "A descriptive epidemiological analysis is presented.",
            "keywords": "public health",
        },
        {
            "publication_id": "p7",
            "ai_llm_status": "success",
            "ai_llm_label": "NON_AI",
            "title": "Soil nutrient status in paddy fields",
            "abstract": "Chemical measurements compare soil samples.",
            "keywords": "agriculture",
        },
        {
            "publication_id": "p8",
            "ai_llm_status": "success",
            "ai_llm_label": "NON_AI",
            "title": "Financial reporting compliance",
            "abstract": "Accounting standards are compared across firms.",
            "keywords": "accounting",
        },
        {
            "publication_id": "p9",
            "ai_llm_status": "success",
            "ai_llm_label": "REVIEW",
            "title": "Ambiguous modelling study",
            "abstract": "",
            "keywords": "",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def write_corpus_csv(path: Path) -> None:
    rows = [
        {"source_record_id": "p1", "title": "already labelled AI", "abstract": "deep learning"},
        {"source_record_id": "p5", "title": "already labelled non AI", "abstract": "soil"},
        {
            "source_record_id": "p10",
            "title": "Neural network for medical image diagnosis",
            "abstract": "A deep learning system classifies x ray images.",
            "keywords": "deep learning",
        },
        {
            "source_record_id": "p11",
            "title": "Library collection management practices",
            "abstract": "A survey of cataloguing workflows.",
            "keywords": "library science",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["source_record_id", "title", "abstract", "keywords"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_train_and_predict_ai_relevance_svm(tmp_path: Path) -> None:
    labelled = tmp_path / "labelled.csv"
    corpus = tmp_path / "corpus.csv"
    model = tmp_path / "model.joblib"
    manifest = tmp_path / "manifest.json"
    predictions = tmp_path / "rest_predictions.csv"
    rest_manifest = tmp_path / "rest_manifest.json"
    write_labelled_csv(labelled)
    write_corpus_csv(corpus)

    train_result = train_ai_relevance_svm(
        AIRelevanceSVMTrainingConfig(
            input_path=labelled,
            model_output=model,
            metrics_output=tmp_path / "metrics.txt",
            label_counts_output=tmp_path / "labels.csv",
            predictions_output=tmp_path / "test_predictions.csv",
            manifest_output=manifest,
            text_columns=("title", "abstract", "keywords"),
            min_class_count=2,
            min_df=1,
            max_df=1.0,
            ngram_max=1,
            cv_folds=2,
            test_size=0.25,
        )
    )

    assert train_result.usable_rows == 8
    assert model.exists()

    predict_result = predict_rest_with_ai_relevance_svm(
        AIRelevanceSVMPredictionConfig(
            input_path=corpus,
            labelled_input_path=labelled,
            model_path=model,
            model_manifest_path=manifest,
            output_path=predictions,
            manifest_output=rest_manifest,
            text_columns=("title", "abstract", "keywords"),
            metadata_columns=("source_record_id", "title"),
        )
    )

    rows = pd.read_csv(predictions)
    assert predict_result.input_rows == 4
    assert predict_result.excluded_rows == 2
    assert predict_result.predicted_rows == 2
    assert rows["source_record_id"].tolist() == ["p10", "p11"]
    assert set(rows["ai_svm_label"]).issubset({"AI", "NON_AI"})
