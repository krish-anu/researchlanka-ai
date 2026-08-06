"""Tests for the Logistic Regression publication classifier trainer."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.modeling.artifacts import file_sha256, save_model_artifacts
from src.modeling.inference import ModelInferenceConfig, run_model_inference
from src.modeling.training import TextTrainingConfig, train_text_classifier
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
    predictions_output = tmp_path / "predictions.csv"
    manifest_output = tmp_path / "manifest.json"
    write_training_csv(input_csv)

    result = train_logistic_regression_classifier(
        input_path=input_csv,
        label_column="primary_domain",
        text_columns=["title", "abstract", "keywords"],
        model_output=model_output,
        metrics_output=metrics_output,
        label_counts_output=labels_output,
        predictions_output=predictions_output,
        manifest_output=manifest_output,
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
    assert predictions_output.exists()
    assert manifest_output.exists()
    assert "Classification report:" in metrics_output.read_text(encoding="utf-8")

    manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    model_artifact = manifest["artifacts"]["model"]
    metrics_artifact = manifest["artifacts"]["metrics"]

    assert manifest["artifact_schema_version"] == 1
    assert manifest["config"]["label_column"] == "primary_domain"
    assert manifest["result"]["test_rows"] == 3
    assert manifest["result"]["model_sha256"] == file_sha256(model_output)
    assert model_artifact["path"] == str(model_output)
    assert model_artifact["bytes"] == model_output.stat().st_size
    assert model_artifact["sha256"] == file_sha256(model_output)
    assert metrics_artifact["sha256"] == file_sha256(metrics_output)
    assert result.model_sha256 == file_sha256(model_output)


def test_train_text_classifier_uses_dataclass_config(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    write_training_csv(input_csv)

    result = train_text_classifier(
        TextTrainingConfig(
            input_path=input_csv,
            label_column="primary_domain",
            text_columns=("title", "abstract", "keywords"),
            model_output=tmp_path / "configured_model.joblib",
            metrics_output=tmp_path / "configured_metrics.txt",
            label_counts_output=tmp_path / "configured_labels.csv",
            predictions_output=tmp_path / "configured_predictions.csv",
            manifest_output=tmp_path / "configured_manifest.json",
            test_size=0.5,
            min_class_count=3,
            max_features=50,
            min_df=1,
            max_df=1.0,
            ngram_max=1,
            max_iter=200,
        )
    )

    assert result.model_output.exists()
    assert result.metrics_output.exists()
    assert result.label_counts_output.exists()
    assert result.predictions_output.exists()
    assert result.manifest_output.exists()
    assert result.macro_f1 >= 0


def test_save_model_artifacts_replaces_outputs_and_records_checksums(tmp_path: Path):
    model_output = tmp_path / "model.joblib"
    metrics_output = tmp_path / "metrics.txt"
    labels_output = tmp_path / "labels.csv"
    predictions_output = tmp_path / "predictions.csv"
    manifest_output = tmp_path / "manifest.json"
    model_output.write_text("old model contents", encoding="utf-8")

    saved = save_model_artifacts(
        model={"version": 1},
        model_output=model_output,
        metrics_text="accuracy: 1.0000\n",
        metrics_output=metrics_output,
        label_counts={"Health Sciences": 2, "Physical Sciences": 2},
        label_counts_output=labels_output,
        predictions=[
            {
                "source_row": 0,
                "label": "Health Sciences",
                "prediction": "Health Sciences",
                "correct": True,
                "text": "health study",
            }
        ],
        predictions_output=predictions_output,
        manifest_output=manifest_output,
        manifest_config={"label_column": "primary_domain"},
        manifest_result={"accuracy": 1.0},
        created_at="2026-08-06T00:00:00+00:00",
    )

    manifest = json.loads(manifest_output.read_text(encoding="utf-8"))

    assert saved.model.path == model_output
    assert saved.model.bytes == model_output.stat().st_size
    assert saved.model.sha256 == file_sha256(model_output)
    assert manifest["artifacts"]["model"]["sha256"] == saved.model.sha256
    assert manifest["artifacts"]["predictions"]["sha256"] == file_sha256(predictions_output)
    assert manifest["result"]["model_sha256"] == saved.model.sha256
    assert "old model contents" not in model_output.read_text(encoding="latin1")


def test_run_model_inference_writes_predictions_and_manifest(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    model_output = tmp_path / "logreg.joblib"
    training_manifest_output = tmp_path / "training_manifest.json"
    inference_output = tmp_path / "inference_predictions.csv"
    inference_manifest_output = tmp_path / "inference_manifest.json"
    write_training_csv(input_csv)

    train_logistic_regression_classifier(
        input_path=input_csv,
        label_column="primary_domain",
        text_columns=["title", "abstract", "keywords"],
        model_output=model_output,
        metrics_output=tmp_path / "metrics.txt",
        label_counts_output=tmp_path / "labels.csv",
        predictions_output=tmp_path / "training_predictions.csv",
        manifest_output=training_manifest_output,
        test_size=0.5,
        min_class_count=3,
        max_features=50,
        min_df=1,
        max_df=1.0,
        ngram_max=1,
        max_iter=200,
    )

    result = run_model_inference(
        ModelInferenceConfig(
            input_path=input_csv,
            model_path=model_output,
            output_path=inference_output,
            inference_manifest_path=inference_manifest_output,
            model_manifest_path=training_manifest_output,
            text_columns=("title", "abstract", "keywords"),
            metadata_columns=("title",),
        )
    )

    rows = list(csv.DictReader(inference_output.open(encoding="utf-8")))
    manifest = json.loads(inference_manifest_output.read_text(encoding="utf-8"))

    assert result.input_rows == 7
    assert result.predicted_rows == 7
    assert result.skipped_rows == 0
    assert len(rows) == 7
    assert rows[0]["predicted_label"]
    assert rows[0]["confidence"]
    assert rows[0]["title"] == "Hospital medicine trial"
    assert manifest["artifact_schema_version"] == 1
    assert manifest["artifacts"]["model"]["sha256"] == file_sha256(model_output)
    assert manifest["artifacts"]["predictions"]["sha256"] == file_sha256(inference_output)


def test_run_model_inference_rejects_model_checksum_mismatch(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    model_output = tmp_path / "logreg.joblib"
    training_manifest_output = tmp_path / "training_manifest.json"
    write_training_csv(input_csv)

    train_logistic_regression_classifier(
        input_path=input_csv,
        label_column="primary_domain",
        text_columns=["title", "abstract", "keywords"],
        model_output=model_output,
        metrics_output=tmp_path / "metrics.txt",
        label_counts_output=tmp_path / "labels.csv",
        predictions_output=tmp_path / "training_predictions.csv",
        manifest_output=training_manifest_output,
        test_size=0.5,
        min_class_count=3,
        max_features=50,
        min_df=1,
        max_df=1.0,
        ngram_max=1,
        max_iter=200,
    )
    with model_output.open("ab") as output_file:
        output_file.write(b"tampered")

    with pytest.raises(ValueError, match="checksum does not match"):
        run_model_inference(
            ModelInferenceConfig(
                input_path=input_csv,
                model_path=model_output,
                output_path=tmp_path / "inference_predictions.csv",
                inference_manifest_path=tmp_path / "inference_manifest.json",
                model_manifest_path=training_manifest_output,
                text_columns=("title", "abstract", "keywords"),
                metadata_columns=("title",),
            )
        )
