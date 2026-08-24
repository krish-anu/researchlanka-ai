"""Tests for the shared record extractor helpers in ``src/utils``.

These extractors run *after* source-specific normalization, so every one of
them reads the **flat common schema** (``journal``, ``publication_date``,
``authors`` ...) rather than a raw Crossref/OpenAlex payload. An earlier
version of this file asserted the raw-payload contract and imported a
``src.extractors`` package that is not in the repository, which broke
collection for the whole suite.

The ``xfail`` block at the end records a real open question -- see
``docs/BACKEND_CODE_AUDIT.md``, "Truncated column-priority lists".
"""

import pandas as pd
import pytest

from src.utils.author_utils import extract_authors, split_author_names
from src.utils.date_utils import extract_publication_date
from src.utils.journal_utils import extract_journal, extract_journal_batch
from src.utils.publisher_utils import extract_publisher
from src.utils.referece_utils import extract_references
from src.utils.title_utils import extract_title, normalize_title_text


# ---------------------------------------------------------------- journal


def test_extract_journal_resolves_the_canonical_name_and_records_its_source():
    record = {
        "journal": "Ceylon Journal of Science",
        "issn": "1234-5678",
        "issn_l": "1111-2222",
        "volume": "51",
        "issue": "3",
        "source_type": "journal",
    }

    result = extract_journal(record)

    assert result["journal_clean"] == "Ceylon Journal of Science"
    assert result["journal_name_source"] == "journal"
    assert result["issn"] == "1234-5678"
    assert result["issn_l"] == "1111-2222"
    assert result["volume"] == "51"
    assert result["issue"] == "3"
    assert result["source_type"] == "journal"


def test_extract_journal_reports_no_source_when_the_venue_is_missing():
    result = extract_journal({"journal": "   "})

    assert result["journal_clean"] is None
    assert result["journal_name_source"] is None


def test_extract_journal_batch_matches_single_record_output():
    frame = pd.DataFrame(
        [
            {"journal": "Journal A", "issn": "1111-1111"},
            {"journal": "Journal B", "issn": "2222-2222"},
        ]
    )

    result = extract_journal_batch(frame)

    assert list(result["journal_clean"]) == ["Journal A", "Journal B"]
    # Chunked processing must be indistinguishable from a single pass.
    chunked = extract_journal_batch(frame, batch_size=1)
    pd.testing.assert_frame_equal(result, chunked)


# -------------------------------------------------------------- publisher


def test_extract_publisher_cleans_name_and_location():
    record = {
        "publisher": "  University of Colombo  ",
        "publisher_location": "Colombo",
    }

    result = extract_publisher(record)

    assert result["publisher"] == "University of Colombo"
    assert result["publisher_location"] == "Colombo"


def test_extract_publisher_returns_none_for_blank_fields():
    result = extract_publisher({"publisher": "", "publisher_location": None})

    assert result["publisher"] is None
    assert result["publisher_location"] is None


# ------------------------------------------------------------------ dates


def test_extract_publication_date_resolves_from_publication_date():
    record = {"publication_date": "2024-03-15", "publication_year": "2024"}

    result = extract_publication_date(record)

    assert result["publication_date_clean"] == pd.Timestamp("2024-03-15")
    assert result["publication_date_source"] == "publication_date"
    assert result["publication_year_clean"] == 2024
    assert result["publication_year"] == 2024


def test_extract_publication_date_falls_back_to_january_first_of_the_year():
    result = extract_publication_date({"publication_year": 2019})

    assert result["publication_date_clean"] == pd.Timestamp("2019-01-01")
    assert result["publication_date_source"] == "publication_year_fallback"
    assert result["publication_year_clean"] == 2019


def test_extract_publication_date_marks_unresolvable_records():
    result = extract_publication_date({"publication_date": None, "publication_year": None})

    assert pd.isna(result["publication_date_clean"])
    assert result["publication_date_source"] == "unresolved"
    assert result["publication_year_clean"] is None


def test_extract_publication_date_rejects_implausible_years():
    # _parse_year only accepts 1000-2100, so a stray value must not become a date.
    result = extract_publication_date({"publication_year": 12345})

    assert result["publication_year"] is None
    assert result["publication_date_source"] == "unresolved"


# ------------------------------------------------------------- references


def test_extract_references_resolves_both_count_groups():
    record = {"reference_count": "42", "citation_count": 7}

    result = extract_references(record)

    assert result["reference_count_clean"] == 42
    assert result["reference_count_source"] == "reference_count"
    assert result["citation_count_clean"] == 7
    assert result["citation_count_source"] == "citation_count"


def test_extract_references_handles_missing_counts():
    result = extract_references({})

    assert result["reference_count_clean"] is None
    assert result["reference_count_source"] is None
    assert result["citation_count_clean"] is None
    assert result["citation_count_source"] is None


# ---------------------------------------------------------------- authors


def test_split_author_names_prefers_unambiguous_delimiters():
    assert split_author_names("Perera, A.; Silva, B.") == ["Perera, A.", "Silva, B."]
    assert split_author_names("Perera A | Silva B") == ["Perera A", "Silva B"]
    # Too few commas to be a list -- treated as a single "Last, First" name.
    assert split_author_names("Perera, A.") == ["Perera, A."]


def test_extract_authors_collapses_names_and_derives_a_count():
    record = {
        "authors": "Perera, A.; Silva, B.; Fernando, C.",
        "author_affiliations": "University of Colombo",
        "author_orcids": "0000-0001-2345-6789",
    }

    result = extract_authors(record)

    assert result["author_names_source"] == "authors"
    assert result["author_list"] == ["Perera, A.", "Silva, B.", "Fernando, C."]
    assert result["author_count_clean"] == 3
    assert result["author_affiliations"] == "University of Colombo"


def test_extract_authors_prefers_an_explicit_author_count():
    record = {"authors": "Perera, A.; Silva, B.", "author_count": "9"}

    assert extract_authors(record)["author_count_clean"] == 9


# ----------------------------------------------------------------- titles


def test_normalize_title_text_strips_accents_punctuation_and_case():
    assert normalize_title_text("Eco-Systemes: A Review!") == "eco systemes a review"


def test_extract_title_joins_subtitle_for_display():
    record = {"title": "Coastal Erosion", "subtitle": "A Sri Lankan Case Study"}

    result = extract_title(record)

    assert result["title_display"] == "Coastal Erosion: A Sri Lankan Case Study"
    assert result["title_normalized"] == "coastal erosion a sri lankan case study"


def test_extract_title_falls_back_to_the_original_title():
    result = extract_title({"title": None, "original_title": "Titre Original"})

    assert result["title_display"] == "Titre Original"


# ------------------------------------------------- known gaps (see audit)
#
# Every *_PRIORITY list in src/utils currently holds a single column, while the
# module docstrings describe multi-column fallbacks. Until the team decides
# whether the narrow behaviour is intended, these encode the documented
# contract without failing the build.


@pytest.mark.xfail(
    reason="JOURNAL_NAME_PRIORITY is ['journal']; docstring also lists "
    "container_title and source_name. See docs/BACKEND_CODE_AUDIT.md.",
    strict=False,
)
def test_extract_journal_falls_back_to_container_title_and_source_name():
    result = extract_journal({"container_title": "Container Journal"})

    assert result["journal_clean"] == "Container Journal"


@pytest.mark.xfail(
    reason="AUTHOR_NAME_PRIORITY is ['authors']; docstring states author_names "
    "should take priority. See docs/BACKEND_CODE_AUDIT.md.",
    strict=False,
)
def test_extract_authors_prefers_the_normalized_author_names_column():
    record = {"authors": "raw form", "author_names": "Perera, A.; Silva, B."}

    assert extract_authors(record)["author_names_source"] == "author_names"


@pytest.mark.xfail(
    reason="DATE_PRIORITY is ['publication_date']; docstring also lists "
    "published_date and created_date. See docs/BACKEND_CODE_AUDIT.md.",
    strict=False,
)
def test_extract_publication_date_falls_back_to_published_and_created_dates():
    result = extract_publication_date({"published_date": "2024-03-15"})

    assert result["publication_date_clean"] == pd.Timestamp("2024-03-15")
