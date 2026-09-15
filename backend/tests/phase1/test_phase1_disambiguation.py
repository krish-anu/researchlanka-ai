"""Phase 1 — author disambiguation edge cases."""

from __future__ import annotations

import pytest

from research_analytics.authors import (
    AuthorVariantIndex,
    disambiguate_authors,
    names_compatible,
    normalize_orcid,
    parse_author_name,
    split_author_field,
)


pytestmark = [pytest.mark.phase1, pytest.mark.disambiguation]

ORCID_A = "0000-0002-1825-0097"
ORCID_B = "0000-0001-5109-3700"


def make_record(**overrides):
    record = {
        "authors": "",
        "author_orcids": "",
        "author_affiliations": "",
        "institutions": "",
        "national_institution_ids": "",
        "publication_year": "2020",
        "source_dataset": "openalex",
    }
    record.update(overrides)
    return record


@pytest.mark.edge_case
def test_split_author_field_handles_empty_and_semicolon():
    assert split_author_field("") == []
    assert split_author_field(None) == []
    assert split_author_field("Perera, K.; Silva, A.") == ["Perera, K.", "Silva, A."]


@pytest.mark.edge_case
def test_parse_author_name_edge_forms():
    assert parse_author_name("") is None
    assert parse_author_name("   ") is None
    comma = parse_author_name("Perera, Kumara")
    assert comma is not None and comma.surname == "perera"
    western = parse_author_name("Kumara Perera")
    assert western is not None and western.surname == "perera"


@pytest.mark.edge_case
def test_normalize_orcid_rejects_invalid_checksum():
    assert normalize_orcid(ORCID_A) == ORCID_A
    assert normalize_orcid("https://orcid.org/" + ORCID_A) == ORCID_A
    assert normalize_orcid("0000-0000-0000-0000") is None
    assert normalize_orcid("") is None


@pytest.mark.edge_case
def test_same_orcid_merges_despite_name_variation():
    index = AuthorVariantIndex()
    index.add_record(
        make_record(authors="Perera, K.", author_orcids=ORCID_A, institutions="University of Colombo"),
        record_id="r1",
    )
    index.add_record(
        make_record(authors="K. Perera", author_orcids=ORCID_A, institutions="University of Colombo"),
        record_id="r2",
    )
    result = disambiguate_authors(index)
    assert len(result.clusters) == 1


@pytest.mark.edge_case
def test_different_orcids_do_not_merge_even_with_same_name():
    # Identical spellings collapse into one variant; conflict is visible there.
    same_spelling = AuthorVariantIndex()
    same_spelling.add_record(
        make_record(
            authors="Perera, Kumara",
            author_orcids=ORCID_A,
            national_institution_ids="LK001",
        ),
        record_id="r1",
    )
    same_spelling.add_record(
        make_record(
            authors="Perera, Kumara",
            author_orcids=ORCID_B,
            national_institution_ids="LK001",
        ),
        record_id="r2",
    )
    variant = same_spelling.variants["perera|kumara"]
    assert variant.orcids == {ORCID_A, ORCID_B}

    # Compatible name forms with distinct ORCIDs must stay separate people.
    index = AuthorVariantIndex()
    index.add_record(
        make_record(
            authors="Perera, Kumara",
            author_orcids=ORCID_A,
            national_institution_ids="LK001",
        ),
        record_id="r1",
    )
    index.add_record(
        make_record(
            authors="Perera, K.",
            author_orcids=ORCID_B,
            national_institution_ids="LK001",
        ),
        record_id="r2",
    )
    result = disambiguate_authors(index)
    assert len(result.clusters) == 2
    assert result.stats.orcid_blocked_merges >= 1


@pytest.mark.edge_case
def test_names_compatible_initial_expansion():
    left = parse_author_name("Perera, K.")
    right = parse_author_name("Perera, Kumara")
    assert left is not None and right is not None
    assert names_compatible(left, right) is True
