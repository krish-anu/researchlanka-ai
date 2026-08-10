"""Tests for author name parsing, ORCID handling and author disambiguation."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from research_analytics.authors import (
    AuthorVariantIndex,
    MATCH_METHOD_AFFILIATION,
    MATCH_METHOD_COAUTHOR,
    MATCH_METHOD_NAME,
    MATCH_METHOD_ORCID,
    MATCH_METHOD_REVIEWED,
    REVIEW_COMPATIBLE_NAMES_NO_EVIDENCE,
    REVIEW_EVIDENCE_SEVERAL_PEOPLE,
    REVIEW_MANUAL_ORCID_OVERRIDE,
    REVIEW_MERGED_ON_NAME_ONLY,
    AuthorDecision,
    author_blocking_key,
    author_mentions,
    author_variant_key,
    disambiguate_authors,
    load_author_decisions,
    names_compatible,
    normalize_orcid,
    parse_author_name,
    record_institution_keys,
    split_author_field,
)
from research_analytics.institutions import NationalInstitutionRegistry
from src.pipeline.build_author_disambiguated_dataset import (
    assign_row,
    build_author_disambiguated_dataset,
)
from src.quality.review_ambiguous_authors import (
    extract_decisions,
    merge_decisions,
    queue_summary,
    validate_decisions,
)


# Real ORCIDs are check-digit protected; these two are valid under MOD 11-2.
ORCID_A = "0000-0002-1825-0097"
ORCID_B = "0000-0001-5109-3700"


def make_record(**overrides: object) -> dict[str, object]:
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


def index_of(*records: dict[str, object]) -> AuthorVariantIndex:
    index = AuthorVariantIndex()
    for position, record in enumerate(records):
        index.add_record(record, record_id=f"rec{position}")
    return index


# --- name parsing -----------------------------------------------------------


def test_comma_form_splits_surname_from_given_names():
    name = parse_author_name("Perera, Kumara Nimal")
    assert name is not None
    assert name.surname == "perera"
    assert name.given == ("kumara", "nimal")


def test_given_name_first_form_uses_last_token_as_surname():
    name = parse_author_name("Kumara Nimal Perera")
    assert name is not None
    assert name.surname == "perera"
    assert name.given == ("kumara", "nimal")


def test_dotted_initial_run_expands_to_separate_initials():
    name = parse_author_name("Perera, K.M.N.")
    assert name is not None
    assert name.given == ("k", "m", "n")
    assert name.is_initials_only


def test_vancouver_style_initials_expand_but_upper_cased_names_do_not():
    assert parse_author_name("Perera KMN").given == ("k", "m", "n")
    # An entirely upper-cased record is a formatting artefact, so "ANNE" stays
    # one given name instead of becoming four initials.
    assert parse_author_name("ANNE SILVA").given == ("anne",)


def test_all_caps_vancouver_form_keeps_the_surname_first():
    name = parse_author_name("SILVA AB")
    assert name is not None
    assert (name.surname, name.given) == ("silva", ("a", "b"))


def test_honorifics_and_degree_suffixes_are_dropped():
    name = parse_author_name("Prof. Sunil de Silva, PhD")
    assert name is not None
    assert name.surname == "desilva"
    assert name.given == ("sunil",)


def test_particles_stay_with_the_surname():
    assert parse_author_name("Jan van der Berg").surname == "vanderberg"


def test_accents_and_case_do_not_change_identity():
    assert author_variant_key("José Fernández") == author_variant_key("Jose FERNANDEZ")


def test_unparseable_names_return_none():
    assert parse_author_name("") is None
    assert parse_author_name("nan") is None
    assert parse_author_name("   ,  ") is None


def test_author_field_splits_on_semicolons_not_on_name_commas():
    assert split_author_field("Perera, K.; Silva, A.") == ["Perera, K.", "Silva, A."]
    assert split_author_field("Perera, K.") == ["Perera, K."]


def test_blocking_key_is_surname_and_first_initial():
    assert author_blocking_key("Perera, Kumara Nimal") == "perera|k"
    assert author_blocking_key("Perera, K.") == "perera|k"


# --- name compatibility -----------------------------------------------------


def test_initial_is_compatible_with_the_matching_full_name():
    assert names_compatible(parse_author_name("Perera, K."), parse_author_name("Perera, Kumara"))


def test_different_spelled_out_given_names_are_incompatible():
    assert not names_compatible(
        parse_author_name("Perera, Kumara"), parse_author_name("Perera, Kamal")
    )


def test_missing_middle_name_does_not_block_compatibility():
    assert names_compatible(
        parse_author_name("Perera, Kumara Nimal"), parse_author_name("Perera, Kumara")
    )


def test_different_surnames_are_never_compatible():
    assert not names_compatible(parse_author_name("Perera, K."), parse_author_name("Silva, K."))


# --- ORCID ------------------------------------------------------------------


def test_valid_orcid_is_normalized_to_the_hyphenated_form():
    assert normalize_orcid("https://orcid.org/0000-0002-1825-0097") == ORCID_A
    assert normalize_orcid("0000000218250097") == ORCID_A


def test_orcid_with_a_bad_check_digit_is_rejected():
    assert normalize_orcid("0000-0002-1825-0098") is None
    assert normalize_orcid("not-an-orcid") is None


def test_orcid_is_attached_only_when_positions_align():
    aligned = author_mentions(
        make_record(authors="Perera, K.; Silva, A.", author_orcids=f"{ORCID_A}; {ORCID_B}")
    )
    assert [mention.orcid for mention in aligned] == [ORCID_A, ORCID_B]

    # Two authors, one ORCID: attaching it would be a guess, so it is dropped.
    mismatched = author_mentions(
        make_record(authors="Perera, K.; Silva, A.", author_orcids=ORCID_A)
    )
    assert [mention.orcid for mention in mismatched] == [None, None]


def test_inline_orcid_is_read_from_the_name_string():
    mentions = author_mentions(
        make_record(authors=f"Perera, K. (https://orcid.org/{ORCID_A}); Silva, A.")
    )
    assert mentions[0].orcid == ORCID_A
    assert mentions[0].name.surname == "perera"
    assert mentions[1].orcid is None


# --- affiliation evidence ---------------------------------------------------


def test_registry_identifiers_are_preferred_over_affiliation_text():
    keys = record_institution_keys(
        make_record(national_institution_ids="LK001", author_affiliations="University of Colombo")
    )
    assert keys == {"id:LK001"}


def test_unresolved_affiliations_still_provide_evidence_keys():
    keys = record_institution_keys(make_record(institutions="Some Unlisted Institute"))
    assert keys == {"aff:some unlisted institute"}


# --- clustering rules -------------------------------------------------------


def test_same_orcid_merges_different_spellings_across_surnames():
    index = index_of(
        make_record(authors="Perera, K.", author_orcids=ORCID_A),
        make_record(authors="Kumara Perera-Silva", author_orcids=ORCID_A),
    )
    result = disambiguate_authors(index)

    assert len(result.clusters) == 1
    cluster = next(iter(result.clusters.values()))
    assert cluster.match_method == MATCH_METHOD_ORCID
    assert cluster.confidence == "high"
    assert cluster.orcids == (ORCID_A,)


def test_different_orcids_are_never_merged_even_with_identical_names():
    index = index_of(
        make_record(
            authors="Perera, Kumara",
            author_orcids=ORCID_A,
            national_institution_ids="LK001",
        ),
        make_record(
            authors="Perera, Kumara",
            author_orcids=ORCID_B,
            national_institution_ids="LK001",
        ),
    )
    # Identical spellings collapse into one variant before any rule runs, so the
    # conflict has to be visible on the variant itself.
    variant = index.variants["perera|kumara"]
    assert variant.orcids == {ORCID_A, ORCID_B}

    other = index_of(
        make_record(authors="Perera, Kumara", author_orcids=ORCID_A, national_institution_ids="LK001"),
        make_record(authors="Perera, K.", author_orcids=ORCID_B, national_institution_ids="LK001"),
    )
    result = disambiguate_authors(other)
    assert len(result.clusters) == 2
    assert result.stats.orcid_blocked_merges >= 1


def test_shared_affiliation_merges_an_initial_with_a_full_name():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
    )
    result = disambiguate_authors(index)

    assert len(result.clusters) == 1
    cluster = next(iter(result.clusters.values()))
    assert cluster.match_method == MATCH_METHOD_AFFILIATION
    assert cluster.confidence == "medium"
    assert cluster.preferred_name.startswith("Perera")


def test_different_affiliations_do_not_merge_incompatible_names():
    index = index_of(
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
        make_record(authors="Perera, Kamal", national_institution_ids="LK001"),
    )
    result = disambiguate_authors(index)
    assert len(result.clusters) == 2


def test_shared_coauthor_merges_when_no_affiliation_is_available():
    index = index_of(
        make_record(authors="Perera, K.; Bandara, Nimal"),
        make_record(authors="Perera, Kumara; Bandara, Nimal"),
    )
    result = disambiguate_authors(index)

    perera = result.author_for("Perera, K.")
    assert perera is not None
    assert perera.match_method == MATCH_METHOD_COAUTHOR
    assert result.author_for("Perera, Kumara").author_id == perera.author_id


def test_the_same_name_written_both_ways_round_is_one_variant():
    index = index_of(
        make_record(authors="Perera, Kumara Nimal"),
        make_record(authors="Kumara Nimal Perera"),
    )
    assert len(index.variants) == 1
    assert len(disambiguate_authors(index).clusters) == 1


def test_initialled_name_joins_the_only_spelled_out_name_it_fits():
    index = index_of(
        make_record(authors="Perera, K."),
        make_record(authors="Perera, Kumara"),
    )
    result = disambiguate_authors(index)

    assert len(result.clusters) == 1
    cluster = next(iter(result.clusters.values()))
    assert cluster.match_method == MATCH_METHOD_NAME
    assert cluster.confidence == "low"
    assert REVIEW_MERGED_ON_NAME_ONLY in cluster.review_reasons


def test_initialled_name_stays_apart_when_two_spelled_out_names_fit():
    index = index_of(
        make_record(authors="Perera, K."),
        make_record(authors="Perera, Kumara"),
        make_record(authors="Perera, Kalpana"),
    )
    result = disambiguate_authors(index)

    assert len(result.clusters) == 3
    assert len(result.review_pairs) >= 2


def test_two_initialled_names_never_merge_on_the_name_alone():
    index = index_of(
        make_record(authors="Perera, K."),
        make_record(authors="Perera, K. M."),
    )
    assert len(disambiguate_authors(index).clusters) == 2


def test_coauthor_evidence_can_require_more_than_one_shared_name():
    records = (
        make_record(authors="Perera, K.; Bandara, Nimal", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara; Bandara, Nimal", national_institution_ids="LK002"),
    )
    merged = disambiguate_authors(index_of(*records))
    assert (
        merged.author_for("Perera, K.").author_id == merged.author_for("Perera, Kumara").author_id
    )

    # One shared coauthor is no longer enough, and the differing institutions
    # keep the weaker name rule from merging them either.
    strict = disambiguate_authors(index_of(*records), min_shared_coauthors=2)
    assert (
        strict.author_for("Perera, K.").author_id != strict.author_for("Perera, Kumara").author_id
    )


def test_an_initial_shared_by_two_people_merges_into_neither():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
        make_record(authors="Perera, K.", national_institution_ids="LK003"),
        make_record(authors="Perera, Kamal", national_institution_ids="LK003"),
    )
    result = disambiguate_authors(index)

    # Merging "K." into either one would be arbitrary; merging into both would
    # fuse two researchers.
    assert len(result.clusters) == 3
    initialled = result.author_for("Perera, K.")
    assert REVIEW_EVIDENCE_SEVERAL_PEOPLE in initialled.review_reasons
    assert len(result.review_pairs) == 2
    assert all(
        REVIEW_EVIDENCE_SEVERAL_PEOPLE in pair.reasons for pair in result.review_pairs
    )


def test_spelled_out_names_that_disagree_never_join_through_a_shared_cluster():
    index = index_of(
        # ORCID ties the initialled spelling to Kumara ...
        make_record(authors="Perera, K.", author_orcids=ORCID_A),
        make_record(authors="Perera, Kumara", author_orcids=ORCID_A),
        # ... so Kamal's shared institution must not pull him in behind it.
        make_record(authors="Perera, K.", national_institution_ids="LK003"),
        make_record(authors="Perera, Kamal", national_institution_ids="LK003"),
    )
    result = disambiguate_authors(index)

    assert result.author_for("Perera, K.").author_id == result.author_for("Perera, Kumara").author_id
    assert result.author_for("Perera, Kamal").author_id != result.author_for("Perera, K.").author_id
    assert result.stats.name_blocked_merges >= 1


def test_author_identifiers_are_stable_across_runs():
    records = [
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
    ]
    first = disambiguate_authors(index_of(*records))
    second = disambiguate_authors(index_of(*reversed(records)))
    assert set(first.clusters) == set(second.clusters)


# --- review queue -----------------------------------------------------------


def test_compatible_names_without_evidence_are_queued_for_review():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK002"),
    )
    result = disambiguate_authors(index)

    assert len(result.clusters) == 2
    assert len(result.review_pairs) == 1
    pair = result.review_pairs[0]
    assert pair.blocking_key == "perera|k"
    assert REVIEW_COMPATIBLE_NAMES_NO_EVIDENCE in pair.reasons


def test_conflicting_orcids_are_settled_and_never_queued():
    index = index_of(
        make_record(authors="Perera, Kumara", author_orcids=ORCID_A),
        make_record(authors="Perera, K.", author_orcids=ORCID_B),
    )
    result = disambiguate_authors(index)
    assert len(result.clusters) == 2
    assert result.review_pairs == []


def test_review_pair_disappears_once_a_decision_exists():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK002"),
    )
    decision = AuthorDecision(
        decision="same_author",
        variant_key_a="perera|k",
        variant_key_b="perera|kumara",
        reviewer="reviewer",
    )
    result = disambiguate_authors(index, decisions=[decision])

    assert len(result.clusters) == 1
    assert result.review_pairs == []
    assert result.stats.decision_merges == 1


def test_reviewed_split_survives_evidence_that_would_have_merged():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
    )
    decision = AuthorDecision(
        decision="different_author",
        variant_key_a="perera|k",
        variant_key_b="perera|kumara",
    )
    result = disambiguate_authors(index, decisions=[decision])

    assert len(result.clusters) == 2
    assert result.stats.decision_splits == 1


def test_a_settled_pair_reports_the_reviewer_and_drops_the_ambiguity_flag():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
        make_record(authors="Perera, K.", national_institution_ids="LK003"),
        make_record(authors="Perera, Kamal", national_institution_ids="LK003"),
    )
    decisions = [
        AuthorDecision("same_author", "perera|k", "perera|kumara", reviewer="reviewer"),
        AuthorDecision("different_author", "perera|k", "perera|kamal", reviewer="reviewer"),
    ]
    result = disambiguate_authors(index, decisions=decisions)

    merged = result.author_for("Perera, K.")
    assert merged.author_id == result.author_for("Perera, Kumara").author_id
    assert merged.match_method == MATCH_METHOD_REVIEWED
    assert merged.confidence == "high"
    # Nothing is left to ask about, so the identity stops marking its records
    # ambiguous.
    assert REVIEW_EVIDENCE_SEVERAL_PEOPLE not in merged.review_reasons
    assert result.review_pairs == []


def test_reviewed_merge_overriding_an_orcid_conflict_is_flagged():
    index = index_of(
        make_record(authors="Perera, Kumara", author_orcids=ORCID_A),
        make_record(authors="Perera, K.", author_orcids=ORCID_B),
    )
    decision = AuthorDecision(
        decision="same_author",
        variant_key_a="perera|kumara",
        variant_key_b="perera|k",
        note="duplicate ORCID registration confirmed with the author",
    )
    result = disambiguate_authors(index, decisions=[decision])

    assert len(result.clusters) == 1
    cluster = next(iter(result.clusters.values()))
    assert REVIEW_MANUAL_ORCID_OVERRIDE in cluster.review_reasons
    assert result.stats.manual_orcid_overrides == 1


def test_oversized_surname_blocks_skip_pairwise_matching_and_are_reported():
    records = [make_record(authors=f"Perera, K{position}umara") for position in range(6)]
    result = disambiguate_authors(index_of(*records), max_block_variants=2)
    assert result.stats.oversized_blocks >= 1


# --- record assignment ------------------------------------------------------


def test_assign_row_writes_identifiers_methods_and_the_ambiguity_flag():
    index = index_of(
        make_record(authors="Perera, K.", national_institution_ids="LK001"),
        make_record(authors="Perera, Kumara", national_institution_ids="LK001"),
    )
    result = disambiguate_authors(index)
    row = make_record(authors="Perera, K.; Silva, A.", national_institution_ids="LK001")
    index.add_record(row, record_id="extra")
    result = disambiguate_authors(index)

    assigned = assign_row(row, result)
    assert len(assigned["author_ids"].split("; ")) == 2
    assert assigned["author_disambiguation_level"] in {
        "orcid",
        "affiliation",
        "coauthor",
        "name",
        "singleton",
    }
    assert isinstance(assigned["ambiguous_author_flag"], bool)


def test_records_without_parseable_authors_get_an_empty_assignment():
    result = disambiguate_authors(index_of(make_record(authors="Perera, K.")))
    assigned = assign_row(make_record(authors=""), result)
    assert assigned["author_ids"] == ""
    assert assigned["author_disambiguation_level"] == "none"


# --- decisions file ---------------------------------------------------------


def test_missing_decisions_file_is_treated_as_no_decisions(tmp_path: Path):
    assert load_author_decisions(tmp_path / "absent.csv") == []


def test_decisions_file_rejects_unknown_verdicts(tmp_path: Path):
    path = tmp_path / "decisions.csv"
    path.write_text(
        "decision,variant_key_a,variant_key_b,reviewer,note\n"
        "maybe,perera|k,perera|kumara,reviewer,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="decision must be one of"):
        load_author_decisions(path)


def test_validate_reports_contradictory_and_stale_decisions(tmp_path: Path):
    path = tmp_path / "decisions.csv"
    path.write_text(
        "decision,variant_key_a,variant_key_b,reviewer,note\n"
        "same_author,perera|k,perera|kumara,a,\n"
        "different_author,perera|kumara,perera|k,b,\n",
        encoding="utf-8",
    )
    problems = validate_decisions(path, known_variant_keys={"perera|k"})
    assert any("both same_author and different_author" in problem for problem in problems)
    assert any("perera|kumara" in problem for problem in problems)


# --- review tooling ---------------------------------------------------------


def test_queue_summary_counts_reasons_and_outstanding_work():
    rows = [
        {
            "reasons": "compatible_names_no_evidence; initials_only_name",
            "needs_review": "True",
            "mentions_total": "12",
            "decision": "",
        },
        {
            "reasons": "compatible_names_no_evidence",
            "needs_review": "False",
            "mentions_total": "2",
            "decision": "same_author",
        },
    ]
    summary = queue_summary(rows)
    assert summary["pairs"] == 2
    assert summary["flagged_pairs"] == 1
    assert summary["decided_pairs"] == 1
    assert summary["undecided_flagged_pairs"] == 1
    assert summary["reasons"]["compatible_names_no_evidence"] == 2
    assert summary["mentions_in_queue"] == 14


def test_extract_decisions_keeps_filled_rows_and_reports_bad_verdicts():
    rows = [
        {"decision": "", "variant_key_a": "a|x", "variant_key_b": "a|y"},
        {
            "decision": "Same_Author",
            "variant_key_a": "b|x",
            "variant_key_b": "b|y",
            "reviewer": "reviewer",
            "note": "same lab",
        },
        {"decision": "merge", "variant_key_a": "c|x", "variant_key_b": "c|y"},
    ]
    decisions, problems = extract_decisions(rows)
    assert [row["variant_key_a"] for row in decisions] == ["b|x"]
    assert decisions[0]["decision"] == "same_author"
    assert len(problems) == 1


def test_merge_decisions_replaces_a_changed_verdict_for_the_same_pair():
    existing = [
        {
            "decision": "same_author",
            "variant_key_a": "a|x",
            "variant_key_b": "a|y",
            "reviewer": "",
            "note": "",
        }
    ]
    new_rows = [
        {
            "decision": "different_author",
            "variant_key_a": "a|y",
            "variant_key_b": "a|x",
            "reviewer": "second",
            "note": "checked ORCID",
        }
    ]
    merged, added, updated = merge_decisions(existing, new_rows)
    assert (added, updated) == (0, 1)
    assert len(merged) == 1
    assert merged[0]["decision"] == "different_author"


# --- pipeline ---------------------------------------------------------------


INPUT_ROWS = [
    {
        "record_number": "1",
        "title": "Rainfall variability",
        "authors": "Perera, K.; Bandara, Nimal",
        "author_orcids": f"{ORCID_A}; {ORCID_B}",
        "author_affiliations": "University of Colombo",
        "institutions": "University of Colombo",
        "national_institution_ids": "LK001",
        "publication_year": "2019",
        "source_dataset": "openalex",
    },
    {
        "record_number": "2",
        "title": "Rainfall variability II",
        "authors": "Perera, Kumara; Bandara, Nimal",
        "author_orcids": "",
        "author_affiliations": "University of Colombo",
        "institutions": "University of Colombo",
        "national_institution_ids": "LK001",
        "publication_year": "2021",
        "source_dataset": "crossref",
    },
    {
        "record_number": "3",
        "title": "Unrelated study",
        "authors": "Perera, Kamal",
        "author_orcids": "",
        "author_affiliations": "University of Moratuwa",
        "institutions": "University of Moratuwa",
        "national_institution_ids": "LK003",
        "publication_year": "2022",
        "source_dataset": "openalex",
    },
]


@pytest.fixture()
def input_csv(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(INPUT_ROWS[0]))
        writer.writeheader()
        writer.writerows(INPUT_ROWS)
    return path


def test_pipeline_writes_dataset_registry_summary_and_review_queue(
    tmp_path: Path, input_csv: Path
):
    output_csv = tmp_path / "out.csv"
    registry_csv = tmp_path / "registry.csv"
    summary_csv = tmp_path / "summary.csv"
    review_csv = tmp_path / "review.csv"

    index, result = build_author_disambiguated_dataset(
        input_csv,
        output_csv,
        registry_csv,
        summary_csv,
        review_csv,
        decisions_csv=tmp_path / "missing_decisions.csv",
    )

    assert index.stats.records == 3
    assert index.stats.author_mentions == 5

    with output_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert all(row["author_ids"] for row in rows)
    # "Perera, K." and "Perera, Kumara" share an institution and a coauthor.
    first_author_ids = [row["author_ids"].split("; ")[0] for row in rows]
    assert first_author_ids[0] == first_author_ids[1]
    assert first_author_ids[2] != first_author_ids[0]
    # The identity carrying the ORCID reports the strongest evidence available.
    assert rows[0]["author_match_methods"].split("; ")[0] == MATCH_METHOD_ORCID

    with registry_csv.open(newline="", encoding="utf-8") as handle:
        registry_rows = {row["author_id"]: row for row in csv.DictReader(handle)}
    assert len(registry_rows) == len(result.clusters)
    merged = registry_rows[first_author_ids[0]]
    assert merged["orcids"] == ORCID_A
    assert merged["publications"] == "2"
    assert merged["year_min"] == "2019" and merged["year_max"] == "2021"
    assert "perera|k" in merged["name_variants"]

    with summary_csv.open(newline="", encoding="utf-8") as handle:
        summary = {row["metric"]: row["value"] for row in csv.DictReader(handle)}
    assert summary["records"] == "3"
    assert summary["author_mentions"] == "5"
    assert summary["entity_fuzzy_auto_resolution_enabled"] == "False"
    assert summary["mention_assignment_rate_pass"] == "True"

    with review_csv.open(newline="", encoding="utf-8") as handle:
        review_rows = list(csv.DictReader(handle))
    assert all(row["decision"] == "" for row in review_rows)


def test_pipeline_applies_reviewed_decisions(tmp_path: Path, input_csv: Path):
    decisions_csv = tmp_path / "decisions.csv"
    decisions_csv.write_text(
        "decision,variant_key_a,variant_key_b,reviewer,note\n"
        "different_author,perera|k,perera|kumara,reviewer,different people\n",
        encoding="utf-8",
    )

    _, result = build_author_disambiguated_dataset(
        input_csv,
        tmp_path / "out.csv",
        tmp_path / "registry.csv",
        tmp_path / "summary.csv",
        tmp_path / "review.csv",
        decisions_csv=decisions_csv,
    )

    assert result.stats.decision_splits == 1
    assert result.author_for("Perera, K.").author_id != result.author_for("Perera, Kumara").author_id


# --- institution registry ambiguity ----------------------------------------


def test_registry_reports_an_alias_claimed_by_two_institutions(tmp_path: Path):
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text(
        "institution_id,preferred_name,alternative_name,country_code,ror_id,"
        "parent_institution_id,institution_type,source_institution_id\n"
        "LK001,University of Colombo,University of Colombo,LK,,,university,cmb\n"
        "LK003,University of Moratuwa,University of Colombo,LK,,,university,uom\n",
        encoding="utf-8",
    )
    registry = NationalInstitutionRegistry.from_csv(registry_path, country_code="LK")

    assert registry.ambiguous_aliases() == [("university of colombo", ["LK001", "LK003"])]
    # The first claim still wins, so resolution stays deterministic.
    assert registry.resolve_name("University of Colombo").institution_id == "LK001"
