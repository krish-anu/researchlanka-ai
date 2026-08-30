"""Tests for hierarchical Linear SVM training artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.modeling.artifacts import file_sha256
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


def write_hierarchical_csv(path: Path) -> None:
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
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(FIELDNAMES, row, strict=True)))


def test_hierarchical_training_preserves_manifest_schema(tmp_path: Path) -> None:
    input_csv = tmp_path / "publications.csv"
    write_hierarchical_csv(input_csv)

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

    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))

    assert manifest["artifact_schema_version"] == 1
    assert manifest["artifacts"]["model"]["sha256"] == file_sha256(
        result.field_model_output
    )
    assert manifest["result"]["field_model_sha256"] == file_sha256(
        result.field_model_output
    )
    assert manifest["artifacts"]["subfield_models"]["sha256"] == file_sha256(
        result.subfield_model_output
    )
    assert manifest["result"]["subfield_model_sha256"] == file_sha256(
        result.subfield_model_output
    )
    assert manifest["result"]["subfield_models_trained_for"] == [
        "Health Sciences",
        "Physical Sciences",
    ]
    assert result.subfield_model_count == 2
    assert result.subfield_evaluated_model_count == 2
