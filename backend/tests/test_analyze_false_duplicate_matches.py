import pandas as pd

from src.quality.analyze_false_duplicate_matches import (
    analyze_candidate_pairs,
    analyze_same_doi_groups,
)


def test_analyze_candidate_pairs_flags_high_score_doi_disagreement():
    pairs = pd.DataFrame(
        [
            {
                "title1": "Same paper",
                "title2": "Same paper",
                "year1": "2024",
                "year2": "2024",
                "doi1": "https://doi.org/10.1234/one",
                "doi2": "10.1234/two",
                "source1": "openalex",
                "source2": "crossref",
                "final_score": 100,
            },
            {
                "title1": "Additional file 1 of Parent Study",
                "title2": "Additional file 2 of Parent Study",
                "year1": "2024",
                "year2": "2024",
                "doi1": "10.6084/m9.figshare.1",
                "doi2": "10.6084/m9.figshare.2",
                "source1": "openalex",
                "source2": "openalex",
                "final_score": 99.5,
            },
            {
                "title1": "Repository-only title",
                "title2": "Repository-only title",
                "year1": "2022",
                "year2": "2022",
                "doi1": pd.NA,
                "doi2": pd.NA,
                "source1": "repositories_combined",
                "source2": "repositories_combined",
                "final_score": 98,
            },
            {
                "title1": "Known article",
                "title2": "Known article",
                "year1": "2021",
                "year2": "2021",
                "doi1": "10.1000/known",
                "doi2": pd.NA,
                "source1": "openalex",
                "source2": "repositories_combined",
                "final_score": 96,
            },
        ]
    )

    analysis = analyze_candidate_pairs(pairs)

    assert analysis.metrics["candidate_pair_rows"] == 4
    assert analysis.metrics["different_doi_when_both_present"] == 2
    assert analysis.metrics["exact_title_same_year_different_doi"] == 1
    assert analysis.metrics["artifact_title"] == 1
    assert analysis.metrics["neither_doi_present"] == 1
    assert analysis.metrics["one_doi_missing"] == 1
    assert analysis.metrics["score_at_least_99_with_different_doi"] == 2
    assert analysis.metrics["score_at_least_95_with_one_or_no_doi"] == 2


def test_analyze_same_doi_groups_flags_severe_title_and_year_conflicts():
    records = pd.DataFrame(
        [
            {
                "source_dataset": "openalex",
                "source_record_id": "oa-1",
                "doi": "10.1234/shared",
                "title": "Deep learning for crops",
                "publication_year": "2024",
            },
            {
                "source_dataset": "repositories_combined",
                "source_record_id": "repo-1",
                "doi": "https://doi.org/10.1234/shared",
                "title": "Ancient history of coastal trade",
                "publication_year": "2024",
            },
            {
                "source_dataset": "crossref",
                "source_record_id": "cr-1",
                "doi": "10.5678/year",
                "title": "Stable title",
                "publication_year": "2020",
            },
            {
                "source_dataset": "openalex",
                "source_record_id": "oa-2",
                "doi": "10.5678/year",
                "title": "Stable title",
                "publication_year": "2023",
            },
            {
                "source_dataset": "openalex",
                "source_record_id": "oa-3",
                "doi": "10.9999/minor",
                "title": "Same title",
                "publication_year": "2022",
            },
            {
                "source_dataset": "crossref",
                "source_record_id": "cr-3",
                "doi": "10.9999/minor",
                "title": "Same-title",
                "publication_year": "2022",
            },
        ]
    )

    analysis = analyze_same_doi_groups(records)

    assert analysis.metrics["all_rows"] == 6
    assert analysis.metrics["rows_with_doi"] == 6
    assert analysis.metrics["duplicate_doi_groups"] == 3
    assert analysis.metrics["conflicting_doi_groups"] == 2
    assert analysis.metrics["title_conflict_groups"] == 1
    assert analysis.metrics["year_conflict_groups"] == 1
    assert analysis.metrics["title_similarity_below_080"] == 1
    assert analysis.metrics["year_span_greater_than_1"] == 1
    assert analysis.metrics["severe_same_doi_conflict_groups"] == 2
    assert set(analysis.severe_groups["doi"]) == {"10.1234/shared", "10.5678/year"}
