import pandas as pd

from src.quality.analyze_missed_duplicate_records import analyze_missed_duplicates


def test_analyze_missed_duplicates_finds_title_year_first_author_groups():
    records = pd.DataFrame(
        [
            {
                "source_dataset": "repositories_combined",
                "source_record_id": "repo-1",
                "doi": pd.NA,
                "title": "Shared repository title",
                "publication_year": "2024",
                "authors": "A. Author; B. Writer",
                "author_names": pd.NA,
                "journal": "Local Journal",
                "container_title": pd.NA,
                "url": "https://repo.example/1",
            },
            {
                "source_dataset": "openalex",
                "source_record_id": "oa-1",
                "doi": "10.1234/preprint",
                "title": "Shared repository title",
                "publication_year": "2024",
                "authors": pd.NA,
                "author_names": "A Author; B Writer",
                "journal": pd.NA,
                "container_title": "Local Journal",
                "url": "https://example.org/2",
            },
        ]
    )

    analysis = analyze_missed_duplicates(records)

    assert analysis.metrics["missed_duplicate_candidate_groups"] == 1
    assert analysis.metrics["title_year_first_author_groups"] == 1
    row = analysis.candidate_groups.loc[0]
    assert row["review_method"] == "title_year_first_author"
    assert row["doi_state"] == "some_missing"
    assert row["input_row_numbers"] == "1; 2"


def test_analyze_missed_duplicates_finds_leftover_duplicate_doi_groups():
    records = pd.DataFrame(
        [
            {
                "source_dataset": "crossref",
                "source_record_id": "cr-1",
                "doi": "10.9999/shared",
                "title": "Crossref title",
                "publication_year": "2023",
                "authors": "A. Author",
                "author_names": "A. Author",
                "journal": pd.NA,
                "container_title": pd.NA,
                "url": pd.NA,
            },
            {
                "source_dataset": "openalex",
                "source_record_id": "oa-1",
                "doi": "https://doi.org/10.9999/shared",
                "title": "OpenAlex title",
                "publication_year": "2023",
                "authors": "A. Author",
                "author_names": "A. Author",
                "journal": pd.NA,
                "container_title": pd.NA,
                "url": pd.NA,
            },
        ]
    )

    analysis = analyze_missed_duplicates(records)

    assert analysis.metrics["duplicate_doi_after_dedup_groups"] == 1
    row = analysis.candidate_groups.loc[0]
    assert row["review_method"] == "duplicate_doi_after_dedup"
    assert row["confidence"] == "high"
    assert row["doi_state"] == "same_doi"


def test_analyze_missed_duplicates_finds_near_year_title_author_groups():
    records = pd.DataFrame(
        [
            {
                "source_dataset": "repositories_combined",
                "source_record_id": "repo-1",
                "doi": pd.NA,
                "title": "Year drift title",
                "publication_year": "2022",
                "authors": "A. Author",
                "author_names": pd.NA,
                "journal": pd.NA,
                "container_title": pd.NA,
                "url": pd.NA,
            },
            {
                "source_dataset": "repositories_combined",
                "source_record_id": "repo-2",
                "doi": pd.NA,
                "title": "Year drift title",
                "publication_year": "2023",
                "authors": "A Author",
                "author_names": pd.NA,
                "journal": pd.NA,
                "container_title": pd.NA,
                "url": pd.NA,
            },
        ]
    )

    analysis = analyze_missed_duplicates(records)

    assert analysis.metrics["title_first_author_near_year_groups"] == 1
    row = analysis.candidate_groups.loc[0]
    assert row["review_method"] == "title_first_author_near_year"
    assert row["publication_year_span"] == 1
