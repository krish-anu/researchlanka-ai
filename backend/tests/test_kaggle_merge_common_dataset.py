"""Tests for common dataset normalization and merge helpers."""

import warnings

import pandas as pd

from src.pipeline.kaggle_merge_common_dataset import (
    COMMON_COLUMNS,
    EXPECTED_FILE_CANDIDATES,
    build_manual_review_candidates,
    deduplicate_publications,
    find_input_file,
    normalize_date,
    normalize_crossref,
    normalize_title_key,
    record_merge_info,
    strip_markup,
)


def test_strip_markup_removes_scholarly_title_tags():
    title = (
        "Cohabitation and<i>Ekageikama</i>in the<scp>K</scp>andyan"
        "<scp>K</scp>ingdom (<scp>S</scp>ri<scp>L</scp>anka)"
    )

    assert strip_markup(title) == "Cohabitation and Ekageikama in the Kandyan Kingdom (Sri Lanka)"


def test_strip_markup_decodes_entities_and_escaped_tags():
    title = (
        "Fired-Siltstone Based Geopolymers for CO&lt;inf&gt;2&lt;/inf&gt; "
        "Sequestration Wells &amp; Storage"
    )

    assert strip_markup(title) == "Fired-Siltstone Based Geopolymers for CO2 Sequestration Wells & Storage"


def test_strip_markup_decodes_nested_and_source_typo_entities():
    abstract = "Oliver&amp;amp;Pharr method and &squo;Gibson' soil"

    assert strip_markup(abstract) == "Oliver&Pharr method and 'Gibson' soil"


def test_normalize_title_key_uses_cleaned_markup():
    title = "<scp>I</scp>slam and Gender"

    assert normalize_title_key(title) == "islam and gender"


def test_normalize_title_key_preserves_unicode_words():
    theory = "තොරතුරු තාක්ෂණය පිළිබඳ පදනම් පාඨමාලාව (සිද්ධාන්ත) - FNDI 22020"
    practical = "තොරතුරු තාක්ෂණය පිළිබඳ පදනම් පාඨමාලාව (ප්‍රායෝගික) - FNDI 22020"

    assert normalize_title_key(theory) != normalize_title_key(practical)
    assert "සිද්ධාන්ත" in normalize_title_key(theory)
    assert "ප්‍රායෝගික" in normalize_title_key(practical)


def test_normalize_date_parses_slash_dates_without_pandas_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        assert normalize_date("31/12/2024") == "2024-12-31"
        assert normalize_date("12/31/2024") == "2024-12-31"
        assert normalize_date("05/06/2024") == "2024-06-05"


def test_normalize_crossref_extracts_nested_publication_fields():
    frame = pd.DataFrame(
        {
            "DOI": ["10.1000/test"],
            "title": ["['Test publication']"],
            "author": [
                str(
                    [
                        {
                            "given": "A.",
                            "family": "Author",
                            "ORCID": "https://orcid.org/0000-0001-0000-0000",
                            "affiliation": [{"name": "University of Colombo"}],
                        },
                        {
                            "given": "B.",
                            "family": "Writer",
                            "affiliation": [{"name": "University of Kelaniya"}],
                        },
                    ]
                )
            ],
            "license": [[{"URL": "https://license.example/policy"}]],
            "page": ["12-18"],
            "reference-count": ["2"],
            "reference": [[{"DOI": "10.1000/ref", "article-title": "Reference"}]],
            "funder": [
                str(
                    [
                        {
                            "DOI": "10.13039/100008902",
                            "name": "Test Fund",
                            "id": [{"id": "10.13039/100008902", "id-type": "DOI"}],
                            "award": ["A1"],
                        }
                    ]
                )
            ],
        }
    )

    normalized = normalize_crossref(frame, include_raw_json=False)
    row = normalized.loc[0]

    assert row["authors"] == "A. Author; B. Writer"
    assert row["author_affiliations"] == "University of Colombo; University of Kelaniya"
    assert row["author_orcids"] == "https://orcid.org/0000-0001-0000-0000"
    assert row["license_url"] == "https://license.example/policy"
    assert row["first_page"] == "12"
    assert row["last_page"] == "18"
    assert row["reference_count"] == 2
    assert "10.1000/ref" in row["references_json"]
    assert row["funder_name"] == "Test Fund"
    assert row["funder_doi"] == "10.13039/100008902"
    assert "10.13039/100008902" in row["funder_id"]
    assert row["funder_award"] == "A1"


def test_find_input_file_accepts_current_crossref_filename(tmp_path):
    crossref_dir = tmp_path / "processed" / "crossref"
    crossref_dir.mkdir(parents=True)
    current_crossref = crossref_dir / "crossref_sri_lanka_works.csv"
    current_crossref.write_text("DOI,title\n10.1000/test,Test\n", encoding="utf-8")

    assert find_input_file(tmp_path, EXPECTED_FILE_CANDIDATES["crossref"]) == current_crossref


def common_row(**overrides):
    row = {column: pd.NA for column in COMMON_COLUMNS}
    row.update(
        {
            "source_dataset": "repositories_combined",
            "source_record_id": "record-1",
            "title": "Same title",
            "publication_year": "2024",
            "author_names": "A. Author",
        }
    )
    row.update(overrides)
    return row


def test_title_year_first_author_is_manual_review_not_auto_merge_key():
    row = pd.Series(
        common_row(
            doi=pd.NA,
            source_dataset="repositories_combined",
            source_record_id="repo-1",
            title="Same title",
            publication_year="2024",
            author_names="A. Author",
        )
    )

    merge_key, merge_method, merge_reason = record_merge_info(row, 1)

    assert merge_key == "source_record:repositories_combined|repo-1"
    assert merge_method == "source_record_id"
    assert "title" not in merge_reason.casefold()


def test_deduplicate_does_not_auto_merge_title_year_first_author_candidates():
    records = pd.DataFrame(
        [
            common_row(source_dataset="repositories_combined", source_record_id="repo-1"),
            common_row(source_dataset="openalex", source_record_id="openalex-1"),
        ],
        columns=COMMON_COLUMNS,
    )

    deduplicated, merge_log = deduplicate_publications(records, return_log=True)
    manual_review = build_manual_review_candidates(records)

    assert len(deduplicated) == 2
    assert not merge_log["was_merged"].any()
    assert len(manual_review) == 1
    assert manual_review.loc[0, "review_method"] == "title_year_first_author"
    assert manual_review.loc[0, "input_row_numbers"] == "1; 2"


def test_deduplicate_still_auto_merges_normalized_doi_matches():
    records = pd.DataFrame(
        [
            common_row(source_dataset="crossref", source_record_id="10.1000/test", doi="10.1000/test"),
            common_row(
                source_dataset="openalex",
                source_record_id="https://openalex.org/W1",
                doi="https://doi.org/10.1000/test",
            ),
        ],
        columns=COMMON_COLUMNS,
    )

    deduplicated, merge_log = deduplicate_publications(records, return_log=True)

    assert len(deduplicated) == 1
    assert merge_log.loc[0, "was_merged"]
    assert merge_log.loc[0, "merge_method"] == "doi"


def test_deduplicate_uses_default_field_source_policy_and_logs_conflicts():
    records = pd.DataFrame(
        [
            common_row(
                source_dataset="crossref",
                source_record_id="10.1000/policy",
                doi="10.1000/policy",
                title="Crossref title",
                publication_year="2022",
                authors="Crossref Author",
                author_names="Crossref Author",
                abstract="Crossref abstract",
                issn="1234-5678",
                is_referenced_by_count="20",
                reference_count="30",
                funder_name="Crossref Funder",
            ),
            common_row(
                source_dataset="openalex",
                source_record_id="https://openalex.org/W-policy",
                openalex_id="https://openalex.org/W-policy",
                doi="https://doi.org/10.1000/policy",
                title="OpenAlex title",
                publication_year="2024",
                authors="OpenAlex Author",
                author_names="OpenAlex Author",
                journal="OpenAlex Journal",
                cited_by_count="5",
                referenced_works_count="10",
            ),
            common_row(
                source_dataset="repositories_combined",
                source_record_id="repo-policy",
                doi="10.1000/policy",
                title="Repository title",
                publication_year="2023",
                abstract="Repository abstract",
                keywords="Repository Keyword",
                author_names=pd.NA,
            ),
        ],
        columns=COMMON_COLUMNS,
    )

    deduplicated, merge_log = deduplicate_publications(records, return_log=True)
    merged = deduplicated.loc[0]

    assert len(deduplicated) == 1
    assert merged["title"] == "Crossref title"
    assert merged["publication_year"] == "2022"
    assert merged["authors"] == "Crossref Author; OpenAlex Author"
    assert merged["author_names"] == "Crossref Author; OpenAlex Author"
    assert merged["journal"] == "OpenAlex Journal"
    assert merged["abstract"] == "Crossref abstract"
    assert merged["issn"] == "1234-5678"
    assert merged["keywords"] == "Repository Keyword"
    assert merged["cited_by_count"] == "5"
    assert merged["is_referenced_by_count"] == "20"
    assert merged["referenced_works_count"] == "10"
    assert merged["reference_count"] == "30"
    assert merged["funder_name"] == "Crossref Funder"
    assert merged["source_dataset"] == "crossref; openalex; repositories_combined"
    assert "title" in merge_log.loc[0, "conflict_fields"]
    assert merge_log.loc[0, "citation_count_difference_oa_minus_crossref"] == -15
    assert merge_log.loc[0, "citation_count_divergence_flag"]
    assert merge_log.loc[0, "reference_count_difference_oa_minus_crossref"] == -20
    assert merge_log.loc[0, "reference_count_divergence_flag"]


def test_deduplicate_field_policy_falls_back_to_available_values():
    records = pd.DataFrame(
        [
            common_row(
                source_dataset="openalex",
                source_record_id="https://openalex.org/W-missing-count",
                openalex_id="https://openalex.org/W-missing-count",
                doi="https://doi.org/10.1000/missing-count",
                title="OpenAlex title",
                journal="OpenAlex Journal",
                concepts="Concept A",
                topics="Topic A",
                cited_by_count=pd.NA,
                referenced_works_count=pd.NA,
            ),
            common_row(
                source_dataset="crossref",
                source_record_id="10.1000/missing-count",
                doi="10.1000/missing-count",
                title="Crossref title",
                cited_by_count="42",
                is_referenced_by_count="42",
                reference_count="12",
            ),
        ],
        columns=COMMON_COLUMNS,
    )

    deduplicated, merge_log = deduplicate_publications(records, return_log=True)
    merged = deduplicated.loc[0]

    assert merged["title"] == "Crossref title"
    assert merged["journal"] == "OpenAlex Journal"
    assert merged["cited_by_count"] == "42"
    assert merged["is_referenced_by_count"] == "42"
    assert merged["reference_count"] == "12"
    assert pd.isna(merge_log.loc[0, "citation_count_difference_oa_minus_crossref"])
    assert pd.isna(merge_log.loc[0, "reference_count_difference_oa_minus_crossref"])


def test_deduplicate_flags_same_doi_groups_that_cross_review_thresholds():
    records = pd.DataFrame(
        [
            common_row(
                source_dataset="crossref",
                source_record_id="10.1000/severe",
                doi="10.1000/severe",
                title="Deep learning for crop disease detection",
                publication_year="2020",
            ),
            common_row(
                source_dataset="openalex",
                source_record_id="https://openalex.org/W-severe",
                doi="https://doi.org/10.1000/severe",
                title="Ancient coastal trade routes in Sri Lanka",
                publication_year="2023",
            ),
        ],
        columns=COMMON_COLUMNS,
    )

    _, merge_log = deduplicate_publications(records, return_log=True)
    log_row = merge_log.loc[0]

    assert bool(log_row["duplicate_threshold_review_flag"])
    assert log_row["duplicate_title_similarity_min"] < 0.80
    assert log_row["duplicate_publication_year_span"] == 3
    assert "title similarity" in log_row["duplicate_threshold_review_reason"]
    assert "publication-year span" in log_row["duplicate_threshold_review_reason"]


def test_deduplicate_flags_artifact_like_same_doi_groups_for_review():
    records = pd.DataFrame(
        [
            common_row(
                source_dataset="openalex",
                source_record_id="artifact-1",
                doi="10.1000/artifact",
                title="Additional file 1 of Parent Study",
                publication_year="2024",
            ),
            common_row(
                source_dataset="crossref",
                source_record_id="artifact-2",
                doi="https://doi.org/10.1000/artifact",
                title="Additional file 1 of Parent Study",
                publication_year="2024",
            ),
        ],
        columns=COMMON_COLUMNS,
    )

    _, merge_log = deduplicate_publications(records, return_log=True)
    log_row = merge_log.loc[0]

    assert bool(log_row["duplicate_artifact_title_flag"])
    assert bool(log_row["duplicate_threshold_review_flag"])
    assert "artifact-like title" in log_row["duplicate_threshold_review_reason"]


def test_deduplicate_allows_field_source_policy_override():
    records = pd.DataFrame(
        [
            common_row(
                source_dataset="crossref",
                source_record_id="10.1000/override",
                doi="10.1000/override",
                title="Crossref title",
                abstract="Crossref abstract",
            ),
            common_row(
                source_dataset="openalex",
                source_record_id="https://openalex.org/W-override",
                doi="https://doi.org/10.1000/override",
                title="OpenAlex title",
            ),
        ],
        columns=COMMON_COLUMNS,
    )

    deduplicated, _ = deduplicate_publications(
        records,
        return_log=True,
        field_source_policy={"title": ["openalex", "crossref"]},
    )

    assert deduplicated.loc[0, "title"] == "OpenAlex title"
    assert deduplicated.loc[0, "abstract"] == "Crossref abstract"
