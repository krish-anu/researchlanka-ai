"""Phase 1 — cleaning function edge cases."""

from __future__ import annotations

import math

import pytest

from research_analytics.cleaning import (
    clean_record,
    is_valid_doi,
    normalize_doi,
    normalize_list_like,
    normalize_publication_date,
    normalize_publication_year,
    normalize_text,
    normalize_title,
    normalize_title_key,
)
from research_analytics.config import CleaningConfig


pytestmark = [pytest.mark.phase1, pytest.mark.cleaning]


@pytest.mark.edge_case
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("nan", None),
        (math.nan, None),
        ("https://doi.org/10.1000/ABC", "10.1000/abc"),
        ("DOI: 10.1000/ABC.", "10.1000/abc"),
        ("http://dx.doi.org/10.1000/xyz;", "10.1000/xyz"),
        ("10.1000/abc (online)", "10.1000/abc(online"),
    ],
)
def test_normalize_doi_edge_cases(raw, expected):
    assert normalize_doi(raw) == expected


@pytest.mark.edge_case
def test_invalid_doi_rejected():
    assert is_valid_doi("not-a-doi") is False
    assert is_valid_doi("10.abc/missing-digits") is False
    assert is_valid_doi("10.1000/valid") is True


@pytest.mark.edge_case
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("  Machine   Learning\nfor  Tea  ", "Machine Learning for Tea"),
        ("Title<sub>2</sub>O", "Title2O"),
        ("A &amp;amp; B", "A & B"),
        ("<i>Italic</i> title", "Italic title"),
        ("Hello , world !", "Hello, world!"),
    ],
)
def test_normalize_title_edge_cases(raw, expected):
    assert normalize_title(raw) == expected


@pytest.mark.edge_case
def test_normalize_title_key_casefolds_and_strips_punctuation():
    assert normalize_title_key("Machine Learning: Tea!") == "machine learning tea"
    assert normalize_title_key("  ") is None


@pytest.mark.edge_case
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("2024", "2024"),
        ("2024-03", "2024-03"),
        ("2024-03-15", "2024-03-15"),
        ("2024-03-15T10:00:00", "2024-03-15"),
        ({"date-parts": [[2023, 5, 1]]}, "2023-05-01"),
        ("not-a-date", None),
        ("", None),
    ],
)
def test_normalize_publication_date_edge_cases(raw, expected):
    assert normalize_publication_date(raw) == expected


@pytest.mark.edge_case
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("2024", 2024),
        ("2024-06-01", 2024),
        ("published in 2019 somewhere", 2019),
        ("no-year", None),
        ("", None),
    ],
)
def test_normalize_publication_year_edge_cases(raw, expected):
    assert normalize_publication_year(raw) == expected


@pytest.mark.edge_case
def test_normalize_text_collapses_whitespace():
    assert normalize_text("  a \t b\n c  ") == "a b c"
    assert normalize_text("   ") is None


@pytest.mark.edge_case
def test_normalize_list_like_handles_null_markers_and_separators():
    assert normalize_list_like(None) == []
    assert normalize_list_like("") == []
    assert normalize_list_like("A; B; ; C", separators=(";",)) == ["A", "B", "C"]
    assert normalize_list_like(["A", "", None, "B"]) == ["A", "None", "B"]
    assert normalize_list_like(["A", "B"]) == ["A", "B"]
    # Comma inside an institution name must stay intact when separators are ";" only.
    assert normalize_list_like("Eastern University, Sri Lanka", separators=(";",)) == [
        "Eastern University, Sri Lanka"
    ]


def test_clean_record_applies_configured_rules_and_provenance():
    config = CleaningConfig(
        normalize_doi=True,
        normalize_title=True,
        normalize_publication_dates=True,
        normalize_author_names=True,
        normalize_institutions=True,
    )
    cleaned = clean_record(
        {
            "doi": "https://doi.org/10.1000/ABC",
            "title": "  Tea <i>Disease</i> Detection  ",
            "publication_date": "2024-01-02T00:00:00",
            "authors": "A. Author; B. Author",
            "institutions": "University of Colombo; University of Peradeniya",
        },
        config,
    )
    assert cleaned["doi"] == "10.1000/abc"
    assert cleaned["title"] == "Tea Disease Detection"
    assert cleaned["normalized_title"] == "tea disease detection"
    assert cleaned["publication_year"] == 2024
    assert cleaned["processing_status"] == "cleaned"
    assert "normalize_doi" in cleaned["_provenance"]["cleaning_rules_applied"]
