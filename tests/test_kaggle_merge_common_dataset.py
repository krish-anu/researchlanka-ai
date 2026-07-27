"""Tests for common dataset normalization and merge helpers."""

import pandas as pd

from scripts.kaggle_merge_common_dataset import (
    COMMON_COLUMNS,
    build_manual_review_candidates,
    deduplicate_publications,
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
