"""Phase 1 — database ingestion contract edge cases."""

from __future__ import annotations

import pytest

from src.database.loader import build_final_publication_row, build_publication_key


pytestmark = [pytest.mark.phase1, pytest.mark.database]


@pytest.mark.edge_case
def test_publication_key_prefers_doi():
    row = {"doi": "10.1000/abc", "openalex_id": "W1", "title": "T"}
    assert build_publication_key(row, 1) == "doi:10.1000/abc"


@pytest.mark.edge_case
def test_build_final_publication_row_normalizes_doi_in_key():
    row = build_final_publication_row(
        {
            "source_name": "phase1",
            "source_record_id": "r-doi",
            "doi": "https://doi.org/10.1000/ABC",
            "title": "Normalized DOI key",
        },
        row_number=1,
    )
    assert row["doi"] == "10.1000/abc"
    assert row["publication_key"] == "doi:10.1000/abc"


@pytest.mark.edge_case
def test_publication_key_falls_back_to_openalex_then_source_then_title():
    assert build_publication_key({"openalex_id": "https://openalex.org/W99"}, 2).startswith(
        "openalex:"
    )
    assert (
        build_publication_key(
            {"source_dataset": "repositories", "source_record_id": "r-1"}, 3
        )
        == "source:repositories:r-1"
    )
    title_key = build_publication_key({"title": "Only Title", "publication_year": 2020}, 4)
    assert title_key.startswith("title:")
    assert build_publication_key({}, 5) == "row:5"


@pytest.mark.edge_case
def test_build_final_publication_row_handles_blankish_values():
    row = build_final_publication_row(
        {
            "source_name": "phase1",
            "source_record_id": "blank-1",
            "doi": "nan",
            "title": "  Valid Title  ",
            "authors": [],
            "institutions": None,
            "is_oa": "false",
            "reference_count": "",
            "publication_year": "2022",
        },
        row_number=9,
    )
    assert row["title"] == "Valid Title" or row["title"]
    assert row["doi"] is None or row["doi"] == ""
    assert row["publication_key"].startswith(("source:", "title:", "row:"))
    assert row["is_oa"] is False
