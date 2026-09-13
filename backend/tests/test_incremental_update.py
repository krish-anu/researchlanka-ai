from src.pipeline.incremental_update import filter_rows_for_database


def test_filter_rows_for_database_requires_allowed_label_and_valid_doi() -> None:
    rows = [
        {"ai_classification_label": "AI", "doi": "https://doi.org/10.1000/ABC"},
        {"ai_classification_label": "AI", "doi": ""},
        {"ai_classification_label": "AI", "doi": "not-a-doi"},
        {"ai_classification_label": "NON_AI", "doi": "10.1000/non-ai"},
    ]

    selected = filter_rows_for_database(rows, labels=("AI",))

    assert selected == [{"ai_classification_label": "AI", "doi": "10.1000/abc"}]
