import sys

from src.pipeline import build_ai_publication_dataset, incremental_update
from src.pipeline.incremental_update import filter_rows_for_database
from src.pipeline.refresh_policy import (
    DEFAULT_CONFIDENCE_REVIEW_THRESHOLD,
    DEFAULT_DB_LABELS,
)


def test_filter_rows_for_database_requires_allowed_label_and_valid_doi() -> None:
    rows = [
        {
            "ai_classification_label": "AI",
            "doi": "https://doi.org/10.1000/ABC",
            "ownership_decision": "INCLUDE",
            "ownership_confidence": "HIGH",
            "needs_manual_review": "false",
        },
        {
            "ai_classification_label": "review",
            "doi": "10.1000/review",
            "ownership_decision": "INCLUDE",
            "ownership_confidence": "MEDIUM",
            "needs_manual_review": "false",
        },
        {"ai_classification_label": "AI", "doi": "", "ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
        {"ai_classification_label": "AI", "doi": "not-a-doi", "ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
        {"ai_classification_label": "AI", "doi": "10.1000/excluded", "ownership_decision": "EXCLUDE", "ownership_confidence": "HIGH"},
        {"ai_classification_label": "NON_AI", "doi": "10.1000/non-ai", "ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
    ]

    selected = filter_rows_for_database(rows, labels=("AI", "review"))

    assert [row["doi"] for row in selected] == ["10.1000/abc", "10.1000/review"]


def test_refresh_entry_points_share_policy_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["incremental_update"])
    incremental_args = incremental_update.parse_args()

    monkeypatch.setattr(sys, "argv", ["build_ai_publication_dataset"])
    historical_args = build_ai_publication_dataset.parse_args()

    assert incremental_args.db_labels == DEFAULT_DB_LABELS
    assert historical_args.db_labels == DEFAULT_DB_LABELS
    assert incremental_args.confidence_review_threshold == DEFAULT_CONFIDENCE_REVIEW_THRESHOLD
    assert historical_args.confidence_review_threshold == DEFAULT_CONFIDENCE_REVIEW_THRESHOLD
