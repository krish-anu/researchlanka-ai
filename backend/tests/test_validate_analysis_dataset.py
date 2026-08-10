"""Tests for the author, institution, citation and collaboration validators."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from research_analytics.institutions import NationalInstitutionRegistry
from src.quality.validate_analysis_dataset import (
    AuthorValidator,
    CitationValidator,
    CollaborationValidator,
    Gate,
    InstitutionValidator,
    build_validators,
    default_input_csv,
    record_identifier,
    render_report,
    run_validators,
    write_report,
)


ORCID_VALID = "0000-0002-1825-0097"
ORCID_BAD_CHECKSUM = "0000-0002-1825-0098"

REGISTRY_ROWS = [
    "institution_id,preferred_name,alternative_name,country_code,ror_id,"
    "parent_institution_id,institution_type,source_institution_id",
    "LK001,University of Colombo,University of Colombo,LK,,,university,cmb",
    "LK003,University of Moratuwa,University of Moratuwa,LK,,,university,uom",
]


@pytest.fixture()
def registry(tmp_path: Path) -> NationalInstitutionRegistry:
    path = tmp_path / "institutions.csv"
    path.write_text("\n".join(REGISTRY_ROWS) + "\n", encoding="utf-8")
    return NationalInstitutionRegistry.from_csv(path, country_code="LK")


def run(validator, rows: list[dict[str, object]]):
    for position, row in enumerate(rows):
        validator.add_row(row, record_id=f"rec{position}")
    return validator.report()


def issue_names(report) -> set[str]:
    return set(report.issue_counts)


def metric(report, name: str):
    for key, value in report.metrics:
        if key == name:
            return value
    raise AssertionError(f"{name} not in report metrics")


def gate(report, name: str) -> Gate:
    for item in report.gates:
        if item.name == name:
            return item
    raise AssertionError(f"{name} not in report gates")


# --- gates ------------------------------------------------------------------


def test_gate_comparisons_and_skipping():
    assert Gate("a", 0.95, 0.9).passed
    assert not Gate("b", 0.5, 0.9).passed
    assert Gate("c", 0, 0, comparison="==").passed
    assert not Gate("d", 3, 0, comparison="==").passed
    assert Gate("e", 5, 2, comparison="<=").passed is False
    # A check with nothing to measure is skipped rather than failed.
    skipped = Gate("f", 0.0, 0.9, skipped=True, note="no values")
    assert skipped.passed
    assert "skipped" in skipped.status


def test_unknown_comparison_is_rejected():
    with pytest.raises(ValueError, match="unknown comparison"):
        Gate("a", 1, 1, comparison="~=").passed


# --- authors ----------------------------------------------------------------


def test_author_validator_accepts_a_clean_record():
    report = run(
        AuthorValidator(),
        [
            {
                "authors": "Perera, Kumara; Silva, Anil",
                "author_count": "2",
                "author_orcids": f"{ORCID_VALID}; 0000-0001-5109-3700",
            }
        ],
    )
    assert report.passed
    assert issue_names(report) == set()
    assert metric(report, "author_presence_rate") == 1.0
    assert metric(report, "rows_with_position_aligned_orcids") == 1


def test_author_validator_flags_missing_and_placeholder_names():
    report = run(
        AuthorValidator(),
        [
            {"authors": "", "author_count": "0", "author_orcids": ""},
            {"authors": "Anonymous", "author_count": "1", "author_orcids": ""},
        ],
    )
    assert "missing_authors" in issue_names(report)
    assert "placeholder_author_name" in issue_names(report)
    assert metric(report, "author_presence_rate") == 0.5
    assert not gate(report, "author_presence_rate").passed


def test_author_validator_flags_a_count_that_disagrees_with_the_names():
    report = run(
        AuthorValidator(),
        [{"authors": "Perera, K.; Silva, A.", "author_count": "5", "author_orcids": ""}],
    )
    assert "author_count_mismatch" in issue_names(report)
    assert metric(report, "author_count_agreement_rate") == 0.0
    assert not gate(report, "author_count_agreement_rate").passed


def test_author_validator_rejects_an_orcid_with_a_bad_check_digit():
    report = run(
        AuthorValidator(),
        [{"authors": "Perera, K.", "author_count": "1", "author_orcids": ORCID_BAD_CHECKSUM}],
    )
    assert "invalid_orcid" in issue_names(report)
    assert metric(report, "orcid_validity_rate") == 0.0
    assert not gate(report, "orcid_validity_rate").passed


def test_author_validator_reports_unaligned_orcids_without_failing_a_gate():
    report = run(
        AuthorValidator(),
        [
            {
                "authors": "Perera, K.; Silva, A.; Bandara, N.",
                "author_count": "3",
                "author_orcids": ORCID_VALID,
            }
        ],
    )
    # Compacted ORCID lists are normal; they are recorded, not failed.
    assert "orcid_count_not_aligned_with_authors" in issue_names(report)
    assert report.passed


def test_author_validator_flags_duplicate_names_and_author_id_mismatch():
    report = run(
        AuthorValidator(),
        [
            {
                "authors": "Perera, Kumara; Perera, Kumara",
                "author_count": "2",
                "author_orcids": "",
                "author_ids": "A1",
            }
        ],
    )
    assert "duplicate_author_in_record" in issue_names(report)
    assert "author_id_count_mismatch" in issue_names(report)


def test_author_gates_are_skipped_when_the_columns_are_absent():
    report = run(AuthorValidator(), [{"authors": "Perera, K."}])
    assert gate(report, "author_count_agreement_rate").status.startswith("skipped")
    assert gate(report, "orcid_validity_rate").status.startswith("skipped")
    assert report.passed


# --- institutions -----------------------------------------------------------


def test_institution_validator_accepts_a_resolved_record(registry):
    report = run(
        InstitutionValidator(registry=registry),
        [
            {
                "institutions": "University of Colombo",
                "national_institution_ids": "LK001",
                "countries": "LK",
                "institution_source": "metadata",
                "author_affiliations": "University of Colombo",
            }
        ],
    )
    assert report.passed
    assert metric(report, "institution_resolution_rate") == 1.0


def test_institution_validator_flags_an_identifier_that_is_not_in_the_registry(registry):
    report = run(
        InstitutionValidator(registry=registry),
        [
            {
                "institutions": "University of Colombo",
                "national_institution_ids": "LK999",
                "countries": "LK",
                "institution_source": "metadata",
            }
        ],
    )
    assert "unknown_registry_identifier" in issue_names(report)
    assert metric(report, "unknown_registry_identifiers") == 1
    assert not gate(report, "unknown_registry_identifiers").passed


def test_institution_validator_flags_unrecognised_countries_and_sources(registry):
    report = run(
        InstitutionValidator(registry=registry),
        [
            {
                "institutions": "University of Colombo",
                "national_institution_ids": "LK001",
                "countries": "Atlantis",
                "institution_source": "guesswork",
            }
        ],
    )
    assert "unrecognised_country" in issue_names(report)
    assert "unknown_institution_source" in issue_names(report)
    # A record resolving to a national institution must carry the country too.
    assert "national_institution_without_national_country" in issue_names(report)
    assert not gate(report, "unknown_institution_source_values").passed


def test_institution_validator_notes_affiliation_text_with_no_institution(registry):
    report = run(
        InstitutionValidator(registry=registry),
        [{"institutions": "", "author_affiliations": "Some Unlisted Institute", "countries": ""}],
    )
    assert "affiliation_present_without_institution" in issue_names(report)
    assert metric(report, "rows_with_affiliation_but_no_institution") == 1


def test_institution_identifier_gate_is_skipped_without_a_registry():
    report = run(
        InstitutionValidator(registry=None),
        [{"institutions": "University of Colombo", "national_institution_ids": "LK999"}],
    )
    assert gate(report, "unknown_registry_identifiers").status.startswith("skipped")
    assert metric(report, "registry_loaded") is False


# --- citations --------------------------------------------------------------


def test_citation_validator_accepts_plausible_counts():
    report = run(
        CitationValidator(),
        [
            {"citation_count": "12", "reference_count": "40", "publication_year": "2020"},
            {"citation_count": "0", "reference_count": "8", "publication_year": "2021"},
        ],
    )
    assert report.passed
    assert metric(report, "zero_citation_rows") == 1
    assert metric(report, "max_citation_count") == 12
    assert metric(report, "total_citations") == 12


def test_citation_validator_flags_non_numeric_and_negative_counts():
    report = run(
        CitationValidator(),
        [
            {"citation_count": "many", "reference_count": "3", "publication_year": "2020"},
            {"citation_count": "-4", "reference_count": "-1", "publication_year": "2020"},
        ],
    )
    assert "citation_count_not_numeric" in issue_names(report)
    assert "negative_citation_count" in issue_names(report)
    assert "negative_reference_count" in issue_names(report)
    assert not gate(report, "citation_numeric_validity_rate").passed
    assert not gate(report, "negative_citation_counts").passed


def test_citation_validator_flags_implausible_counts_and_years():
    report = run(
        CitationValidator(),
        [
            {"citation_count": "9999999", "reference_count": "1", "publication_year": "2020"},
            {"citation_count": "1", "reference_count": "1", "publication_year": "1650"},
        ],
    )
    assert "implausible_citation_count" in issue_names(report)
    assert "implausible_publication_year" in issue_names(report)
    assert not gate(report, "implausible_citation_counts").passed


def test_citation_validator_flags_citations_on_a_future_publication():
    report = run(
        CitationValidator(),
        [{"citation_count": "5", "reference_count": "1", "publication_year": "2999"}],
    )
    # 2999 is outside the plausible range, so the year itself is reported and the
    # citation cannot be judged against it.
    assert "implausible_publication_year" in issue_names(report)


def test_citation_validator_separates_missing_from_zero():
    report = run(
        CitationValidator(),
        [
            {"citation_count": "", "publication_year": "2020"},
            {"citation_count": "0", "publication_year": "2020"},
        ],
    )
    assert metric(report, "rows_missing_citation_count") == 1
    assert metric(report, "zero_citation_rows") == 1
    assert metric(report, "citation_coverage") == 0.5


# --- collaboration ----------------------------------------------------------


def test_collaboration_validator_accepts_consistent_records():
    report = run(
        CollaborationValidator(),
        [
            {
                "collaboration_type": "domestic_single_institution",
                "collaboration_scope": "local",
                "national_institution_ids": "LK001",
                "countries": "LK",
                "unresolved_institutions": "",
            },
            {
                "collaboration_type": "international_collaboration",
                "collaboration_scope": "international",
                "national_institution_ids": "LK001",
                "countries": "LK; GB",
                "unresolved_institutions": "",
            },
        ],
    )
    assert report.passed
    assert metric(report, "total_inconsistencies") == 0


def test_collaboration_validator_flags_a_scope_that_contradicts_its_type():
    report = run(
        CollaborationValidator(),
        [
            {
                "collaboration_type": "international_collaboration",
                "collaboration_scope": "local",
                "national_institution_ids": "LK001",
                "countries": "LK; GB",
                "unresolved_institutions": "",
            }
        ],
    )
    assert "scope_does_not_match_type" in issue_names(report)
    assert not gate(report, "scope_type_mismatches").passed


def test_collaboration_validator_flags_international_without_a_foreign_country():
    report = run(
        CollaborationValidator(),
        [
            {
                "collaboration_type": "international_collaboration",
                "collaboration_scope": "international",
                "national_institution_ids": "LK001",
                "countries": "LK",
                "unresolved_institutions": "",
            }
        ],
    )
    assert "international_without_foreign_country" in issue_names(report)
    assert not gate(report, "collaboration_inconsistencies").passed


def test_collaboration_validator_flags_multi_institution_with_one_institution():
    report = run(
        CollaborationValidator(),
        [
            {
                "collaboration_type": "domestic_multi_institution",
                "collaboration_scope": "local",
                "national_institution_ids": "LK001",
                "countries": "LK",
                "unresolved_institutions": "",
            }
        ],
    )
    assert "multi_institution_without_two_institutions" in issue_names(report)


def test_collaboration_validator_flags_unresolved_without_evidence_and_unknown_types():
    report = run(
        CollaborationValidator(),
        [
            {
                "collaboration_type": "unresolved_affiliation",
                "collaboration_scope": "unknown",
                "national_institution_ids": "",
                "countries": "",
                "unresolved_institutions": "",
            },
            {
                "collaboration_type": "mystery",
                "collaboration_scope": "unknown",
                "national_institution_ids": "",
                "countries": "",
                "unresolved_institutions": "",
            },
        ],
    )
    assert "unresolved_without_unresolved_institutions" in issue_names(report)
    assert "unknown_collaboration_type" in issue_names(report)
    assert not gate(report, "unknown_collaboration_types").passed


def test_collaboration_gate_is_skipped_when_the_column_is_absent():
    report = run(CollaborationValidator(), [{"title": "No collaboration columns here"}])
    assert gate(report, "collaboration_presence_rate").status.startswith("skipped")
    assert report.passed


# --- runner -----------------------------------------------------------------


DATASET_ROWS = [
    {
        "record_number": "1",
        "authors": "Perera, Kumara; Silva, Anil",
        "author_count": "2",
        "author_orcids": ORCID_VALID,
        "institutions": "University of Colombo",
        "national_institution_ids": "LK001",
        "countries": "LK",
        "institution_source": "metadata",
        "author_affiliations": "University of Colombo",
        "unresolved_institutions": "",
        "collaboration_type": "domestic_single_institution",
        "collaboration_scope": "local",
        "citation_count": "7",
        "reference_count": "31",
        "publication_year": "2020",
    },
    {
        "record_number": "2",
        "authors": "Bandara, Nimal",
        "author_count": "9",
        "author_orcids": ORCID_BAD_CHECKSUM,
        "institutions": "University of Moratuwa",
        "national_institution_ids": "LK999",
        "countries": "Atlantis",
        "institution_source": "metadata",
        "author_affiliations": "University of Moratuwa",
        "unresolved_institutions": "",
        "collaboration_type": "international_collaboration",
        "collaboration_scope": "local",
        "citation_count": "-3",
        "reference_count": "10",
        "publication_year": "2021",
    },
]


@pytest.fixture()
def dataset_csv(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DATASET_ROWS[0]))
        writer.writeheader()
        writer.writerows(DATASET_ROWS)
    return path


def test_record_identifier_prefers_stable_identifiers():
    assert record_identifier({"record_number": "7", "doi": "10.1/x"}, 3) == "7"
    assert record_identifier({"doi": "10.1/x"}, 3) == "10.1/x"
    assert record_identifier({}, 3) == "row:3"


def test_running_every_validator_over_one_dataset(dataset_csv, registry, tmp_path):
    validators = build_validators(
        ["authors", "institutions", "citations", "collaboration"], registry=registry
    )
    reports = run_validators(dataset_csv, validators)
    by_name = {report.name: report for report in reports}

    assert [report.name for report in reports] == [
        "authors",
        "institutions",
        "citations",
        "collaboration",
    ]
    assert all(report.rows == 2 for report in reports)

    # The second row is deliberately broken in all four ways.
    assert "invalid_orcid" in issue_names(by_name["authors"])
    assert "author_count_mismatch" in issue_names(by_name["authors"])
    assert "unknown_registry_identifier" in issue_names(by_name["institutions"])
    assert "unrecognised_country" in issue_names(by_name["institutions"])
    assert "negative_citation_count" in issue_names(by_name["citations"])
    assert "scope_does_not_match_type" in issue_names(by_name["collaboration"])
    assert not any(report.passed for report in reports)

    # Issues carry the record identifier, so a count can be traced to rows.
    assert {issue.record_id for issue in by_name["citations"].issues} == {"2"}


def test_reports_are_written_as_summary_gates_and_issues(dataset_csv, registry, tmp_path):
    reports = run_validators(dataset_csv, build_validators(["citations"], registry=registry))
    written = write_report(reports[0], tmp_path / "validation")

    summary = {
        row["metric"]: row["value"]
        for row in csv.DictReader((written["summary"]).open(encoding="utf-8"))
    }
    assert summary["check"] == "citations"
    assert summary["rows"] == "2"
    assert summary["passed"] == "False"

    gates = list(csv.DictReader(written["gates"].open(encoding="utf-8")))
    assert any(row["gate"] == "negative_citation_counts" and row["status"] == "FAIL" for row in gates)

    issues = list(csv.DictReader(written["issues"].open(encoding="utf-8")))
    assert {row["issue"] for row in issues} == {"negative_citation_count"}


def test_issue_samples_are_capped_but_counts_stay_complete():
    validator = CitationValidator(max_issues=2)
    report = run(
        validator,
        [{"citation_count": "-1", "publication_year": "2020"} for _ in range(10)],
    )
    assert len(report.issues) == 2
    assert report.issues_truncated
    assert report.issue_counts["negative_citation_count"] == 10


def test_rendering_a_report_names_the_failing_gate(dataset_csv, registry):
    reports = run_validators(dataset_csv, build_validators(["citations"], registry=registry))
    rendered = render_report(reports[0])
    assert "citations: FAIL" in rendered
    assert "negative_citation_counts" in rendered


def test_unknown_check_names_are_rejected():
    with pytest.raises(ValueError, match="unknown check"):
        build_validators(["authors", "nonsense"])


def test_default_input_prefers_the_most_normalized_dataset():
    assert default_input_csv().name.startswith("common_publications_final")
