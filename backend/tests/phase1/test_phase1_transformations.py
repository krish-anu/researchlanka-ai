"""Phase 1 — transforming / schema mapping edge cases."""

from __future__ import annotations

import pytest

from research_analytics import map_to_standard_schema
from research_analytics.schema import STANDARD_PUBLICATION_FIELDS
from research_analytics.transformations import apply_transformations, transform_value


pytestmark = [pytest.mark.phase1, pytest.mark.transforming]


@pytest.mark.edge_case
@pytest.mark.parametrize(
    "value,rule,expected",
    [
        ("2024-05-01", {"type": "extract_year"}, 2024),
        ("A; B; C", {"type": "split", "separator": ";"}, ["A", "B", "C"]),
        ("https://doi.org/10.1000/X", {"type": "normalize_doi"}, "10.1000/x"),
        ("  spaced  title ", {"type": "normalize_title"}, "spaced title"),
        ("  spaced  text ", {"type": "normalize_text"}, "spaced text"),
        (None, {"type": "normalize_doi"}, None),
        ("", {"type": "split"}, []),
    ],
)
def test_transform_value_edge_cases(value, rule, expected):
    assert transform_value(value, rule) == expected


def test_apply_transformations_only_touches_declared_fields():
    record = {
        "title": "  Raw Title ",
        "doi": "https://doi.org/10.1/ABC",
        "authors": "A; B",
        "extra": "keep-me",
    }
    out = apply_transformations(
        record,
        {
            "title": {"type": "normalize_title"},
            "doi": {"type": "normalize_doi"},
            "authors": {"type": "split", "separator": ";"},
            "missing": {"type": "normalize_text"},
        },
    )
    assert out["title"] == "Raw Title"
    assert out["doi"] == "10.1/abc"
    assert out["authors"] == ["A", "B"]
    assert out["extra"] == "keep-me"
    assert "missing" not in out


def test_map_to_standard_schema_fills_standard_fields():
    mapped = map_to_standard_schema(
        {
            "paper_name": "Configurable mapping",
            "researcher": "Asha Example",
            "university": "Example University",
            "published_year": "2024",
        },
        {
            "paper_name": "title",
            "researcher": "authors",
            "university": "institutions",
            "published_year": "publication_year",
        },
        source_name="phase1_fixture",
    )
    assert set(STANDARD_PUBLICATION_FIELDS).issubset(mapped)
    assert mapped["source_name"] == "phase1_fixture"
    assert mapped["title"] == "Configurable mapping"


@pytest.mark.edge_case
def test_apply_transformations_noop_when_rules_missing():
    record = {"title": "Keep"}
    assert apply_transformations(record, None) == record
    assert apply_transformations(record, {}) == record
