"""Tests for the shared record extractor helpers."""

from src.extractors.journal import extract_journal
from src.extractors.publication_date import extract_publication_date
from src.extractors.publisher import extract_publisher
from src.extractors.references import extract_references


def test_extract_journal_supports_crossref_and_openalex():
    record = {
        "container-title": ["Example Journal"],
        "ISSN": ["1234-5678"],
        "host_venue": {
            "display_name": "OpenAlex Journal",
            "issn": ["8765-4321"],
            "issn_l": "1111-2222",
        },
        "source_name": "Source Name",
    }

    result = extract_journal(record)

    assert result["journal"] == "Example Journal"
    assert result["container_title"] == "Example Journal"
    assert result["source_name"] == "Source Name"
    assert result["issn"] == ["1234-5678"]
    assert result["issn_l"] == "1111-2222"


def test_extract_publisher_handles_repository_and_openalex_fields():
    record = {
        "publisher_name": "Repository Publisher",
        "publisher_location": "Colombo",
        "host_venue": {"publisher": "OpenAlex Publisher"},
    }

    result = extract_publisher(record)

    assert result["publisher"] == "Repository Publisher"
    assert result["publisher_location"] == "Colombo"


def test_extract_publication_date_prioritizes_published_over_created():
    record = {
        "published-online": {"date-parts": [[2024, 3, 15]]},
        "created": {"date-time": "2024-01-05T00:00:00Z"},
        "publication_year": "2024",
    }

    result = extract_publication_date(record)

    assert result["publication_date"] == "2024-03-15"
    assert result["published_date"] == "2024-03-15"
    assert result["created_date"] == "2024-01-05T00:00:00Z"
    assert result["publication_year"] == 2024


def test_extract_references_supports_crossref_and_openalex_payloads():
    record = {
        "referenced_works": ["https://openalex.org/W123"],
        "reference-count": 1,
    }

    result = extract_references(record)

    assert result["references_json"] == ["https://openalex.org/W123"]
    assert result["reference_count"] == 1
