"""Tests for model-ready publication text extraction scripts."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.extraction.extract_publication_abstracts_for_model import (
    clean_abstract,
    extract_abstracts,
)
from scripts.extraction.build_publication_tfidf_features import (
    build_tfidf_features,
    tokenize_text,
)
from scripts.extraction.extract_publication_keywords_for_model import (
    extract_keywords,
    normalize_keywords,
    split_keywords,
)
from scripts.extraction.extract_publication_titles_for_model import (
    clean_title,
    extract_titles,
    normalize_title,
)


FIELDNAMES = [
    "title",
    "abstract",
    "keywords",
    "publication_year",
    "type",
    "journal",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "doi",
    "openalex_id",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
]


def write_publications_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_extract_publication_titles_for_model_keeps_model_context(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    write_publications_csv(
        input_csv,
        [
            {
                "title": " Machine Learning for Tea ",
                "abstract": "A study abstract.",
                "keywords": "AI; tea",
                "publication_year": "2024",
                "type": "journal-article",
                "journal": "Example Journal",
                "primary_topic": "Agriculture",
                "primary_field": "Computer Science",
                "primary_subfield": "AI",
                "primary_domain": "Science",
                "doi": "10.1000/example",
                "openalex_id": "https://openalex.org/W1",
                "source_dataset": "openalex",
                "source_institution_id": "uoc",
                "source_record_id": "record-1",
            },
            {
                "title": "machine-learning for tea",
                "abstract": "Duplicate title variant.",
                "keywords": "AI",
                "publication_year": "2024",
            },
            {"title": "", "publication_year": "2025"},
        ],
    )

    rows = extract_titles(input_csv, deduplicate_titles=True)

    assert len(rows) == 1
    assert rows[0]["title_clean"] == "Machine Learning for Tea"
    assert rows[0]["title_normalized"] == "machine learning for tea"
    assert rows[0]["primary_topic"] == "Agriculture"
    assert clean_title("<i>Tea &amp;amp; Rice</i>") == "Tea & Rice"
    assert normalize_title("Tea & Rice!") == "tea rice"


def test_extract_publication_abstracts_for_model_cleans_html_and_deduplicates(
    tmp_path: Path,
):
    input_csv = tmp_path / "publications.csv"
    write_publications_csv(
        input_csv,
        [
            {
                "title": "First paper",
                "abstract": "<jats:p>Sri&nbsp;Lanka &amp;amp; AI study.</jats:p>",
                "keywords": "AI; Sri Lanka",
                "publication_year": "2024",
                "doi": "10.1000/abstract",
            },
            {
                "title": "Second paper",
                "abstract": "Sri Lanka & AI study.",
                "keywords": "AI",
                "publication_year": "2024",
                "doi": "10.1000/duplicate-abstract",
            },
            {"title": "No abstract", "abstract": "", "publication_year": "2024"},
        ],
    )

    rows = extract_abstracts(input_csv, deduplicate_abstracts=True)

    assert len(rows) == 1
    assert rows[0]["abstract_clean"] == "Sri Lanka & AI study."
    assert rows[0]["abstract_normalized"] == "sri lanka ai study"
    assert rows[0]["title"] == "First paper"
    assert clean_abstract("<p>Tea&nbsp;research</p>") == "Tea research"


def test_extract_publication_keywords_for_model_normalizes_keyword_sets(
    tmp_path: Path,
):
    input_csv = tmp_path / "publications.csv"
    write_publications_csv(
        input_csv,
        [
            {
                "title": "Keyword paper",
                "abstract": "A study abstract.",
                "keywords": " AI ; ai ; Machine   Learning, Tea|Tea ",
                "publication_year": "2024",
                "doi": "10.1000/keywords",
            },
            {
                "title": "Duplicate keyword paper",
                "abstract": "Another abstract.",
                "keywords": "ai; machine learning; tea",
                "publication_year": "2025",
            },
            {"title": "No keywords", "keywords": "", "publication_year": "2026"},
        ],
    )

    rows = extract_keywords(input_csv, deduplicate_keyword_sets=True)

    assert len(rows) == 1
    assert rows[0]["keywords_clean"] == "AI; Machine Learning; Tea"
    assert rows[0]["keywords_normalized"] == "ai; machine learning; tea"
    assert rows[0]["keyword_count"] == "3"
    assert rows[0]["abstract"] == "A study abstract."
    assert split_keywords("AI; ai, Tea|Tea") == ["AI", "Tea"]
    assert normalize_keywords("AI; Machine   Learning") == "ai; machine learning"


def test_build_publication_tfidf_features_creates_sparse_feature_rows(
    tmp_path: Path,
):
    input_csv = tmp_path / "publications.csv"
    write_publications_csv(
        input_csv,
        [
            {
                "title": "Machine learning for tea disease detection",
                "abstract": "Tea disease detection using machine learning.",
                "keywords": "AI; tea",
                "publication_year": "2024",
                "doi": "10.1000/tea",
            },
            {
                "title": "Machine learning for rice disease detection",
                "abstract": "Rice disease detection using machine learning.",
                "keywords": "AI; rice",
                "publication_year": "2025",
                "doi": "10.1000/rice",
            },
            {"title": "", "abstract": "", "keywords": "", "publication_year": "2026"},
        ],
    )

    feature_rows, vocabulary_rows, summary_rows = build_tfidf_features(
        input_csv,
        max_features=20,
        min_df=1,
        max_df=1.0,
        ngram_max=2,
        top_features_per_record=4,
    )

    terms = {row["term"] for row in vocabulary_rows}
    summary = {row["metric"]: row["value"] for row in summary_rows}

    assert len(feature_rows) == 2
    assert "tea" in terms
    assert "machine learning" in terms
    assert "for" not in terms
    assert feature_rows[0]["record_number"] == "1"
    assert feature_rows[0]["doi"] == "10.1000/tea"
    assert "tea:" in feature_rows[0]["tfidf_features"]
    assert summary["documents_with_text"] == "2"
    assert summary["normalization"] == "l2"
    assert tokenize_text("<p>Tea &amp;amp; Rice!</p>") == ["tea", "rice"]
