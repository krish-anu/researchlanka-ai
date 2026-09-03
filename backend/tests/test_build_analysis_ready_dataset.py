"""Tests for analysis-ready preprocessing."""

import pandas as pd

from src.pipeline.build_analysis_ready_dataset import (
    build_analysis_ready_dataset,
    build_analysis_ready_dataframe,
    normalize_author_name,
    normalize_identifier_cell,
    normalize_keywords_for_search,
    normalize_search_text,
)


def test_normalize_search_text_and_keywords():
    assert normalize_search_text("  Sri   Lanka Research ") == "sri lanka research"
    assert normalize_search_text("") is pd.NA
    assert normalize_keywords_for_search("AI; ai ; Machine   Learning") == "ai; machine learning"


def test_normalize_identifier_cell_handles_common_ids():
    assert normalize_identifier_cell("doi", "https://doi.org/10.1000/ABC.") == "10.1000/abc"
    assert normalize_identifier_cell("url", "https://doi.org/10.35609/gjbssr.2019.7.3(5)") == (
        "https://doi.org/10.35609/gjbssr.2019.7.3(5)"
    )
    assert normalize_identifier_cell("author_orcids", "0000-0002-1825-0097") == (
        "https://orcid.org/0000-0002-1825-0097"
    )
    assert normalize_identifier_cell("issn", "1234567X") == "1234-567X"


def test_normalize_author_name_handles_simple_cases():
    assert normalize_author_name("SILVA, KALINGA") == "Kalinga Silva"
    assert normalize_author_name("  Kalinga   Tudor Silva ") == "Kalinga Tudor Silva"


def test_build_analysis_ready_dataframe_adds_helper_columns_and_converts_types():
    df = pd.DataFrame(
        {
            "source_dataset": ["openalex"],
            "source_record_id": ["record-1"],
            "doi": ["https://doi.org/10.1000/ABC"],
            "title": [" Test Title "],
            "abstract": [pd.NA],
            "keywords": ["AI; ai"],
            "authors": ["SILVA, KALINGA"],
            "author_orcids": [pd.NA],
            "publication_year": ["2020"],
            "publication_date": ["2020-01-15"],
            "author_count": ["1"],
            "citation_count": ["2"],
            "reference_count": ["3"],
            "citation_count_difference_oa_minus_crossref": ["0"],
            "reference_count_difference_oa_minus_crossref": ["1"],
            "oa_status": [pd.NA],
            "is_oa": ["False"],
            "license": ["CC_BY"],
            "license_url": ["http://creativecommons.org/licenses/by/4.0/"],
            "funder_name": [pd.NA],
            "funder_doi": [pd.NA],
            "funder_identifier": [pd.NA],
            "funder_award": [pd.NA],
            "pdf_url": [pd.NA],
            "article_number": [pd.NA],
        }
    )

    cleaned = build_analysis_ready_dataframe(df)

    assert cleaned.loc[0, "doi"] == "10.1000/abc"
    assert cleaned.loc[0, "title_search_text"] == "test title"
    assert cleaned.loc[0, "abstract_missing_flag"]
    assert cleaned.loc[0, "keywords_search_text"] == "ai"
    assert cleaned.loc[0, "authors_clean"] == "Kalinga Silva"
    assert "publication_year" not in cleaned.columns
    assert cleaned.loc[0, "publication_date"] == "2020-01-15"
    assert "citation_count" not in cleaned.columns
    assert cleaned.loc[0, "oa_status"] == "unknown"
    assert cleaned.loc[0, "is_oa"] is False
    assert cleaned.loc[0, "license"] == "cc-by"
    assert cleaned.loc[0, "license_url"] == "https://creativecommons.org/licenses/by/4.0/"


def test_build_analysis_ready_dataset_writes_separate_issue_files(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "analysis_ready.csv"
    issue_dir = tmp_path / "issues"
    summary_csv = tmp_path / "summary.csv"
    df = pd.DataFrame(
        {
            "source_dataset": ["openalex"],
            "source_record_id": ["record-1"],
            "doi": ["https://doi.org/10.1000/ABC"],
            "title": [" Test Title "],
            "abstract": [pd.NA],
            "keywords": ["AI; ai"],
            "authors": ["SILVA, KALINGA"],
            "author_orcids": [pd.NA],
            "publication_year": ["2020"],
            "publication_date": ["2020-01-15"],
            "author_count": ["1"],
            "citation_count": ["2"],
            "reference_count": ["3"],
            "citation_count_difference_oa_minus_crossref": ["0"],
            "reference_count_difference_oa_minus_crossref": ["1"],
            "oa_status": [pd.NA],
            "is_oa": ["False"],
            "license": ["CC_BY"],
            "license_url": ["http://creativecommons.org/licenses/by/4.0/"],
            "funder_name": [pd.NA],
            "funder_doi": [pd.NA],
            "funder_identifier": [pd.NA],
            "funder_award": [pd.NA],
            "pdf_url": [pd.NA],
            "article_number": [pd.NA],
        }
    )
    df.to_csv(input_csv, index=False)

    cleaned, issue_rows = build_analysis_ready_dataset(input_csv, output_csv, issue_dir, summary_csv)

    assert len(cleaned) == 1
    assert issue_rows > 0
    assert output_csv.exists()
    assert summary_csv.exists()
    assert (issue_dir / "text_issues.csv").exists()
    assert (issue_dir / "identifier_issues.csv").exists()
    assert (issue_dir / "numeric_issues.csv").exists()
    assert (issue_dir / "missingness_issues.csv").exists()
    assert (issue_dir / "author_issues.csv").exists()
    assert (issue_dir / "oa_license_issues.csv").exists()
    assert (issue_dir / "all_preprocessing_issues.csv").exists()
