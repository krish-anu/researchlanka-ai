"""Phase 1 — institution entity resolution edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_analytics.institutions import (
    NationalInstitutionRegistry,
    enrich_national_context,
    normalize_lookup_key,
    standardize_country,
)


pytestmark = [pytest.mark.phase1, pytest.mark.entity_resolution]

REGISTRY_ROWS = """institution_id,preferred_name,alternative_name,country_code,ror_id,parent_institution_id,institution_type,source_institution_id
LK001,University of Colombo,University of Colombo,LK,,,university,cmb
LK001,University of Colombo,UOC,LK,,,university,
LK001,University of Colombo,Univ. of Colombo,LK,,,university,
LK003,University of Moratuwa,University of Moratuwa,LK,,,university,uom
"""


@pytest.fixture()
def registry(tmp_path: Path) -> NationalInstitutionRegistry:
    path = tmp_path / "institutions.csv"
    path.write_text(REGISTRY_ROWS, encoding="utf-8")
    return NationalInstitutionRegistry.from_csv(path, country_code="LK")


@pytest.mark.edge_case
def test_lookup_key_expands_abbreviations():
    assert normalize_lookup_key("Univ. of Colombo") == normalize_lookup_key("University of Colombo")
    assert normalize_lookup_key("UOC") != ""


@pytest.mark.edge_case
def test_alias_resolves_to_preferred_institution(registry: NationalInstitutionRegistry):
    resolved = registry.resolve_name("UOC")
    assert resolved is not None
    assert resolved.institution_id == "LK001"
    assert "Colombo" in resolved.preferred_name


@pytest.mark.edge_case
def test_unknown_foreign_institution_does_not_force_lk(registry: NationalInstitutionRegistry):
    resolved = registry.resolve_name("Massachusetts Institute of Technology")
    assert resolved is None


@pytest.mark.edge_case
def test_enrich_national_context_sets_collaboration_type(registry: NationalInstitutionRegistry):
    record = enrich_national_context(
        {
            "institutions": "University of Colombo; University of Oxford",
            "countries": "LK; GB",
            "authors": "A; B",
        },
        registry,
        national_country_code="LK",
    )
    assert "LK001" in record["national_institution_ids"]
    assert record["collaboration_scope"] in {"international", "local", "unknown"}
    assert record["collaboration_type"]


@pytest.mark.edge_case
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Sri Lanka", "LK"),
        ("LK", "LK"),
        ("United Kingdom", "GB"),
        ("", None),
        (None, None),
    ],
)
def test_standardize_country_edge_cases(raw, expected):
    assert standardize_country(raw) == expected
