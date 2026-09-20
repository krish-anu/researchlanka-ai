"""Phase 2 — classification (hierarchical field → subfield) ML tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.modeling.hierarchical_linear_svm import (
    HierarchicalTrainingConfig,
    default_manifest_output,
    default_metrics_output,
    default_subfield_model_output,
    stratified_test_count,
    train_hierarchical_classifier,
)


pytestmark = [pytest.mark.phase2, pytest.mark.classification]


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
        ("Bridge materials", "Concrete beam load testing", "civil", "bridge", "structures", "Physical Sciences", "Civil Engineering"),
        ("Road pavement", "Asphalt durability traffic load", "civil", "road", "materials", "Physical Sciences", "Civil Engineering"),
        ("Solar inverter", "Photovoltaic grid voltage control", "energy", "solar", "power", "Physical Sciences", "Electrical Engineering"),
        ("Wind turbine", "Renewable generator power system", "energy", "wind", "electricity", "Physical Sciences", "Electrical Engineering"),
        ("Hospital care", "Patient treatment clinical workflow", "medicine", "patient", "health", "Health Sciences", "Clinical Medicine"),
        ("Cancer screening", "Diagnosis clinical oncology patient", "medicine", "screening", "health", "Health Sciences", "Clinical Medicine"),
        ("Disease surveillance", "Community infection prevention", "public health", "disease", "population", "Health Sciences", "Public Health"),
        ("Vaccination program", "Population immunity prevention", "public health", "vaccine", "community", "Health Sciences", "Public Health"),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(FIELDNAMES, row, strict=True)))


def test_default_classification_artifact_names():
    assert default_subfield_model_output().name.endswith(".joblib")
    assert default_metrics_output().suffix == ".txt"
    assert default_manifest_output().suffix == ".json"


def test_stratified_test_count_expands_tiny_holdout():
    rows = []
    for class_index in range(5):
        for row_index in range(4):
            rows.append({"text": f"class {class_index} example {row_index}", "label": f"class-{class_index}"})
    frame = pd.DataFrame(rows)
    assert stratified_test_count(frame, "label", test_size=0.15) == 5


def test_hierarchical_classifier_trains_and_writes_artifacts(tmp_path: Path):
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
    assert result.manifest_output.exists()
    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == 1
    assert result.subfield_model_count >= 1


@pytest.mark.edge_case
def test_hierarchical_training_requires_label_columns(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    with bad.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "abstract"])
        writer.writerow(["Only title", "Only abstract"])

    with pytest.raises((KeyError, ValueError, SystemExit)):
        train_hierarchical_classifier(
            HierarchicalTrainingConfig(
                input_path=bad,
                taxonomy_path=tmp_path / "missing_taxonomy.json",
                field_model_output=tmp_path / "field.joblib",
                subfield_model_output=tmp_path / "subfields.joblib",
                metrics_output=tmp_path / "metrics.txt",
                label_counts_output=tmp_path / "labels.csv",
                manifest_output=tmp_path / "manifest.json",
                min_df=1,
                max_df=1.0,
            )
        )
