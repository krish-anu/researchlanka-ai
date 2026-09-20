"""Unit tests — preprocessing (text cleaning + OpenAlex helpers).

Test Plan: 3.1.2 Data Collection and ETL Testing (preprocessing stage)
These are focused unit tests for ResearchLanka text/publication preprocessing.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.preprocessing.openalex_normalizer import (
    normalize_publication_date,
    normalize_publication_year,
)
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


pytestmark = [pytest.mark.sw_testing, pytest.mark.preprocessing]


def test_strip_non_latin_removes_tamil_keeps_english_content():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: strip_non_latin keeps English tokens and removes Tamil script.
    """
    mixed = "Machine learning கற்றல் for tea"
    cleaned = strip_non_latin(mixed)
    assert "Machine learning" in cleaned
    assert "கற்றல்" not in cleaned
    assert non_latin_char_ratio(mixed) > 0
    assert non_latin_char_ratio(cleaned) == 0


def test_strip_non_latin_removes_sinhala_script_runs():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: Sinhala script is stripped the same way as Tamil.
    """
    mixed = "Climate study මාතෘකාව results"
    cleaned = strip_non_latin(mixed)
    assert "Climate study" in cleaned
    assert "මාතෘකාව" not in cleaned


def test_strip_boilerplate_removes_placeholder_abstract_phrases():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: metadata placeholder phrases are removed from abstract-like text.
    """
    assert strip_boilerplate("editorial note").strip() == ""
    cleaned = strip_boilerplate("abstract not available real abstract text")
    assert "real abstract text" in cleaned
    assert "abstract not available" not in cleaned.casefold()


def test_clean_text_series_collapses_whitespace_and_strips_noise():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: clean_text_series collapses whitespace and clears placeholder rows.
    """
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


def test_cleaning_report_counts_boilerplate_and_non_latin_rows():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: cleaning_report counts rows affected by boilerplate / non-Latin text.
    """
    series = pd.Series(["normal text", "abstract available", "கற்றல்"])
    report = cleaning_report(series)
    assert report["n_rows"] == 3
    assert report["rows_with_boilerplate_phrases"] >= 1
    assert report["rows_with_non_latin_chars"] >= 1
    assert boilerplate_hit_count(series) >= 1


def test_ngram_stopword_filter_drops_function_phrases_keeps_topic_phrases():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: NMF stopword n-grams drop function phrases but keep topic phrases.
    """
    assert ngram_contains_stopword("of science") is True
    assert ngram_contains_stopword("sri lanka") is True
    assert ngram_contains_stopword("machine learning") is False
    assert "study" in CUSTOM_STOP_WORDS


def test_openalex_normalize_publication_year_from_int_and_digit_string():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: OpenAlex year normalizer accepts ints and digit strings only.
    """
    assert normalize_publication_year(2020) == 2020
    assert normalize_publication_year("2021") == 2021
    assert normalize_publication_year("2021-06-15") is None
    assert normalize_publication_year(None) is None


def test_openalex_normalize_publication_date_returns_iso_date_or_none():
    """
    Test Plan: 3.1.2 Data Collection and ETL Testing
    Unit: OpenAlex date normalizer returns ISO YYYY-MM-DD when parseable.
    """
    assert normalize_publication_date("2022-03-01") == "2022-03-01"
    assert normalize_publication_date(None) is None
    assert normalize_publication_date("not-a-date") is None
