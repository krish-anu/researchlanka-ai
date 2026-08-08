"""Tests for author and institution disambiguation."""

from collections import Counter

import pytest

from research_analytics.institutions import Institution, NationalInstitutionRegistry
from src.disambiguation import (
    InstitutionResolver,
    align_orcids,
    blocking_key,
    build_author_review_queue,
    build_institution_review_queue,
    build_mentions,
    disambiguate_authors,
    drop_intra_record_fragments,
    extract_record_evidence,
    name_compatibility,
    normalize_orcid,
    parse_name,
    split_names,
)


# --------------------------------------------------------------------- names


def test_parse_name_handles_surname_first_and_initial_runs():
    parsed = parse_name("Deepagoda, T.K.K.C.")
    assert parsed is not None
    assert parsed.surname == "deepagoda"
    assert parsed.initials == ("t", "k", "k", "c")
    assert parsed.given == ()


def test_parse_name_keeps_surname_particles_together():
    parsed = parse_name("Nimal de Silva")
    assert parsed is not None
    assert parsed.surname == "de silva"
    assert parsed.given == ("nimal",)


def test_parse_name_folds_accents_and_drops_honorifics():
    plain = parse_name("Prof. Wimal Perera")
    accented = parse_name("Wimal Pereră")
    assert plain is not None and accented is not None
    assert plain.surname == accented.surname == "perera"
    assert "prof" in plain.dropped_tokens


def test_parse_name_returns_none_for_unusable_input():
    assert parse_name("   ") is None
    assert parse_name("...") is None
    assert parse_name("Dr.") is None


def test_split_names_uses_semicolons_not_commas():
    # A comma is name-internal in this dataset; splitting on it would invent an author.
    assert split_names("Deepagoda, T.K.K.C.") == ["Deepagoda, T.K.K.C."]
    assert split_names("A Silva; B Perera") == ["A Silva", "B Perera"]


def test_blocking_key_groups_abbreviated_and_full_given_names():
    assert blocking_key(parse_name("Wimal Perera")) == blocking_key(parse_name("W. Perera"))


def test_blocking_key_isolates_surname_only_mentions():
    assert blocking_key(parse_name("Perera")) == "perera|_"
    assert blocking_key(parse_name("Perera")) != blocking_key(parse_name("W. Perera"))


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("Wimal Perera", "Wimal Perera", 1.0),
        ("Wimal Perera", "W. Perera", 0.8),
        ("Wimal Perera", "Sunil Perera", 0.0),
        ("W. Perera", "S. Perera", 0.0),
    ],
)
def test_name_compatibility_scores(left, right, expected):
    assert name_compatibility(parse_name(left), parse_name(right)) == pytest.approx(expected)


def test_drop_intra_record_fragments_removes_partial_names():
    # Reproduces the real artefact: full names listed beside their own fragments.
    names = [
        parse_name(value)
        for value in ["Gyan Prasad Bajgai", "Sangay Tshering", "Gyan Prasad", "Sangay"]
    ]
    kept, dropped = drop_intra_record_fragments(names)

    kept_raw = {name.raw for name in kept}
    assert kept_raw == {"Gyan Prasad Bajgai", "Sangay Tshering", "Sangay"}
    assert {name.raw for name in dropped} == {"Gyan Prasad"}


def test_drop_intra_record_fragments_keeps_single_token_names():
    # "Sangay" is one token, so it is never treated as a subset fragment —
    # dropping it would lose a real single-name author.
    names = [parse_name(value) for value in ["Sangay Tshering", "Sangay"]]
    kept, dropped = drop_intra_record_fragments(names)
    assert len(kept) == 2
    assert dropped == []


# ------------------------------------------------------------------ evidence


def test_normalize_orcid_extracts_bare_identifier():
    assert normalize_orcid("https://orcid.org/0000-0002-7517-0894") == "0000-0002-7517-0894"
    assert normalize_orcid("0000-0001-8124-550X") == "0000-0001-8124-550X"
    assert normalize_orcid("not an orcid") is None


def test_align_orcids_attributes_when_counts_match_on_ordered_source():
    names = [parse_name("A Silva"), parse_name("B Perera")]
    aligned = align_orcids(
        names,
        ["0000-0002-7517-0894", "0000-0001-8124-5509"],
        source_dataset="openalex",
    )
    assert aligned == ["0000-0002-7517-0894", "0000-0001-8124-5509"]


def test_align_orcids_refuses_when_counts_differ():
    # The dominant real case: 13 authors, 1 surviving ORCID after unique_join.
    names = [parse_name(f"Author{index} Silva") for index in range(3)]
    assert align_orcids(names, ["0000-0002-7517-0894"], source_dataset="openalex") == [
        None,
        None,
        None,
    ]


def test_align_orcids_refuses_for_unordered_sources():
    names = [parse_name("A Silva"), parse_name("B Perera")]
    aligned = align_orcids(
        names,
        ["0000-0002-7517-0894", "0000-0001-8124-5509"],
        source_dataset="repositories",
    )
    assert aligned == [None, None]


def test_align_orcids_refuses_when_a_name_repeats():
    names = [parse_name("A Silva"), parse_name("A Silva")]
    aligned = align_orcids(
        names,
        ["0000-0002-7517-0894", "0000-0001-8124-5509"],
        source_dataset="openalex",
    )
    assert aligned == [None, None]


def test_extract_record_evidence_collects_all_signals():
    evidence = extract_record_evidence(
        {
            "source_dataset": "openalex",
            "publication_year": "2021",
            "authors": "Wimal Perera; Nimal de Silva",
            "author_orcids": "https://orcid.org/0000-0002-7517-0894; https://orcid.org/0000-0001-8124-5509",
            "sri_lankan_institutions": "University of Colombo",
            "countries": "LK",
            "primary_field": "Medicine",
        },
        record_key="doi:10.1/a",
    )

    assert evidence.publication_year == 2021
    assert len(evidence.names) == 2
    assert evidence.orcids == frozenset({"0000-0002-7517-0894", "0000-0001-8124-5509"})
    assert evidence.orcid_by_position == ("0000-0002-7517-0894", "0000-0001-8124-5509")
    assert "university of colombo" in evidence.institutions
    assert evidence.primary_field == "medicine"


# ------------------------------------------------------------------- authors


def _mentions(records: list[dict]):
    evidence = [
        extract_record_evidence(record, record_key=f"doi:10.1/{index}")
        for index, record in enumerate(records)
    ]
    return build_mentions(evidence)


def test_shared_orcid_merges_across_name_variants_and_blocks():
    # Two spellings that block differently; only the ORCID connects them.
    result = disambiguate_authors(
        _mentions(
            [
                {
                    "source_dataset": "openalex",
                    "authors": "Chamindu Deepagoda",
                    "author_orcids": "0000-0002-8818-8671",
                },
                {
                    "source_dataset": "openalex",
                    "authors": "Thuduwe Chamindu",
                    "author_orcids": "0000-0002-8818-8671",
                },
            ]
        )
    )

    assert len(result.clusters) == 1
    assert result.clusters[0].confidence == "orcid_confirmed"
    assert result.clusters[0].publication_count == 2


def test_conflicting_orcids_are_never_merged():
    result = disambiguate_authors(
        _mentions(
            [
                {
                    "source_dataset": "openalex",
                    "authors": "Wimal Perera",
                    "author_orcids": "0000-0002-8818-8671",
                },
                {
                    "source_dataset": "openalex",
                    "authors": "Wimal Perera",
                    "author_orcids": "0000-0001-8124-5509",
                },
            ]
        )
    )

    # Same name, same institution-free context, but different identifiers.
    assert len(result.clusters) == 2
    assert result.stats["pairs_orcid_conflict"] == 1


def test_shared_coauthor_and_institution_merge_an_abbreviated_name():
    result = disambiguate_authors(
        _mentions(
            [
                {
                    "source_dataset": "openalex",
                    "authors": "Wimal Perera; Nimal de Silva",
                    "sri_lankan_institutions": "University of Colombo",
                    "primary_field": "Medicine",
                },
                {
                    "source_dataset": "openalex",
                    "authors": "W. Perera; Nimal de Silva",
                    "sri_lankan_institutions": "University of Colombo",
                    "primary_field": "Medicine",
                },
            ]
        )
    )

    perera = [c for c in result.clusters if c.block.startswith("perera")]
    assert len(perera) == 1
    assert perera[0].publication_count == 2
    assert perera[0].confidence in {"high", "medium"}


def test_name_alone_is_not_enough_to_merge():
    # Same abbreviated name, no shared coauthor, institution or field: 0.45*0.7
    # = 0.315, below the review floor. Two identities, not one.
    result = disambiguate_authors(
        _mentions(
            [
                {"source_dataset": "openalex", "authors": "Wimal Perera"},
                {"source_dataset": "openalex", "authors": "W. Perera"},
            ]
        )
    )
    assert len(result.clusters) == 2


def test_different_given_names_never_merge_despite_shared_context():
    result = disambiguate_authors(
        _mentions(
            [
                {
                    "source_dataset": "openalex",
                    "authors": "Wimal Perera; Nimal de Silva",
                    "sri_lankan_institutions": "University of Colombo",
                    "primary_field": "Medicine",
                },
                {
                    "source_dataset": "openalex",
                    "authors": "Sunil Perera; Nimal de Silva",
                    "sri_lankan_institutions": "University of Colombo",
                    "primary_field": "Medicine",
                },
            ]
        )
    )
    perera = [c for c in result.clusters if c.block.startswith("perera")]
    assert len(perera) == 2


def test_cluster_canonical_name_prefers_the_most_complete_variant():
    result = disambiguate_authors(
        _mentions(
            [
                {
                    "source_dataset": "openalex",
                    "authors": "Wimal Perera",
                    "author_orcids": "0000-0002-8818-8671",
                },
                {
                    "source_dataset": "openalex",
                    "authors": "W. Perera",
                    "author_orcids": "0000-0002-8818-8671",
                },
                {
                    "source_dataset": "openalex",
                    "authors": "W. Perera",
                    "author_orcids": "0000-0002-8818-8671",
                },
            ]
        )
    )
    assert result.clusters[0].canonical_name == "Wimal Perera"


def test_intra_record_fragments_do_not_become_authors():
    result = disambiguate_authors(
        _mentions(
            [
                {
                    "source_dataset": "openalex",
                    "authors": "Gyan Prasad Bajgai; Sangay Tshering; Gyan Prasad",
                }
            ]
        )
    )
    assert len(result.clusters) == 2


# -------------------------------------------------------------- institutions


@pytest.fixture
def resolver() -> InstitutionResolver:
    registry = NationalInstitutionRegistry(
        {
            "LK001": Institution(
                institution_id="LK001",
                preferred_name="University of Colombo",
                country_code="LK",
                alternative_names={"UOC"},
            ),
            "LK003": Institution(
                institution_id="LK003",
                preferred_name="University of Moratuwa",
                country_code="LK",
                ror_id="https://ror.org/0abcd1234",
            ),
        }
    )
    return InstitutionResolver(registry)


def test_resolve_exact_registry_name(resolver):
    resolution = resolver.resolve("University of Colombo")
    assert resolution.institution_id == "LK001"
    assert resolution.method == "registry_exact"
    assert resolution.confidence == "high"


def test_resolve_alias(resolver):
    assert resolver.resolve("UOC").institution_id == "LK001"


def test_resolve_finds_institution_inside_an_address(resolver):
    resolution = resolver.resolve(
        "Department of Civil Engineering, University of Moratuwa, Katubedda, Sri Lanka"
    )
    assert resolution.institution_id == "LK003"
    assert resolution.method == "registry_segment"
    assert resolution.matched_on == "University of Moratuwa"


def test_resolve_by_ror_identifier(resolver):
    resolution = resolver.resolve("Some Unlisted Unit, https://ror.org/0abcd1234")
    assert resolution.institution_id == "LK003"
    assert resolution.method == "ror"
    assert resolution.confidence == "certain"


def test_resolve_fuzzy_match_for_abbreviated_form(resolver):
    resolution = resolver.resolve("Univ. of Moratuwa")
    assert resolution.institution_id == "LK003"
    assert resolution.method == "registry_fuzzy"
    assert resolution.confidence == "medium"


def test_generic_tokens_do_not_produce_a_false_match(resolver):
    # "University" and "Sri Lanka" are shared by every entry; on their own they
    # must not resolve to any particular institution.
    resolution = resolver.resolve("University of Kelaniya, Sri Lanka")
    assert resolution.institution_id is None
    assert resolution.method == "unresolved"


def test_unresolved_reports_the_closest_candidate(resolver):
    resolution = resolver.resolve("Ministry of Health")
    assert not resolution.is_resolved
    assert resolution.confidence == "none"


# -------------------------------------------------------------------- review


def test_author_review_queue_ranks_by_impact_and_excludes_clean_clusters():
    records = [
        # Ten records merged on name alone -> flagged, high impact.
        *[
            {
                "source_dataset": "openalex",
                "authors": "Wimal Perera; Nimal de Silva",
                "sri_lankan_institutions": "University of Colombo",
                "primary_field": "Medicine",
            }
            for _ in range(10)
        ],
        # One ORCID-confirmed record -> not flagged, must not appear.
        {
            "source_dataset": "openalex",
            "authors": "Chamindu Deepagoda",
            "author_orcids": "0000-0002-8818-8671",
        },
    ]
    result = disambiguate_authors(_mentions(records))
    queue = build_author_review_queue(result)

    assert queue, "expected at least one flagged cluster"
    assert all(item.confidence != "orcid_confirmed" for item in queue)
    assert all(item.actions for item in queue)
    priorities = [item.priority for item in queue]
    assert priorities == sorted(priorities, reverse=True)


def test_author_review_queue_respects_minimum_publication_count():
    result = disambiguate_authors(
        _mentions([{"source_dataset": "openalex", "authors": "Perera"}])
    )
    assert build_author_review_queue(result, min_publications=5) == []


def test_institution_review_queue_includes_fuzzy_and_unresolved(resolver):
    raws = ["Univ. of Moratuwa", "Ministry of Health", "University of Colombo"]
    resolutions = {raw: resolver.resolve(raw) for raw in raws}
    counts = Counter({"Univ. of Moratuwa": 5, "Ministry of Health": 40, "University of Colombo": 900})

    queue = build_institution_review_queue(resolutions, counts)
    queued = {item.raw_affiliation for item in queue}

    assert "University of Colombo" not in queued  # cleanly resolved
    assert queued == {"Univ. of Moratuwa", "Ministry of Health"}
    # The unresolved 40-record string outranks the already-usable fuzzy match.
    assert queue[0].raw_affiliation == "Ministry of Health"
    assert all(item.suggested_action for item in queue)


def test_align_orcids_accepts_merged_multi_source_records():
    # `source_dataset` on a merged record is a list, not a single value. An
    # exact-match test on the whole string rejects the entire corpus.
    names = [parse_name("A Silva"), parse_name("B Perera")]
    aligned = align_orcids(
        names,
        ["0000-0002-7517-0894", "0000-0001-8124-5509"],
        source_dataset="openalex; crossref; repositories_combined",
    )
    assert aligned == ["0000-0002-7517-0894", "0000-0001-8124-5509"]


def test_uppercase_initials_are_not_mistaken_for_honorifics():
    # "MS" and "JNR" are in the honorific/suffix lists but here they are
    # initials. Stripping them leaves a bare surname, which collapsed 1,575
    # publications into one false "Perera" identity before this guard existed.
    ms_perera = parse_name("MS Perera")
    assert ms_perera.initials == ("m",)
    assert not ms_perera.is_surname_only

    jnr = parse_name("Perera, JNR")
    assert jnr.initials == ("j",)
    assert blocking_key(ms_perera) != blocking_key(jnr)


def test_real_honorifics_and_suffixes_are_still_dropped():
    titled = parse_name("Dr. S. Perera")
    assert titled.surname == "perera"
    assert titled.initials == ("s",)
    assert "dr" in titled.dropped_tokens

    suffixed = parse_name("Silva Jr")
    assert suffixed.surname == "silva"
    assert "jr" in suffixed.dropped_tokens
