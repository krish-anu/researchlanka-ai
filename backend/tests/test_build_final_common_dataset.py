"""Tests for final common dataset cleanup."""

import pandas as pd

from src.pipeline.build_final_common_dataset import (
    build_final_common_dataset,
    build_count_audit_rows,
    clean_final_dataset,
    final_inclusion_mask,
    normalize_funder_identifier,
    repository_review_mask,
    split_reference_payload,
    verified_ownership_mask,
)


def test_normalize_funder_identifier_extracts_doi_and_ror_values():
    value = (
        '{"asserted-by": "publisher", "id": "10.13039/100008968", "id-type": "DOI"}; '
        "{'id': 'https://ror.org/057p7e749', 'id-type': 'ROR'}; "
        '{"id": "10.13039/100008968", "id-type": "DOI"}'
    )

    assert normalize_funder_identifier(value) == "10.13039/100008968; https://ror.org/057p7e749"


def test_split_reference_payload_keeps_semicolon_inside_json_string():
    value = (
        '{"DOI": "10.1000/a", "article-title": "One; still one"}; '
        '{"DOI": "10.1000/b", "year": "2020"}'
    )

    assert split_reference_payload(value) == [
        '{"DOI": "10.1000/a", "article-title": "One; still one"}',
        '{"DOI": "10.1000/b", "year": "2020"}',
    ]


def test_clean_final_dataset_applies_last_26_column_decisions():
    df = pd.DataFrame(
        {
            "doi": ["10.1000/test"],
            "source_dataset": ["openalex; crossref"],
            "source_record_id": ["10.1000/test"],
            "cited_by_count": ["5"],
            "is_referenced_by_count": ["17"],
            "reference_count": ["12"],
            "referenced_works_count": ["15"],
            "references_json": ['{"DOI": "10.1000/ref"}'],
            "concepts": ["Medicine; Medicine; Biology"],
            "topics": ["Topic A; Topic A"],
            "funder_name": ["Fund A; Fund A"],
            "funder_doi": ["https://doi.org/10.13039/100008968; 10.13039/100008968"],
            "funder_id": ['{"id": "https://ror.org/057p7e749", "id-type": "ROR"}'],
            "funder_award": ["A1; A1"],
            "event_name": ["Conference"],
            "event_acronym": ["CONF"],
            "event_location": ["Colombo"],
            "event_start_date": ["2024-01-01"],
            "event_end_date": ["2024-01-02"],
            "event_sponsor": ["Sponsor"],
            "source_set_specs": ["set1; set1; set2"],
            "raw_identifiers": ["https://doi.org/10.1000/test; https://doi.org/10.1000/test"],
            "raw_source_json": ['{"raw": true}'],
        }
    )

    cleaned = clean_final_dataset(df)

    assert "citation_count" not in cleaned.columns
    assert cleaned.loc[0, "reference_count"] == 12
    assert cleaned.loc[0, "citation_count_difference_oa_minus_crossref"] == -12
    assert cleaned.loc[0, "citation_count_divergence_flag"]
    assert cleaned.loc[0, "reference_count_difference_oa_minus_crossref"] == 3
    assert cleaned.loc[0, "reference_count_divergence_flag"]
    assert cleaned.loc[0, "concepts"] == "Medicine; Biology"
    assert cleaned.loc[0, "funder_doi"] == "10.13039/100008968"
    assert cleaned.loc[0, "funder_identifier"] == "https://ror.org/057p7e749"
    assert cleaned.loc[0, "source_set_specs"] == "set1; set2"
    assert cleaned.loc[0, "raw_identifiers"] == "10.1000/test"

    for column in [
        "cited_by_count",
        "citation_count",
        "is_referenced_by_count",
        "referenced_works_count",
        "references_json",
        "funder_id",
        "event_name",
        "event_acronym",
        "event_location",
        "event_start_date",
        "event_end_date",
        "event_sponsor",
        "raw_source_json",
    ]:
        assert column not in cleaned.columns


def test_clean_final_dataset_applies_columns_26_50_decisions():
    df = pd.DataFrame(
        {
            "doi": ["10.1000/test"],
            "source_dataset": ["openalex"],
            "source_record_id": ["10.1000/test"],
            "journal": ["Ceylon Medical Journal"],
            "container_title": ["Ceylon Medical Journal"],
            "source_name": ["Ceylon Medical Journal"],
            "page": ["1-6"],
            "first_page": ["1"],
            "last_page": ["6"],
            "rights": ["This content is protected by copyright."],
            "editors": ["An Editor"],
            "publisher_location": ["Cham"],
            "publisher": ["Springer"],
        }
    )

    cleaned = clean_final_dataset(df)

    for column in [
        "container_title",
        "source_name",
        "page",
        "rights",
        "editors",
        "publisher_location",
    ]:
        assert column not in cleaned.columns

    # The surviving fields must keep the information the dropped ones carried.
    assert cleaned.loc[0, "journal"] == "Ceylon Medical Journal"
    assert cleaned.loc[0, "first_page"] == "1"
    assert cleaned.loc[0, "last_page"] == "6"
    assert cleaned.loc[0, "publisher"] == "Springer"


def test_clean_final_dataset_applies_columns_1_25_decisions():
    df = pd.DataFrame(
        {
            "source_dataset": ["openalex"],
            "source_institution_id": ["uom"],
            "source_record_id": ["https://openalex.org/W1"],
            "source_datestamp": ["2026-02-15T05:19:04Z"],
            "openalex_id": ["https://openalex.org/W1"],
            "doi": ["10.1000/test"],
            "url": ["https://doi.org/10.1000/test"],
            "landing_page_url": ["https://doi.org/10.1000/test"],
            "pdf_url": ["https://example.test/paper.pdf"],
            "title": ["Test publication"],
            "subtitle": ["A subtitle"],
            "original_title": ["Test publication"],
            "abstract": ["An abstract"],
            "keywords": ["keyword a; keyword b"],
            "publication_year": ["2024"],
            "publication_date": ["2024-01-01"],
            "created_date": ["2023-12-01"],
            "published_date": ["2024-01-01"],
            "type": ["article"],
            "subtype": ["preprint"],
            "publication_type": ["article"],
            "authors": ["A. Author"],
            "author_count": ["1"],
            "author_names": ["A. Author"],
            "author_affiliations": ["University of Moratuwa"],
        }
    )

    cleaned = clean_final_dataset(df)

    for column in [
        "landing_page_url",
        "subtitle",
        "original_title",
        "created_date",
        "published_date",
        "subtype",
        "publication_type",
        "author_names",
    ]:
        assert column not in cleaned.columns

    # The surviving fields keep the analysis-ready value from each dropped duplicate group.
    assert cleaned.loc[0, "url"] == "https://doi.org/10.1000/test"
    assert cleaned.loc[0, "publication_date"] == "2024-01-01"
    assert cleaned.loc[0, "type"] == "article"
    assert cleaned.loc[0, "authors"] == "A. Author"


def test_build_count_audit_rows_preserves_source_specific_counts():
    df = pd.DataFrame(
        {
            "doi": ["10.1000/test"],
            "source_dataset": ["openalex; crossref"],
            "source_record_id": ["10.1000/test"],
            "title": ["Test publication"],
            "cited_by_count": ["5"],
            "is_referenced_by_count": ["17"],
            "reference_count": ["12"],
            "referenced_works_count": ["15"],
        }
    )

    rows = build_count_audit_rows(df)

    assert len(rows) == 1
    assert rows[0]["publication_key"] == "doi:10.1000/test"
    assert rows[0]["citation_count"] == 5
    assert rows[0]["is_referenced_by_count"] == 17
    assert rows[0]["reference_count"] == 12
    assert rows[0]["referenced_works_count"] == 15
    assert rows[0]["citation_count_difference_oa_minus_crossref"] == -12
    assert rows[0]["reference_count_difference_oa_minus_crossref"] == 3


def test_build_final_common_dataset_writes_sidecars(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "final.csv"
    references_csv = tmp_path / "references.csv"
    count_audit_csv = tmp_path / "count_audit.csv"
    summary_csv = tmp_path / "summary.csv"
    review_csv = tmp_path / "review.csv"
    excluded_csv = tmp_path / "excluded.csv"
    verified_csv = tmp_path / "verified.csv"

    pd.DataFrame(
        {
            "source_dataset": ["crossref", "openalex", "crossref"],
            "source_record_id": ["10.1000/test", "10.1000/review", "10.1000/excluded"],
            "doi": ["10.1000/test", "10.1000/review", "10.1000/excluded"],
            "title": ["Test publication", "Review publication", "Excluded publication"],
            "cited_by_count": ["3", pd.NA, pd.NA],
            "is_referenced_by_count": ["3", pd.NA, pd.NA],
            "reference_count": ["1", pd.NA, pd.NA],
            "referenced_works_count": [pd.NA, pd.NA, pd.NA],
            "references_json": [
                '{"DOI": "10.1000/ref", "article-title": "Reference", "author": "A.", "year": "2020"}',
                pd.NA,
                pd.NA,
            ],
            "ownership_decision": ["INCLUDE", "REVIEW", "EXCLUDE"],
            "ownership_class": [
                "SL_OWNED_INTERNATIONAL",
                "FIRST_AUTHOR_ONLY_LK_EVIDENCE",
                "FOREIGN_PROJECT_WITH_SL_PARTICIPATION",
            ],
            "ownership_confidence": ["MEDIUM", "LOW", "MEDIUM"],
            "ownership_reason": ["LK corresponding author.", "First author only.", "Foreign lead."],
            "ownership_evidence": [
                "crossref:explicit_corresponding_or_project_lead_affiliation",
                "openalex:first_author_affiliation_countries",
                "crossref:explicit_corresponding_or_project_lead_affiliation",
            ],
            "lead_country": ["LK", "LK", "AU"],
            "needs_manual_review": [False, True, False],
            "ownership_policy_version": ["1.0", "1.0", "1.0"],
            "funder_id": [pd.NA, pd.NA, pd.NA],
            "raw_source_json": [pd.NA, pd.NA, pd.NA],
        }
    ).to_csv(input_csv, index=False)

    cleaned, reference_rows, count_audit_rows = build_final_common_dataset(
        input_csv,
        output_csv,
        references_csv,
        count_audit_csv,
        summary_csv,
        review_csv=review_csv,
        excluded_csv=excluded_csv,
        verified_csv=verified_csv,
    )

    references = pd.read_csv(references_csv)
    count_audit = pd.read_csv(count_audit_csv)

    assert reference_rows == 1
    assert count_audit_rows == 1
    assert len(cleaned) == 1
    assert cleaned.loc[0, "ownership_decision"] == "INCLUDE"
    assert output_csv.exists()
    assert count_audit_csv.exists()
    assert summary_csv.exists()
    assert len(pd.read_csv(review_csv)) == 1
    assert len(pd.read_csv(excluded_csv)) == 1
    assert len(pd.read_csv(verified_csv)) == 1
    assert "is_referenced_by_count" not in cleaned.columns
    assert "citation_count" not in cleaned.columns
    assert "referenced_works_count" not in cleaned.columns
    assert references.loc[0, "publication_key"] == "doi:10.1000/test"
    assert references.loc[0, "reference_doi"] == "10.1000/ref"
    assert references.loc[0, "reference_title"] == "Reference"
    assert count_audit.loc[0, "publication_key"] == "doi:10.1000/test"
    assert count_audit.loc[0, "is_referenced_by_count"] == 3


def test_verified_ownership_mask_requires_complete_lk_policy_evidence():
    df = pd.DataFrame(
        {
            "ownership_decision": ["INCLUDE", "INCLUDE", "INCLUDE", "INCLUDE"],
            "ownership_confidence": ["MEDIUM", "MEDIUM", "MEDIUM", "MEDIUM"],
            "needs_manual_review": [False, False, False, False],
            "lead_country": ["LK", "AU", "LK", "LK"],
            "ownership_reason": ["LK corresponding author.", "Foreign lead.", "", "LK lead."],
            "ownership_evidence": [
                "crossref:explicit_corresponding_or_project_lead_affiliation",
                "crossref:explicit_corresponding_or_project_lead_affiliation",
                "crossref:explicit_corresponding_or_project_lead_affiliation",
                "crossref:explicit_corresponding_or_project_lead_affiliation",
            ],
            "ownership_policy_version": ["1.0", "1.0", "1.0", "legacy"],
        }
    )

    assert verified_ownership_mask(df).tolist() == [True, False, False, False]


def test_final_inclusion_can_add_repository_review_rows():
    df = pd.DataFrame(
        {
            "source_dataset": [
                "openalex",
                "repositories_combined",
                "openalex; repositories_combined",
                "sljol",
            ],
            "ownership_decision": ["INCLUDE", "REVIEW", "REVIEW", "REVIEW"],
            "ownership_class": [
                "SL_DOMESTIC",
                "REPOSITORY_ONLY_EVIDENCE",
                "REPOSITORY_ONLY_EVIDENCE",
                "SLJOL_VENUE_ONLY_EVIDENCE",
            ],
            "ownership_confidence": ["MEDIUM", "LOW", "LOW", "LOW"],
            "needs_manual_review": [False, True, True, True],
            "lead_country": ["LK", pd.NA, pd.NA, pd.NA],
            "ownership_reason": [
                "LK corresponding author.",
                "Repository-only evidence requires review.",
                "Repository-only evidence requires review.",
                "Venue-only evidence requires review.",
            ],
            "ownership_evidence": [
                "openalex:corresponding_author_countries",
                "repositories_combined:source_provenance_only",
                "repositories_combined:source_provenance_only",
                "sljol:source_provenance_only",
            ],
            "ownership_policy_version": ["1.0", "1.0", "1.0", "1.0"],
        }
    )

    assert repository_review_mask(df).tolist() == [False, True, True, False]
    assert final_inclusion_mask(df).tolist() == [True, False, False, False]
    assert final_inclusion_mask(
        df,
        include_repository_review_records=True,
    ).tolist() == [True, True, True, False]


def test_malformed_include_rows_go_to_review_sidecar(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "final.csv"
    references_csv = tmp_path / "references.csv"
    count_audit_csv = tmp_path / "count_audit.csv"
    summary_csv = tmp_path / "summary.csv"
    review_csv = tmp_path / "review.csv"
    excluded_csv = tmp_path / "excluded.csv"
    verified_csv = tmp_path / "verified.csv"

    pd.DataFrame(
        {
            "source_dataset": ["crossref"],
            "source_record_id": ["10.1000/malformed"],
            "doi": ["10.1000/malformed"],
            "title": ["Malformed ownership row"],
            "ownership_decision": ["INCLUDE"],
            "ownership_class": ["SL_OWNED_INTERNATIONAL"],
            "ownership_confidence": ["MEDIUM"],
            "ownership_reason": [""],
            "ownership_evidence": [""],
            "lead_country": [""],
            "needs_manual_review": [False],
            "ownership_policy_version": ["1.0"],
        }
    ).to_csv(input_csv, index=False)

    final, _reference_rows, _count_audit_rows = build_final_common_dataset(
        input_csv,
        output_csv,
        references_csv,
        count_audit_csv,
        summary_csv,
        review_csv=review_csv,
        excluded_csv=excluded_csv,
        verified_csv=verified_csv,
    )

    assert len(final) == 0
    assert len(pd.read_csv(review_csv)) == 1
    assert len(pd.read_csv(excluded_csv)) == 0
