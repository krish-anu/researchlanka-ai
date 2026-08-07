"""Tests for publication classifier train/validation/test dataset splits."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.modeling.dataset_splits import DatasetSplitConfig, create_dataset_splits
from scripts.modeling.create_dataset_splits import parse_text_columns


FIELDNAMES = ["title", "abstract", "keywords", "primary_domain", "doi"]


def write_split_source_csv(path: Path) -> None:
    rows = []
    for label in ["Health Sciences", "Physical Sciences"]:
        for index in range(12):
            rows.append(
                {
                    "title": f"{label} publication {index}",
                    "abstract": f"{label} abstract {index}",
                    "keywords": f"{label}; sri lanka",
                    "primary_domain": label,
                    "doi": f"10.1000/{label[:3].lower()}{index}",
                }
            )

    rows.extend(
        [
            {
                "title": "Blank label row",
                "abstract": "This row should be dropped",
                "keywords": "",
                "primary_domain": "",
                "doi": "10.1000/blank-label",
            },
            {
                "title": "",
                "abstract": "",
                "keywords": "",
                "primary_domain": "Health Sciences",
                "doi": "10.1000/blank-text",
            },
        ]
    )

    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_create_dataset_splits_writes_stratified_outputs(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    output_dir = tmp_path / "splits"
    write_split_source_csv(input_csv)

    result = create_dataset_splits(
        DatasetSplitConfig(
            input_path=input_csv,
            output_dir=output_dir,
            train_ratio=0.5,
            validation_ratio=0.25,
            test_ratio=0.25,
            min_class_count=4,
            random_state=7,
        )
    )

    train = pd.read_csv(result.train_output)
    validation = pd.read_csv(result.validation_output)
    test = pd.read_csv(result.test_output)
    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))

    assert result.input_rows == 26
    assert result.usable_rows == 24
    assert result.dropped_rows == 2
    assert result.train_rows == 12
    assert result.validation_rows == 6
    assert result.test_rows == 6
    assert result.class_count == 2
    assert list(train.columns[:2]) == ["source_row", "split"]
    assert set(train["split"]) == {"train"}
    assert set(validation["split"]) == {"validation"}
    assert set(test["split"]) == {"test"}
    assert train["primary_domain"].value_counts().to_dict() == {
        "Health Sciences": 6,
        "Physical Sciences": 6,
    }
    assert validation["primary_domain"].value_counts().to_dict() == {
        "Health Sciences": 3,
        "Physical Sciences": 3,
    }
    assert test["primary_domain"].value_counts().to_dict() == {
        "Health Sciences": 3,
        "Physical Sciences": 3,
    }
    assert manifest["split_counts"] == {"test": 6, "train": 12, "validation": 6}
    assert manifest["config"]["random_state"] == 7
    assert (output_dir / "split_summary.csv").exists()


def test_create_dataset_splits_drops_small_classes(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    output_dir = tmp_path / "splits"
    write_split_source_csv(input_csv)

    with input_csv.open("a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writerows(
            [
                {
                    "title": "Tiny class one",
                    "abstract": "Small label",
                    "keywords": "small",
                    "primary_domain": "Tiny Class",
                    "doi": "10.1000/tiny1",
                },
                {
                    "title": "Tiny class two",
                    "abstract": "Small label",
                    "keywords": "small",
                    "primary_domain": "Tiny Class",
                    "doi": "10.1000/tiny2",
                },
            ]
        )

    result = create_dataset_splits(
        DatasetSplitConfig(
            input_path=input_csv,
            output_dir=output_dir,
            train_ratio=0.5,
            validation_ratio=0.25,
            test_ratio=0.25,
            min_class_count=4,
        )
    )

    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))

    assert result.input_rows == 28
    assert result.usable_rows == 24
    assert result.dropped_rows == 4
    assert "Tiny Class" not in manifest["label_counts"]


def test_create_dataset_splits_rejects_invalid_ratios(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    write_split_source_csv(input_csv)

    with pytest.raises(ValueError, match="ratios must sum"):
        create_dataset_splits(
            DatasetSplitConfig(
                input_path=input_csv,
                output_dir=tmp_path / "splits",
                train_ratio=0.8,
                validation_ratio=0.2,
                test_ratio=0.2,
            )
        )


def test_parse_text_columns_requires_at_least_one_column():
    assert parse_text_columns("title, abstract") == ("title", "abstract")

    with pytest.raises(Exception, match="at least one text column"):
        parse_text_columns(" , ")
