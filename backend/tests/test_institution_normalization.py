"""Tests for institution, affiliation and country standardization."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from research_analytics.cleaning import normalize_list_like
from research_analytics.institutions import (
    NationalInstitutionRegistry,
    collaboration_scope,
    enrich_national_context,
    normalize_lookup_key,
    parse_affiliation,
    split_multi_value,
    standardize_countries,
    standardize_country,
    standardize_institution_name,
)
from src.pipeline.build_institution_normalized_dataset import (
    NormalizationStats,
    build_institution_normalized_dataset,
    normalize_row,
)
from src.pipeline.build_institution_registry import (
    build_registry_rows,
    find_possible_duplicates,
    infer_institution_type,
    read_seed_counts,
)


REGISTRY_ROWS = [
    "institution_id,preferred_name,alternative_name,country_code,ror_id,"
    "parent_institution_id,institution_type,source_institution_id",
    "LK001,University of Colombo,University of Colombo,LK,,,university,cmb",
    "LK001,University of Colombo,UOC,LK,,,university,",
    "LK003,University of Moratuwa,University of Moratuwa,LK,,,university,uom",
    "LK028,\"Eastern University, Sri Lanka\",\"Eastern University, Sri Lanka\",LK,,,university,esn",
]


@pytest.fixture()
def registry(tmp_path: Path) -> NationalInstitutionRegistry:
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")
    return NationalInstitutionRegistry.from_csv(registry_path, country_code="LK")


# --- multi-value splitting (regression for the comma-splitting defect) -------


def test_institution_name_containing_comma_is_not_split():
    assert split_multi_value("Eastern University, Sri Lanka") == ["Eastern University, Sri Lanka"]
    assert split_multi_value("Ministry of Health, Nutrition and Indigenous Medicine") == [
        "Ministry of Health, Nutrition and Indigenous Medicine"
    ]


def test_semicolon_separated_values_still_split():
    assert split_multi_value("University of Colombo; Eastern University, Sri Lanka") == [
        "University of Colombo",
        "Eastern University, Sri Lanka",
    ]


def test_normalize_list_like_keeps_comma_splitting_for_free_text_fields():
    assert normalize_list_like("AI, ML") == ["AI", "ML"]


def test_normalize_list_like_honours_explicit_separators():
    assert normalize_list_like("Eastern University, Sri Lanka", separators=(";",)) == [
        "Eastern University, Sri Lanka"
    ]


# --- lookup keys ------------------------------------------------------------


def test_lookup_key_collapses_abbreviations_and_punctuation():
    expected = normalize_lookup_key("University of Colombo")
    assert normalize_lookup_key("Univ. of Colombo") == expected
    assert normalize_lookup_key("university  of   colombo") == expected


def test_lookup_key_strips_department_prefix_when_parent_segment_remains():
    assert normalize_lookup_key("Department of Physics, University of Colombo") == (
        normalize_lookup_key("University of Colombo")
    )
    assert normalize_lookup_key("Faculty of Medicine, University of Colombo") == (
        normalize_lookup_key("University of Colombo")
    )


def test_lookup_key_keeps_standalone_department_names():
    """A government department is an institution, not a sub-unit to strip."""
    assert normalize_lookup_key("Department of Archaeology") == "department of archaeology"


def test_lookup_key_does_not_strip_institution_named_institute_of():
    assert normalize_lookup_key("Institute of Policy Studies of Sri Lanka") == (
        "institute of policy studies of sri lanka"
    )


def test_standardize_institution_name_tidies_without_changing_identity():
    assert standardize_institution_name("  University   of Colombo ,") == "University of Colombo"
    assert standardize_institution_name("") is None


# --- registry resolution ----------------------------------------------------


def test_registry_resolves_alias_and_department_prefixed_name(registry):
    assert registry.resolve_name("UOC").institution_id == "LK001"
    assert registry.resolve_name("Department of Physics, University of Colombo").institution_id == (
        "LK001"
    )


def test_registry_resolves_institution_name_containing_comma(registry):
    resolved, unresolved = registry.resolve_names("Eastern University, Sri Lanka")
    assert [institution.institution_id for institution in resolved] == ["LK028"]
    assert unresolved == []


def test_registry_resolves_repository_source_code(registry):
    resolved = registry.resolve_from_source_id("uom")
    assert [institution.institution_id for institution in resolved] == ["LK003"]


def test_registry_ignores_journal_platform_source_code(registry):
    """SLJOL hosts many universities' journals; it is not itself an institution."""
    assert registry.resolve_from_source_id("sljol") == []


def test_registry_alias_index_has_no_conflicting_ids(registry):
    for key, institution_id in registry.alias_index.items():
        assert institution_id in registry.institutions, key


def test_alias_index_and_lookup_share_one_normalization(tmp_path: Path):
    """The index and the lookup must both go through normalize_lookup_key.

    If either side stops using it, matching fails silently -- nothing raises,
    records simply stop resolving. This pins the symmetry directly by storing a
    messy alias and querying with a clean one.
    """
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text(
        "institution_id,preferred_name,alternative_name,country_code,ror_id,"
        "parent_institution_id,institution_type,source_institution_id\n"
        "LK003,University of Moratuwa,  UNIVERSITY   OF  MORATUWA ,LK,,,university,uom\n",
        encoding="utf-8",
    )
    resolver = NationalInstitutionRegistry.from_csv(registry_path, country_code="LK")

    assert resolver.resolve_name("University of Moratuwa").institution_id == "LK003"
    assert resolver.resolve_name("Univ. of Moratuwa").institution_id == "LK003"


# --- countries --------------------------------------------------------------


def test_standardize_country_accepts_codes_and_names():
    assert standardize_country("LK") == "LK"
    assert standardize_country("lk") == "LK"
    assert standardize_country("Sri Lanka") == "LK"
    assert standardize_country("United Kingdom") == "GB"


def test_standardize_country_rejects_unknown_values():
    assert standardize_country("ZZ") is None
    assert standardize_country("Atlantis") is None
    assert standardize_country("") is None


def test_standardize_countries_separates_recognised_from_unknown():
    assert standardize_countries("LK; US; Atlantis") == (["LK", "US"], ["Atlantis"])


def test_standardize_countries_deduplicates():
    assert standardize_countries("LK; lk; Sri Lanka")[0] == ["LK"]


# --- affiliation parsing ----------------------------------------------------


def test_parse_affiliation_splits_and_strips_department_prefix():
    institutions, countries = parse_affiliation(
        "Department of Physics, University of Colombo, Sri Lanka"
    )
    assert institutions == ["University of Colombo"]
    assert countries == ["LK"]


def test_parse_affiliation_detects_foreign_country_without_truncating_the_name():
    institutions, countries = parse_affiliation(
        "Teaching Hospital Kandy; National Referral Hospital Thimphu Bhutan"
    )
    assert countries == ["BT"]
    assert institutions == [
        "Teaching Hospital Kandy",
        "National Referral Hospital Thimphu Bhutan",
    ]


def test_parse_affiliation_drops_country_only_when_it_is_an_address_tail():
    """A comma marks an address tail; without one the country is part of the name."""
    assert parse_affiliation("University of Colombo, Sri Lanka")[0] == ["University of Colombo"]
    assert parse_affiliation("Rajarata University of Sri Lanka")[0] == [
        "Rajarata University of Sri Lanka"
    ]


def test_registry_resolves_names_carrying_an_address_tail(tmp_path: Path):
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")
    resolver = NationalInstitutionRegistry.from_csv(registry_path, country_code="LK")

    for name in (
        "University of Colombo, Colombo",
        "University of Colombo, Colombo 00300",
        "University of Colombo, Faculty of Science, Colombo",
    ):
        assert resolver.resolve_name(name).institution_id == "LK001", name


def test_registry_does_not_resolve_an_unrelated_institution_by_prefix(tmp_path: Path):
    """Shortening must never reduce a name past its own first segment."""
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")
    resolver = NationalInstitutionRegistry.from_csv(registry_path, country_code="LK")

    assert resolver.resolve_name("University of Oxford") is None
    assert resolver.resolve_name("University of Oxford, Oxford") is None


def test_parse_affiliation_keeps_commas_inside_a_single_institution():
    institutions, _ = parse_affiliation("Ministry of Health, Nutrition and Indigenous Medicine")
    assert institutions == ["Ministry of Health, Nutrition and Indigenous Medicine"]


# --- collaboration classification -------------------------------------------


def test_collaboration_scope_reduces_types_to_local_and_international():
    assert collaboration_scope("domestic_single_institution") == "local"
    assert collaboration_scope("domestic_multi_institution") == "local"
    assert collaboration_scope("international_collaboration") == "international"
    assert collaboration_scope("unresolved_affiliation") == "unknown"
    assert collaboration_scope("not_national") == "unknown"


def test_local_collaboration_across_two_national_institutions(registry):
    enriched = enrich_national_context(
        {"institutions": ["University of Colombo", "University of Moratuwa"], "countries": ["LK"]},
        registry,
        national_country_code="LK",
    )
    assert enriched["collaboration_type"] == "domestic_multi_institution"
    assert enriched["collaboration_scope"] == "local"


def test_international_collaboration_when_a_foreign_country_is_present(registry):
    enriched = enrich_national_context(
        {"institutions": ["University of Colombo"], "countries": ["LK", "GB"]},
        registry,
        national_country_code="LK",
    )
    assert enriched["collaboration_type"] == "international_collaboration"
    assert enriched["collaboration_scope"] == "international"


# --- row normalization ------------------------------------------------------


def test_row_backfills_institution_and_country_from_source_id(registry):
    stats = NormalizationStats()
    output = normalize_row(
        {
            "institutions": "",
            "countries": "",
            "author_affiliations": "",
            "source_institution_id": "uom",
        },
        registry,
        stats,
    )

    assert output["institutions"] == "University of Moratuwa"
    assert output["national_institution_ids"] == "LK003"
    assert output["countries"] == "LK"
    assert output["institution_source"] == "source_institution_id"
    assert output["collaboration_scope"] == "local"
    assert stats.backfilled_from_source_id == 1
    assert stats.countries_inferred == 1


def test_row_from_sljol_is_not_given_an_institution(registry):
    stats = NormalizationStats()
    output = normalize_row(
        {
            "institutions": "",
            "countries": "",
            "author_affiliations": "",
            "source_institution_id": "sljol",
        },
        registry,
        stats,
    )

    assert output["institutions"] == ""
    assert output["national_institution_ids"] == ""
    assert output["institution_source"] == "none"
    assert output["collaboration_scope"] == "unknown"


def test_row_prefers_registry_canonical_spelling(registry):
    stats = NormalizationStats()
    output = normalize_row(
        {"institutions": "UOC", "countries": "LK", "author_affiliations": ""},
        registry,
        stats,
    )
    assert output["institutions"] == "University of Colombo"
    assert output["institution_source"] == "metadata"


def test_row_records_unresolved_institutions_without_dropping_them(registry):
    stats = NormalizationStats()
    output = normalize_row(
        {
            "institutions": "University of Colombo; Some Unknown Institute",
            "countries": "LK",
            "author_affiliations": "",
        },
        registry,
        stats,
    )

    assert output["national_institutions"] == "University of Colombo"
    assert output["unresolved_institutions"] == "Some Unknown Institute"
    assert "Some Unknown Institute" in output["institutions"]
    assert stats.unresolved["Some Unknown Institute"] == 1


def test_row_marks_international_when_affiliation_names_a_foreign_country(registry):
    stats = NormalizationStats()
    output = normalize_row(
        {
            "institutions": "University of Colombo",
            "countries": "LK",
            "author_affiliations": "University of Colombo; Some Hospital Thimphu Bhutan",
        },
        registry,
        stats,
    )
    assert "BT" in output["countries"].split("; ")
    assert output["collaboration_scope"] == "international"


# --- end to end -------------------------------------------------------------


def test_build_dataset_writes_outputs_and_improves_coverage(tmp_path: Path):
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")

    input_csv = tmp_path / "publications.csv"
    input_csv.write_text(
        "\n".join(
            [
                "title,institutions,countries,author_affiliations,source_institution_id",
                "Repository only,,,,uom",
                "Metadata row,UOC,LK,,cmb",
                "Journal platform,,,,sljol",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_csv = tmp_path / "out.csv"
    summary_csv = tmp_path / "summary.csv"
    unresolved_csv = tmp_path / "unresolved.csv"

    stats = build_institution_normalized_dataset(
        input_csv, output_csv, summary_csv, registry_path, unresolved_csv, chunk_size=2
    )

    assert stats.rows == 3
    assert stats.rows_with_institution_before == 1
    assert stats.rows_with_institution_after == 2

    rows = list(csv.DictReader(output_csv.open(encoding="utf-8")))
    assert len(rows) == 3
    assert rows[0]["national_institution_ids"] == "LK003"
    assert rows[1]["national_institution_ids"] == "LK001"
    assert rows[2]["national_institution_ids"] == ""
    assert summary_csv.exists()
    assert unresolved_csv.exists()


def test_summary_reports_national_resolution_separately(tmp_path: Path):
    """Registry quality is national_resolution_rate, not institution_resolution_rate.

    The latter counts foreign institutions, which a national registry can never
    resolve by design, so it understates quality. Both must be reported so the
    two are not confused.
    """
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")

    input_csv = tmp_path / "publications.csv"
    input_csv.write_text(
        "title,institutions,sri_lankan_institutions,countries,"
        "author_affiliations,source_institution_id\n"
        "A,University of Colombo; University of Oxford,University of Colombo,LK; GB,,\n",
        encoding="utf-8",
    )
    summary_csv = tmp_path / "summary.csv"
    build_institution_normalized_dataset(
        input_csv,
        tmp_path / "out.csv",
        summary_csv,
        registry_path,
        tmp_path / "unresolved.csv",
    )

    metrics = {
        row["metric"]: row["value"]
        for row in csv.DictReader(summary_csv.open(encoding="utf-8"))
    }

    # The one Sri Lankan institution resolves; the registry is complete.
    assert metrics["national_mentions_expected"] == "1"
    assert metrics["national_mentions_resolved"] == "1"
    assert metrics["national_resolution_rate"] == "100.0%"

    # Oxford is out of scope for a national registry, so the all-mentions rate
    # is lower. That is expected, not a defect.
    assert metrics["institution_mentions"] == "2"
    assert metrics["institution_mentions_resolved"] == "1"
    assert metrics["institution_resolution_rate"] == "50.0%"


def test_build_dataset_preserves_every_input_column(tmp_path: Path):
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")

    input_csv = tmp_path / "publications.csv"
    input_csv.write_text(
        "doi,title,institutions,countries,author_affiliations,source_institution_id\n"
        "10.1/a,Paper,UOC,LK,,cmb\n",
        encoding="utf-8",
    )
    output_csv = tmp_path / "out.csv"
    build_institution_normalized_dataset(
        input_csv,
        output_csv,
        tmp_path / "summary.csv",
        registry_path,
        tmp_path / "unresolved.csv",
    )

    header = output_csv.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:6] == [
        "doi",
        "title",
        "institutions",
        "countries",
        "author_affiliations",
        "source_institution_id",
    ]
    assert "collaboration_scope" in header


# --- registry generation ----------------------------------------------------


def test_seed_counts_read_confirmed_national_column(tmp_path: Path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "title,sri_lankan_institutions\n"
        "A,University of Colombo; University of Moratuwa\n"
        "B,University of Colombo\n",
        encoding="utf-8",
    )
    counts = read_seed_counts(dataset)
    assert counts["University of Colombo"] == 2
    assert counts["University of Moratuwa"] == 1


def test_seed_counts_require_the_national_column(tmp_path: Path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text("title\nA\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sri_lankan_institutions"):
        read_seed_counts(dataset)


def test_registry_generation_preserves_existing_identifiers():
    existing = {
        "LK001": {
            "institution_id": "LK001",
            "preferred_name": "University of Colombo",
            "aliases": {"University of Colombo", "UOC"},
            "ror_id": "",
            "parent_institution_id": "",
            "institution_type": "university",
        }
    }
    key_to_id = {
        normalize_lookup_key("University of Colombo"): "LK001",
        normalize_lookup_key("UOC"): "LK001",
    }
    rows = build_registry_rows(
        {"University of Colombo": 10, "University of Kelaniya": 5},
        existing,
        key_to_id,
        {"cmb": "University of Colombo"},
    )

    by_name = {row["preferred_name"]: row["institution_id"] for row in rows}
    assert by_name["University of Colombo"] == "LK001"
    assert by_name["University of Kelaniya"] != "LK001"
    assert any(row["source_institution_id"] == "cmb" for row in rows)


def test_registry_generation_merges_curated_alias_into_existing_entry():
    """The dataset spelling of NSF must not become a second institution."""
    existing = {
        "LK006": {
            "institution_id": "LK006",
            "preferred_name": "National Science Foundation",
            "aliases": {"National Science Foundation"},
            "ror_id": "",
            "parent_institution_id": "",
            "institution_type": "research_institute",
        }
    }
    key_to_id = {normalize_lookup_key("National Science Foundation"): "LK006"}
    rows = build_registry_rows(
        {"National Science Foundation of Sri Lanka": 220}, existing, key_to_id, {}
    )
    assert {row["institution_id"] for row in rows} == {"LK006"}


def test_registry_row_order_is_deterministic():
    """Regenerating an unchanged registry must produce an identical file.

    Aliases live in a set, so any sort key that leaves two of them equal falls
    back to set iteration order, which varies between runs. Case variants such
    as "PDN" and "pdn" are exactly that case, and produced a spurious diff on
    every regeneration until the sort key was made total.
    """
    existing = {
        "LK002": {
            "institution_id": "LK002",
            "preferred_name": "University of Peradeniya",
            "aliases": {"University of Peradeniya", "PDN", "pdn", "UOP", "uop"},
            "ror_id": "",
            "parent_institution_id": "",
            "institution_type": "university",
        }
    }
    key_to_id = {normalize_lookup_key("University of Peradeniya"): "LK002"}

    runs = [
        [
            (row["institution_id"], row["alternative_name"])
            for row in build_registry_rows(
                {"University of Peradeniya": 5}, existing, dict(key_to_id), {}
            )
        ]
        for _ in range(5)
    ]
    assert all(run == runs[0] for run in runs)


def test_infer_institution_type_recognises_common_shapes():
    assert infer_institution_type("University of Colombo") == "university"
    assert infer_institution_type("Teaching Hospital Kandy") == "hospital"
    assert infer_institution_type("Department of Archaeology") == "government_body"
    assert infer_institution_type("Industrial Technology Institute") == "research_institute"


def test_find_possible_duplicates_flags_nested_names():
    rows = [
        {"institution_id": "LK001", "preferred_name": "University of Colombo"},
        {"institution_id": "LK055", "preferred_name": "University of Colombo, Sri Lanka"},
        {"institution_id": "LK003", "preferred_name": "University of Moratuwa"},
    ]
    duplicates = find_possible_duplicates(rows)
    assert len(duplicates) == 1
    assert "LK001" in duplicates[0][0]
