"""Tests for publication classification model-family comparison."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.modeling.classification_comparison import (
    ClassificationComparisonConfig,
    compare_classification_models,
    parse_model_families,
)


FIELDNAMES = ["title", "abstract", "keywords", "primary_domain"]


def write_comparison_csv(path: Path) -> None:
    rows = [
        {
            "title": "Hospital patient care",
            "abstract": "Clinical treatment medicine evidence",
            "keywords": "health; patient",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Disease surveillance",
            "abstract": "Public health prevention study",
            "keywords": "disease; health",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Cancer screening",
            "abstract": "Medical diagnosis patient cohort",
            "keywords": "medicine; diagnosis",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Nursing education",
            "abstract": "Clinical care hospital training",
            "keywords": "care; medicine",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Bridge sensor network",
            "abstract": "Structural engineering monitoring system",
            "keywords": "engineering; sensors",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Energy material simulation",
            "abstract": "Physics experiment advanced materials",
            "keywords": "physics; materials",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Wireless optimization",
            "abstract": "Engineering algorithm communication networks",
            "keywords": "engineering; networks",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Quantum device",
            "abstract": "Physics materials laboratory measurement",
            "keywords": "physics; device",
            "primary_domain": "Physical Sciences",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_comparison_csv_with_unusable_rows(path: Path) -> None:
    rows = [
        {
            "title": "Blank label row",
            "abstract": "This row has text but no target label",
            "keywords": "ignored",
            "primary_domain": "",
        },
        {
            "title": "",
            "abstract": "",
            "keywords": "",
            "primary_domain": "Health Sciences",
        },
        {
            "title": "Single small class",
            "abstract": "Only one row should be removed by min class count",
            "keywords": "small",
            "primary_domain": "Social Sciences",
        },
    ]
    with path.open("a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writerows(rows)


def test_compare_classification_models_trains_and_ranks_all_families_on_shared_rows(
    tmp_path: Path,
) -> None:
    input_csv = tmp_path / "publications.csv"
    output_dir = tmp_path / "comparison"
    write_comparison_csv(input_csv)
    write_comparison_csv_with_unusable_rows(input_csv)

    result = compare_classification_models(
        ClassificationComparisonConfig(
            input_path=input_csv,
            label_column="primary_domain",
            text_columns=("title", "abstract", "keywords"),
            output_dir=output_dir,
            test_size=0.25,
            min_class_count=4,
            max_features=50,
            min_df=1,
            max_df=1.0,
            ngram_max=1,
            max_iter=500,
            c_values=(0.1, 1.0),
            cv_folds=2,
        )
    )

    comparison_rows = list(csv.DictReader(result.comparison_output.open(encoding="utf-8")))
    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))

    assert result.model_count == 3
    assert {row["model_family"] for row in comparison_rows} == {
        "logistic_regression",
        "multinomial_nb",
        "linear_svm",
    }
    assert comparison_rows[0]["rank"] == "1"
    assert manifest["best_model_family"] == result.best_model_family
    assert manifest["ranking_metric"] == "macro_f1"
    assert result.shared_training_rows == 8
    assert result.shared_training_input.exists()
    assert manifest["source_input_rows"] == 11
    assert manifest["shared_training_rows"] == 8
    assert {row["usable_rows"] for row in comparison_rows} == {"8"}
    assert {row["train_rows"] for row in comparison_rows} == {"6"}
    assert {row["test_rows"] for row in comparison_rows} == {"2"}

    for row in comparison_rows:
        assert Path(row["model_path"]).exists()
        assert Path(row["metrics_path"]).exists()
        assert Path(row["predictions_path"]).exists()
        assert Path(row["manifest_path"]).exists()


def test_parse_model_families_rejects_unknown_family() -> None:
    try:
        parse_model_families("logistic_regression,random_forest")
    except Exception as exc:
        assert "unsupported model family" in str(exc)
    else:
        raise AssertionError("unsupported model family was accepted")
