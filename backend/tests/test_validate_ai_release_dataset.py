from __future__ import annotations

import pandas as pd

from src.pipeline import incremental_update
from src.pipeline.incremental_update import apply_ai_classification
from src.quality.validate_ai_release_dataset import (
    AIReleaseValidationConfig,
    validate_ai_release_dataset,
)


def test_validate_ai_release_dataset_writes_release_reports(tmp_path):
    input_path = tmp_path / "ai_only.csv"
    output_dir = tmp_path / "report"
    pd.DataFrame(
        [
            {
                "title": "Machine learning for tea",
                "publication_date": "2024-01-01",
                "source_dataset": "openalex",
                "source_record_id": "1",
                "openalex_id": "W1",
                "doi": "10.1/a",
                "sri_lankan_authors": "University of Colombo, Sri Lanka",
                "license": "cc-by",
                "ai_classification_label": "AI",
                "ai_classification_confidence": "0.91",
                "ai_classification_model": "linear_svm",
            },
            {
                "title": "Machine learning for tea",
                "publication_date": "2024-02-01",
                "source_dataset": "openalex",
                "source_record_id": "2",
                "openalex_id": "W2",
                "doi": "10.1/b",
                "sri_lankan_authors": "University of Colombo, Sri Lanka",
                "license": "cc-by",
                "ai_classification_label": "AI",
                "ai_classification_confidence": "0.87",
                "ai_classification_model": "linear_svm",
            },
        ]
    ).to_csv(input_path, index=False)

    summary = validate_ai_release_dataset(
        AIReleaseValidationConfig(input_path=input_path, output_dir=output_dir, current_year=2026)
    )

    assert summary["rows"] == 2
    gates = pd.read_csv(output_dir / "quality_gates.csv")
    duplicate_gate = gates[gates["check"] == "duplicate_candidates"].iloc[0]
    assert duplicate_gate["status"] == "review_required"
    assert duplicate_gate["count"] == 2
    assert (output_dir / "field_completeness.csv").exists()
    assert (output_dir / "distribution_summary.csv").exists()
    assert (output_dir / "README.md").exists()


def test_apply_ai_classification_uses_svm_margin_as_confidence(tmp_path, monkeypatch):
    model_path = tmp_path / "model.joblib"
    model_path.write_text("placeholder", encoding="utf-8")

    class FakeSVM:
        def predict(self, text):
            assert list(text) == ["neural model"]
            return ["AI"]

        def decision_function(self, text):
            return [2.0]

    monkeypatch.setattr(incremental_update.joblib, "load", lambda path: FakeSVM())

    rows = apply_ai_classification(
        [{"title": "neural model"}],
        model_path=model_path,
        text_columns=("title",),
        confidence_review_threshold=None,
    )

    assert rows[0]["ai_classification_label"] == "AI"
    assert rows[0]["ai_classification_confidence"] == "0.880797"
