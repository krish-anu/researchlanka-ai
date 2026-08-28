"""Tests for Crossref data normalization."""

from src.preprocessing.crossref_normalizer import (
    first_author_is_from_sri_lanka,
    reduce_work,
)
from src.collectors.schema_mapping import map_crossref_record


def test_reduce_work_basic():
    """Test basic work reduction."""
    work = {
        "DOI": "10.1234/test",
        "title": ["Test Paper"],
        "type": "journal-article",
        "issued": {"date-parts": [[2024]]},
        "author": [{"given": "John", "family": "Doe"}],
        "container-title": ["Nature"],
        "publisher": "Springer",
    }

    result = reduce_work(work)

    assert result["DOI"] == "10.1234/test"
    assert result["title"] == ["Test Paper"]
    assert result["type"] == "journal-article"
    assert result["publisher"] == "Springer"


def test_reduce_work_marks_first_author_lk_from_registry_affiliation():
    work = {
        "DOI": "10.1234/lk-first",
        "title": ["LK First Author"],
        "type": "journal-article",
        "author": [
            {
                "given": "A.",
                "family": "Author",
                "affiliation": [{"name": "University of Colombo"}],
            },
            {
                "given": "B.",
                "family": "Writer",
                "affiliation": [{"name": "Example University, Australia"}],
            },
        ],
    }

    result = reduce_work(work)

    assert first_author_is_from_sri_lanka(work) is True
    assert result["first_author_name"] == "A. Author"
    assert result["first_author_affiliation"] == "University of Colombo"
    assert result["first_author_country"] == "LK"
    assert result["has_sri_lankan_participant"] is True
    assert result["keep_in_strict_sri_lanka_dataset"] is True


def test_first_author_lk_rejects_sri_lankan_later_author_only():
    work = {
        "DOI": "10.1234/lk-collab",
        "title": ["LK Later Author"],
        "type": "journal-article",
        "author": [
            {
                "given": "A.",
                "family": "Lead",
                "affiliation": [{"name": "Example University, Australia"}],
            },
            {
                "given": "B.",
                "family": "Collaborator",
                "affiliation": [{"name": "University of Colombo"}],
            },
        ],
    }

    result = reduce_work(work)

    assert first_author_is_from_sri_lanka(work) is False
    assert result["has_sri_lankan_participant"] is True
    assert result["keep_in_strict_sri_lanka_dataset"] is False


def test_sljol_crossref_mapping_carries_first_author_lk_fields():
    record = {
        "DOI": "10.4038/example",
        "title": ["SLJOL article"],
        "type": "journal-article",
        "issued": {"date-parts": [[2024, 5, 1]]},
        "author": [
            {
                "given": "A.",
                "family": "Author",
                "affiliation": [{"name": "University of Peradeniya, Sri Lanka"}],
            }
        ],
    }

    mapped = map_crossref_record(record, institution_id="sljol")

    assert mapped["first_author_name"] == "A. Author"
    assert mapped["first_author_affiliation"] == "University of Peradeniya, Sri Lanka"
    assert mapped["first_author_country"] == "LK"
    assert mapped["keep_in_strict_sri_lanka_dataset"] is True


def test_reduce_work_handles_missing_fields():
    """Test that missing fields are handled gracefully."""
    work = {
        "DOI": "10.1234/test",
        "title": ["Test Paper"],
    }

    result = reduce_work(work)

    assert result["DOI"] == "10.1234/test"
    assert result["title"] == ["Test Paper"]
    assert result["abstract"] is None
    assert result["author"] is None
    assert result["issued.date-parts"] is None


def test_reduce_work_nested_fields():
    """Test extraction of nested fields."""
    work = {
        "DOI": "10.1234/test",
        "issued": {"date-parts": [[2024, 3, 15]]},
        "created": {"date-parts": [[2024, 3, 10]]},
        "event": {
            "name": "Conference 2024",
            "location": "Berlin",
            "start": {"date-parts": [[2024, 6, 1]]},
        },
    }

    result = reduce_work(work)

    assert result["issued.date-parts"] == [[2024, 3, 15]]
    assert result["created.date-parts"] == [[2024, 3, 10]]
    assert result["event.name"] == "Conference 2024"
    assert result["event.location"] == "Berlin"
    assert result["event.start.date-parts"] == [[2024, 6, 1]]


def test_reduce_work_preserves_lists():
    """Test that list fields are preserved."""
    work = {
        "DOI": "10.1234/test",
        "ISSN": ["1234-5678", "8765-4321"],
        "author": [
            {"given": "John", "family": "Doe"},
            {"given": "Jane", "family": "Smith"},
        ],
    }

    result = reduce_work(work)

    assert result["ISSN"] == ["1234-5678", "8765-4321"]
    assert len(result["author"]) == 2


def test_reduce_work_all_fields_present():
    """Test that all expected fields are in the output."""
    work = {
        "DOI": "10.1234/test",
        "title": ["Test"],
        "reference-count": 42,
        "is-referenced-by-count": 5,
        "volume": "10",
        "issue": "3",
        "page": "100-110",
        "article-number": "e12345",
        "abstract": "This is a test paper.",
    }

    result = reduce_work(work)

    # Verify all expected keys exist
    expected_keys = [
        "reference-count",
        "publisher",
        "issue",
        "abstract",
        "DOI",
        "type",
        "is-referenced-by-count",
        "title",
        "volume",
        "author",
        "container-title",
        "URL",
        "ISSN",
        "issued.date-parts",
        "published.date-parts",
        "created.date-parts",
        "license",
        "page",
        "reference",
        "event.name",
        "event.location",
        "event.start.date-parts",
        "event.end.date-parts",
        "language",
        "editor",
        "funder",
        "article-number",
        "publisher-location",
        "event.acronym",
        "group-title",
        "subtype",
        "event.sponsor",
        "original-title",
        "subtitle",
    ]

    for key in expected_keys:
        assert key in result


def test_reduce_work_complex_nested():
    """Test reduction of complex nested structures."""
    work = {
        "DOI": "10.1234/complex",
        "event": {
            "name": "Annual Conference",
            "location": "NYC",
            "start": {"date-parts": [[2024, 1, 15]]},
            "end": {"date-parts": [[2024, 1, 20]]},
            "acronym": "AC2024",
            "sponsor": ["NSF", "NIH"],
        },
        "funder": [
            {"name": "NSF", "DOI": "10.13039/100000001"},
            {"name": "NIH", "DOI": "10.13039/100000002"},
        ],
    }

    result = reduce_work(work)

    assert result["event.name"] == "Annual Conference"
    assert result["event.start.date-parts"] == [[2024, 1, 15]]
    assert result["event.end.date-parts"] == [[2024, 1, 20]]
    assert result["event.acronym"] == "AC2024"
