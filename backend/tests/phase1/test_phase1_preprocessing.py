"""Phase 1 — preprocessing / text cleaning edge cases."""

from __future__ import annotations

import pandas as pd
import pytest

from src.preprocessing.text_cleaning import (
    CUSTOM_STOP_WORDS,
    boilerplate_hit_count,
    clean_text_series,
    cleaning_report,
    ngram_contains_stopword,
    non_latin_char_ratio,
    strip_boilerplate,
    strip_non_latin,
)


pytestmark = [pytest.mark.phase1, pytest.mark.preprocessing]


@pytest.mark.edge_case
def test_strip_non_latin_removes_tamil_keeps_english():
    mixed = "Machine learning கற்றல் for tea"
    cleaned = strip_non_latin(mixed)
    assert "Machine learning" in cleaned
    assert "கற்றல்" not in cleaned
    assert non_latin_char_ratio(mixed) > 0
    assert non_latin_char_ratio(cleaned) == 0


@pytest.mark.edge_case
def test_strip_boilerplate_placeholders():
    assert strip_boilerplate("editorial note").strip() == ""
    cleaned = strip_boilerplate("abstract not available real abstract text")
    assert "real abstract text" in cleaned
    assert "abstract not available" not in cleaned.lower()


@pytest.mark.edge_case
def test_clean_text_series_collapses_and_strips():
    series = pd.Series(
        [
            "  Tea   disease\n detection  ",
            "abstract not available",
            None,
            "கக English kept",
        ]
    )
    cleaned = clean_text_series(series)
    assert cleaned.iloc[0] == "Tea disease detection"
    assert cleaned.iloc[1].strip() == ""
    assert cleaned.iloc[2] == ""
    assert "English kept" in cleaned.iloc[3]
    assert "கக" not in cleaned.iloc[3]


def test_cleaning_report_counts_affected_rows():
    series = pd.Series(["normal text", "abstract available", "கற்றல்"])
    report = cleaning_report(series)
    assert report["n_rows"] == 3
    assert report["rows_with_boilerplate_phrases"] >= 1
    assert report["rows_with_non_latin_chars"] >= 1
    assert boilerplate_hit_count(series) >= 1


@pytest.mark.edge_case
def test_ngram_stopword_filter_drops_function_phrases():
    assert ngram_contains_stopword("of science") is True
    assert ngram_contains_stopword("sri lanka") is True
    assert ngram_contains_stopword("machine learning") is False
    assert "study" in CUSTOM_STOP_WORDS
