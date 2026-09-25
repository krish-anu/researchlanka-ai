from src.pipeline.incremental_update import filter_rows_for_database


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
