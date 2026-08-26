"""Tests for publication type and venue standardization."""

from __future__ import annotations

import csv
from pathlib import Path

from research_analytics.venues import (
    NON_RESEARCH_TYPES,
    PUBLICATION_TYPES,
    classify_venue,
    standardize_journal_name,
    standardize_publication_type,
    strip_trailing_parenthetical,
)
from src.pipeline.build_type_journal_normalized_dataset import (
    TypeJournalStats,
    VenueIndex,
    build_type_journal_normalized_dataset,
    build_venue_index,
    normalize_row,
    primary_issn,
)


# --- publication types ------------------------------------------------------


def test_case_and_separator_variants_collapse_to_one_type():
    """article / Article / journal-article are ~99,000 records of one type."""
    for value in ("article", "Article", "journal-article", "Journal Article"):
        assert standardize_publication_type(value).publication_type == "journal_article"


def test_conference_variants_including_typos_collapse():
    for value in (
        "conference-paper",
        "Conference Paper",
        "Conferenece paper",
        "proceedings-article",
        "Conference-Full-text",
    ):
        assert standardize_publication_type(value).publication_type == "conference_paper"


def test_record_form_is_kept_rather_than_discarded():
    """Standardizing must not lose the full-text vs abstract distinction."""
    full_text = standardize_publication_type("Thesis-Full-text")
    abstract = standardize_publication_type("Thesis-Abstract")

    assert full_text.publication_type == abstract.publication_type == "thesis"
    assert full_text.record_form == "full_text"
    assert abstract.record_form == "abstract"


def test_extended_abstract_is_an_abstract_form():
    result = standardize_publication_type("Conference-Extended-Abstract")
    assert result.publication_type == "conference_paper"
    assert result.record_form == "abstract"


def test_thesis_degree_level_is_extracted():
    assert standardize_publication_type("PhD Thesis").thesis_degree_level == "phd"
    assert standardize_publication_type("Masters Thesis").thesis_degree_level == "masters"
    assert standardize_publication_type("M.phil. Thesis").thesis_degree_level == "mphil"


def test_misspelled_degree_still_resolves():
    """'M.pil. Thesis' appears in the corpus and is an mphil."""
    result = standardize_publication_type("M.pil. Thesis")
    assert result.publication_type == "thesis"
    assert result.thesis_degree_level == "mphil"


def test_degree_level_only_applies_to_theses():
    assert standardize_publication_type("article").thesis_degree_level == "unknown"


def test_non_research_outputs_are_flagged():
    for value in ("Exam Paper", "Convocation booklet", "Contents", "Animation", "Other"):
        assert standardize_publication_type(value).is_research_output is False


def test_research_outputs_are_not_flagged_as_non_research():
    for value in ("article", "Thesis", "conference-paper", "dataset", "preprint"):
        assert standardize_publication_type(value).is_research_output is True


def test_ambiguous_single_letter_codes_become_unknown():
    """'A' has 2,069 records and carries no recoverable meaning."""
    assert standardize_publication_type("A").publication_type == "unknown"
    assert standardize_publication_type("P").publication_type == "unknown"


def test_blank_and_missing_types_are_unknown():
    for value in ("", "   ", None, "nan"):
        assert standardize_publication_type(value).publication_type == "unknown"


def test_standalone_abstract_keeps_its_form():
    result = standardize_publication_type("Research abstract")
    assert result.publication_type == "abstract"
    assert result.record_form == "abstract"


def test_every_result_uses_the_controlled_vocabulary():
    corpus_values = [
        "article", "Article", "journal-article", "conference-paper", "Other", "Thesis",
        "preprint", "Conference-Full-text", "Exam Paper", "Thesis-Abstract", "book-chapter",
        "A", "Research abstract", "report", "review", "dataset", "Journal full-text",
        "Presentation", "Software", "Book", "SRC-Report", "peer-review", "erratum",
        "editorial", "reference-entry", "paratext", "Masters Thesis", "journal-issue",
        "posted-content", "Animation", "E-Book-Chapter", "Pre-Text", "Short communication",
        "data-paper", "retraction", "Working Paper", "Contents", "Guest Speech",
    ]
    for value in corpus_values:
        result = standardize_publication_type(value)
        assert result.publication_type in PUBLICATION_TYPES, value
        assert result.record_form in {"full_text", "abstract", "unknown"}, value
        assert result.is_research_output == (
            result.publication_type not in NON_RESEARCH_TYPES
        ), value


# --- venue names ------------------------------------------------------------


def test_standardize_journal_name_tidies_whitespace_and_punctuation():
    assert standardize_journal_name("  Ceylon   Medical Journal. ") == "Ceylon Medical Journal"
    assert standardize_journal_name("") is None
    assert standardize_journal_name(None) is None


def test_strip_trailing_parenthetical_removes_publisher_qualifiers():
    assert strip_trailing_parenthetical("arXiv (Cornell University)") == "arXiv"
    assert strip_trailing_parenthetical("Ceylon Medical Journal") == "Ceylon Medical Journal"
    assert strip_trailing_parenthetical(
        "American Scientific Research Journal (Global Society of Scientific Research)"
    ) == "American Scientific Research Journal"


def test_strip_trailing_parenthetical_removes_a_repeated_name():
    assert strip_trailing_parenthetical("Research Square (Research Square)") == "Research Square"


def test_strip_trailing_parenthetical_keeps_series_qualifiers():
    """A series name is part of the venue's identity, not a publisher tag."""
    name = "Ceylon Journal of Science (Biological Sciences)"
    assert strip_trailing_parenthetical(name) == name


def test_proceedings_in_a_title_does_not_make_it_a_conference():
    """PNAS is a journal despite being named "Proceedings of ..."."""
    assert classify_venue(
        "Proceedings of the National Academy of Sciences", has_issn=True
    ) == "journal"


def test_classify_venue_recognises_conference_venues():
    for name in (
        "2026 IEEE International Research Conference on Smart Computing",
        "Moratuwa Engineering Research Conference (MERCon)",
        "International Symposium on Advances in Computing",
    ):
        assert classify_venue(name) == "conference", name


def test_classify_venue_recognises_book_series():
    assert classify_venue("Elsevier eBooks") == "book_series"


def test_classify_venue_identifies_platforms_not_journals():
    assert classify_venue("Zenodo (CERN European Organization for Nuclear Research)") == (
        "data_repository"
    )
    assert classify_venue("SSRN Electronic Journal") == "preprint_server"
    assert classify_venue("Research Square") == "preprint_server"
    assert classify_venue("Archaeology Data Service") == "data_repository"
    assert classify_venue("PubMed") == "aggregator"
    assert classify_venue("Murdoch Research Repository (Murdoch University)") == (
        "institutional_repository"
    )


def test_classify_venue_recognises_real_journals():
    assert classify_venue("Ceylon Medical Journal") == "journal"
    assert classify_venue("Tropical Agricultural Research", has_issn=True) == "journal"
    assert classify_venue("Some Venue", has_issn=True) == "journal"


def test_classify_venue_handles_missing_names():
    assert classify_venue("") == "unknown"
    assert classify_venue(None) == "unknown"


# --- venue canonicalization -------------------------------------------------


def test_dominant_spelling_wins_within_a_casefold_group():
    index = VenueIndex()
    for _ in range(33):
        index.observe("Desalination and Water Treatment", None)
    index.observe("DESALINATION AND WATER TREATMENT", None)
    index.finalize()

    assert index.canonical("DESALINATION AND WATER TREATMENT", None) == (
        "Desalination and Water Treatment"
    )


def test_tie_between_spellings_prefers_natural_title_case():
    """Alphabetical tie-breaking would pick "Journal Of The ..." because
    uppercase sorts first; natural title case must win instead."""
    index = VenueIndex()
    for _ in range(130):
        index.observe("Journal of the Postgraduate Institute of Medicine", None)
    for _ in range(130):
        index.observe("Journal Of The Postgraduate Institute of Medicine", None)
    index.finalize()

    assert index.canonical("Journal Of The Postgraduate Institute of Medicine", None) == (
        "Journal of the Postgraduate Institute of Medicine"
    )


def test_issn_is_authoritative_over_the_name():
    """Records sharing an ISSN are the same venue however the name was written."""
    index = VenueIndex()
    for _ in range(12):
        index.observe("Epidemiology", "1044-3983")
    index.observe("PubMed", "1044-3983")
    index.finalize()

    assert index.canonical("PubMed", "1044-3983") == "Epidemiology"


def test_parenthetical_is_dropped_only_when_shorter_form_is_attested():
    index = VenueIndex()
    for _ in range(1259):
        index.observe("Research Square", None)
    for _ in range(30):
        index.observe("Research Square (Research Square)", None)
    index.observe("Lonely Venue (Some Publisher)", None)
    index.finalize()

    assert index.canonical("Research Square (Research Square)", None) == "Research Square"
    # No shorter spelling attested, so the name is left alone.
    assert index.canonical("Lonely Venue (Some Publisher)", None) == "Lonely Venue (Some Publisher)"


def test_canonical_handles_missing_names():
    index = VenueIndex()
    index.finalize()
    assert index.canonical(None, None) is None
    assert index.canonical("", None) is None


def test_primary_issn_prefers_the_linking_issn():
    assert primary_issn({"issn_l": "1234-5678", "issn": "9999-9999"}) == "1234-5678"
    assert primary_issn({"issn_l": "", "issn": "9999-9999; 1111-1111"}) == "9999-9999"
    assert primary_issn({"issn_l": "", "issn": ""}) is None
    assert primary_issn({"issn_l": "nan", "issn": "nan"}) is None


# --- row normalization ------------------------------------------------------


def test_normalize_row_adds_all_derived_fields():
    index = VenueIndex()
    index.observe("Ceylon Medical Journal", "0009-0875")
    index.finalize()
    stats = TypeJournalStats()

    output = normalize_row(
        {
            "publication_type": "Article-Abstract",
            "journal": "Ceylon Medical Journal",
            "issn_l": "0009-0875",
            "issn": "",
        },
        index,
        stats,
    )

    assert output["publication_type_standardized"] == "journal_article"
    assert output["record_form"] == "abstract"
    assert output["thesis_degree_level"] == "unknown"
    assert output["is_research_output"] is True
    assert output["journal_standardized"] == "Ceylon Medical Journal"
    assert output["venue_type"] == "journal"


def test_normalize_row_falls_back_to_the_type_column():
    index = VenueIndex()
    index.finalize()
    stats = TypeJournalStats()
    output = normalize_row({"type": "Thesis", "journal": ""}, index, stats)

    assert output["publication_type_standardized"] == "thesis"
    assert output["journal_standardized"] == ""
    assert output["venue_type"] == "unknown"


def test_stats_record_the_raw_to_standardized_mapping():
    index = VenueIndex()
    index.finalize()
    stats = TypeJournalStats()
    normalize_row({"publication_type": "Article", "journal": ""}, index, stats)
    normalize_row({"publication_type": "journal-article", "journal": ""}, index, stats)

    assert stats.type_mapping["Article"]["journal_article"] == 1
    assert stats.type_mapping["journal-article"]["journal_article"] == 1
    assert stats.standardized_types["journal_article"] == 2


# --- end to end -------------------------------------------------------------


def _write_dataset(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "title,publication_type,journal,issn_l,issn",
                "A,Article,Ceylon Medical Journal,0009-0875,",
                "B,journal-article,CEYLON MEDICAL JOURNAL,0009-0875,",
                "C,Thesis-Abstract,,,",
                "D,Exam Paper,,,",
                "E,article,Zenodo (CERN European Organization for Nuclear Research),,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_dataset_writes_all_outputs(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    _write_dataset(input_csv)
    output_csv = tmp_path / "out.csv"
    summary_csv = tmp_path / "summary.csv"
    type_mapping_csv = tmp_path / "types.csv"
    journal_mapping_csv = tmp_path / "journals.csv"

    stats = build_type_journal_normalized_dataset(
        input_csv, output_csv, summary_csv, type_mapping_csv, journal_mapping_csv, chunk_size=2
    )

    assert stats.rows == 5
    assert stats.research_outputs == 4  # the exam paper is excluded
    assert output_csv.exists() and summary_csv.exists()
    assert type_mapping_csv.exists() and journal_mapping_csv.exists()

    rows = list(csv.DictReader(output_csv.open(encoding="utf-8")))
    assert [row["publication_type_standardized"] for row in rows] == [
        "journal_article",
        "journal_article",
        "thesis",
        "exam_paper",
        "journal_article",
    ]
    # Both spellings collapse onto the dominant one via the shared ISSN.
    assert rows[0]["journal_standardized"] == rows[1]["journal_standardized"]
    assert rows[4]["venue_type"] == "data_repository"


def test_build_dataset_preserves_every_input_column(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    _write_dataset(input_csv)
    output_csv = tmp_path / "out.csv"

    build_type_journal_normalized_dataset(
        input_csv,
        output_csv,
        tmp_path / "summary.csv",
        tmp_path / "types.csv",
        tmp_path / "journals.csv",
    )

    header = output_csv.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:5] == ["title", "publication_type", "journal", "issn_l", "issn"]
    for column in (
        "publication_type_standardized",
        "record_form",
        "thesis_degree_level",
        "is_research_output",
        "journal_standardized",
        "venue_type",
    ):
        assert column in header


def test_venue_index_is_built_from_the_whole_corpus(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    _write_dataset(input_csv)
    index = build_venue_index(input_csv, chunk_size=2)

    # Chunking must not affect the result: the dominant spelling is corpus-wide.
    assert index.canonical("CEYLON MEDICAL JOURNAL", "0009-0875") == "Ceylon Medical Journal"
