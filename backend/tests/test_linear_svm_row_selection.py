"""Tests for Linear SVM row selection alignment."""

from __future__ import annotations

import csv
from pathlib import Path

from src.modeling.linear_svm_training import load_training_frame as load_svm_frame
from src.modeling.training import load_training_frame as load_shared_frame


FIELDNAMES = ["title", "abstract", "keywords", "primary_domain"]


def write_row_selection_csv(path: Path) -> None:
    rows = [
        {
            "title": "abstract available",
            "abstract": "editorial",
            "keywords": "",
            "primary_domain": "Life Sciences",
        },
        {
            "title": "Rice field genetics",
            "abstract": "Plant breeding genome study",
            "keywords": "agriculture",
            "primary_domain": "Life Sciences",
        },
        {
            "title": "Bridge load analysis",
            "abstract": "Structural engineering materials",
            "keywords": "civil",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "abstract not available",
            "abstract": "editorial note",
            "keywords": "",
            "primary_domain": "Physical Sciences",
        },
        {
            "title": "Missing label",
            "abstract": "This row should be filtered",
            "keywords": "",
            "primary_domain": "",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_linear_svm_uses_shared_row_selection(tmp_path: Path) -> None:
    input_csv = tmp_path / "publications.csv"
    write_row_selection_csv(input_csv)

    kwargs = {
        "label_column": "primary_domain",
        "text_columns": ["title", "abstract", "keywords"],
        "min_class_count": 2,
        "max_rows": None,
    }
    svm_frame, svm_input_rows, svm_label_counts = load_svm_frame(input_csv, **kwargs)
    shared_frame, shared_input_rows, shared_label_counts = load_shared_frame(
        input_csv,
        **kwargs,
    )

    assert svm_input_rows == shared_input_rows == 5
    assert svm_frame["text"].tolist() == shared_frame["text"].tolist()
    assert svm_frame["label"].tolist() == shared_frame["label"].tolist()
    assert svm_label_counts.to_dict() == shared_label_counts.to_dict()
