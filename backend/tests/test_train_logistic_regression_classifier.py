"""Tests for the Logistic Regression publication classifier trainer."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.modeling.train_logistic_regression_classifier import (
    load_training_frame,
    train_logistic_regression_classifier,
)


FIELDNAMES = ["title", "abstract", "keywords", "primary_domain"]


def write_training_csv(path: Path) -> None:
    rows = [
        {
            "title": "Hospital medicine trial",
            "abstract": "Clinical health patient treatment study",
            "keywords": "medicine; health",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Public health surveillance",
            "abstract": "Disease prevention and patient care evidence",
            "keywords": "health; disease",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Cancer diagnosis model",
            "abstract": "Medical screening and clinical diagnosis",
            "keywords": "medicine; diagnosis",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Bridge sensor design",
            "abstract": "Structural engineering monitoring system",
            "keywords": "engineering; sensors",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Energy materials simulation",
            "abstract": "Physics experiment for advanced materials",
            "keywords": "physics; materials",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Wireless network optimization",
            "abstract": "Engineering algorithm for communication networks",
            "keywords": "engineering; networks",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Blank label row",
            "abstract": "This row should be dropped",
            "keywords": "",
            "primary_domain": "",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_load_training_frame_drops_blank_labels_and_small_classes(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    write_training_csv(input_csv)

    frame, input_rows, label_counts = load_training_frame(
        input_csv,
        label_column="primary_domain",
        text_columns=["title", "abstract", "keywords"],
        min_class_count=3,
        max_rows=None,
    )

    assert input_rows == 7
    assert len(frame) == 6
    assert set(label_counts.index) == {"Health Sciences", "Physical Sciences"}
    assert frame["text"].str.contains("Hospital medicine trial").any()


def test_train_logistic_regression_classifier_writes_model_and_metrics(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    model_output = tmp_path / "logreg.joblib"
    metrics_output = tmp_path / "metrics.txt"
    labels_output = tmp_path / "labels.csv"
    write_training_csv(input_csv)

    result = train_logistic_regression_classifier(
        input_path=input_csv,
        label_column="primary_domain",
        text_columns=["title", "abstract", "keywords"],
        model_output=model_output,
        metrics_output=metrics_output,
        label_counts_output=labels_output,
        test_size=0.5,
        min_class_count=3,
        max_features=50,
        min_df=1,
        max_df=1.0,
        ngram_max=1,
        max_iter=200,
    )

    assert result.usable_rows == 6
    assert result.class_count == 2
    assert model_output.exists()
    assert labels_output.exists()
    assert "Classification report:" in metrics_output.read_text(encoding="utf-8")
