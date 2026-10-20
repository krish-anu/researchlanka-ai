from __future__ import annotations

import csv
from pathlib import Path

from src.cse_uom.dataset import build_cse_uom_dataset, deduplication_key


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_builder_requires_staff_match_and_uom_affiliation(tmp_path: Path) -> None:
    roster = tmp_path / "roster.tsv"
    roster.write_text(
        "researcher_id\tofficial_name\tdisplay_name\tprofile_url\tauthor_aliases\troster_checked_on\n"
        "nisansa\tDr. N.H.N.D. de Silva\tNisansa de Silva\thttps://example.test\tNisansa de Silva\t2026-10-07\n",
        encoding="utf-8",
    )
    source = tmp_path / "source.csv"
    write_csv(
        source,
        [
            {
                "doi": "https://doi.org/10.1/verified",
                "title": "Verified work",
                "publication_year": "2024",
                "authors": "Nisansa de Silva; A. Collaborator",
                "institutions": "University of Moratuwa",
                "sri_lankan_institutions": "University of Moratuwa",
                "source_dataset": "openalex",
            },
            {
                "doi": "10.1/review",
                "title": "Needs review",
                "publication_year": "2024",
                "authors": "Nisansa de Silva",
                "institutions": "Other University",
                "sri_lankan_institutions": "",
                "source_dataset": "openalex",
            },
            {
                "doi": "10.1/not-cse",
                "title": "Not CSE",
                "publication_year": "2024",
                "authors": "Unrelated de Silva",
                "institutions": "University of Moratuwa",
                "sri_lankan_institutions": "University of Moratuwa",
                "source_dataset": "openalex",
            },
        ],
    )
    candidates = tmp_path / "candidates.csv"
    verified = tmp_path / "verified.csv"

    summary = build_cse_uom_dataset(
        input_path=source,
        roster_path=roster,
        candidate_output=candidates,
        verified_output=verified,
    )

    assert summary == {
        "staff_count": 1,
        "candidate_count": 2,
        "verified_count": 1,
        "manual_review_count": 1,
        "rejected_count": 0,
        "initials_review_count": 0,
    }
    with verified.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["uom_cse_authors"] == "Nisansa de Silva"
    assert rows[0]["cse_affiliation_verified"] == "TRUE"
    assert rows[0]["source_openalex"] == "TRUE"


def test_deduplication_prefers_doi_then_title_and_year() -> None:
    assert deduplication_key({"doi": "https://doi.org/10.1000/ABC"}) == "doi:10.1000/abc"
    assert deduplication_key(
        {"title": "A study: of AI", "publication_year": 2023}
    ) == "title-year:a study of ai:2023"


def test_builder_derives_year_from_publication_date(tmp_path: Path) -> None:
    roster = tmp_path / "roster.tsv"
    roster.write_text(
        "researcher_id\tofficial_name\tdisplay_name\tprofile_url\tauthor_aliases\troster_checked_on\n"
        "dulani\tDulani Meedeniya\tDulani Meedeniya\thttps://example.test\tDulani Meedeniya\t2026-10-07\n",
        encoding="utf-8",
    )
    source = tmp_path / "source.csv"
    write_csv(
        source,
        [{
            "doi": "10.1/date",
            "title": "Date-only work",
            "publication_date": "2022-03-21",
            "authors": "Dulani Meedeniya",
            "institutions": "University of Moratuwa",
            "sri_lankan_institutions": "University of Moratuwa",
            "source_dataset": "openalex",
        }],
    )
    candidate = tmp_path / "candidate.csv"
    verified = tmp_path / "verified.csv"
    summary = build_cse_uom_dataset(
        input_path=source,
        roster_path=roster,
        candidate_output=candidate,
        verified_output=verified,
    )
    assert summary["verified_count"] == 1
    with verified.open(encoding="utf-8") as handle:
        assert next(csv.DictReader(handle))["publication_year"] == "2022"


def test_initials_only_match_is_not_verified_by_generic_uom_affiliation(
    tmp_path: Path,
) -> None:
    roster = tmp_path / "roster.tsv"
    roster.write_text(
        "researcher_id\tofficial_name\tdisplay_name\tprofile_url\tauthor_aliases\troster_checked_on\n"
        "msd-fernando\tProf. M.S.D. Fernando\tM.S.D. Fernando\thttps://example.test\t"
        "Shantha Fernando|M.S.D. Fernando|MSD Fernando\t2026-10-07\n",
        encoding="utf-8",
    )
    source = tmp_path / "source.csv"
    write_csv(
        source,
        [
            {
                "doi": "10.1/electrical",
                "title": "Electrical engineering work",
                "publication_year": "2024",
                "authors": "Msd Fernando; A. Collaborator",
                "author_affiliations": (
                    "University of Moratuwa, "
                    "Department of Electrical Engineering, Sri Lanka"
                ),
                "institutions": "University of Moratuwa",
                "sri_lankan_institutions": "University of Moratuwa",
                "source_dataset": "openalex",
            }
        ],
    )
    candidates = tmp_path / "candidates.csv"
    verified = tmp_path / "verified.csv"
    audit = tmp_path / "audit.csv"

    summary = build_cse_uom_dataset(
        input_path=source,
        roster_path=roster,
        candidate_output=candidates,
        verified_output=verified,
        audit_output=audit,
    )

    assert summary["verified_count"] == 0
    assert summary["manual_review_count"] == 1
    assert summary["initials_review_count"] == 1
    with candidates.open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["uom_cse_authors"] == ""
    assert row["cse_unverified_roster_matches"] == "M.S.D. Fernando"
    assert row["cse_validation_decision"] == "REVIEW"


def test_verified_openalex_author_id_can_resolve_initials_only_name(
    tmp_path: Path,
) -> None:
    roster = tmp_path / "roster.tsv"
    roster.write_text(
        "researcher_id\tofficial_name\tdisplay_name\tprofile_url\tauthor_aliases\t"
        "roster_checked_on\topenalex_author_id\torcid\n"
        "rms-rathnayake\tDr. R.M.S. Rathnayake\tR.M.S. Rathnayake\t"
        "https://example.test\tR.M.S. Rathnayake\t2026-10-20\tA5126836088\t\n",
        encoding="utf-8",
    )
    source = tmp_path / "source.csv"
    write_csv(
        source,
        [{
            "doi": "10.1/openalex-id",
            "title": "Verified identifier work",
            "publication_year": "2025",
            "authors": "R.M.S. Rathnayake",
            "author_openalex_ids": "https://openalex.org/A5126836088",
            "raw_affiliation_strings": (
                "Department of Computer Science and Engineering, University of Moratuwa"
            ),
            "source_dataset": "openalex_cse_staff_fresh",
        }],
    )
    candidates = tmp_path / "candidates.csv"
    verified = tmp_path / "verified.csv"
    summary = build_cse_uom_dataset(
        input_path=source,
        roster_path=roster,
        candidate_output=candidates,
        verified_output=verified,
    )
    assert summary["verified_count"] == 1
    with verified.open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["uom_cse_researcher_ids"] == "rms-rathnayake"
    assert "verified_openalex_author_id" in row["cse_match_evidence"]


def test_reviewed_corrections_reject_collision_and_restore_omitted_author(
    tmp_path: Path,
) -> None:
    roster = tmp_path / "roster.tsv"
    roster.write_text(
        "researcher_id\tofficial_name\tdisplay_name\tprofile_url\tauthor_aliases\troster_checked_on\n"
        "msd-fernando\tProf. M.S.D. Fernando\tM.S.D. Fernando\thttps://example.test\t"
        "Shantha Fernando|M.S.D. Fernando|MSD Fernando\t2026-10-07\n",
        encoding="utf-8",
    )
    source = tmp_path / "source.csv"
    write_csv(
        source,
        [
            {
                "doi": "10.1/wrong-person",
                "title": "Wrong person",
                "publication_year": "2024",
                "authors": "Msd Fernando",
                "author_affiliations": "Department of Electrical Engineering",
                "institutions": "University of Moratuwa",
                "sri_lankan_institutions": "University of Moratuwa",
                "source_dataset": "openalex",
            },
            {
                "doi": "10.1/omitted-author",
                "title": "Confirmed work",
                "publication_year": "2020",
                "authors": "Lead Author",
                "author_affiliations": "Other University",
                "institutions": "Other University",
                "sri_lankan_institutions": "",
                "source_dataset": "openalex",
            },
        ],
    )
    corrections = tmp_path / "corrections.tsv"
    corrections.write_text(
        "doi\tdecision\tresearcher_ids\tcorrected_authors\tcorrected_author_affiliations\t"
        "evidence_url\treason\n"
        "10.1/wrong-person\tEXCLUDE_STAFF\tmsd-fernando\t\t\thttps://evidence.test/wrong\t"
        "Different person\n"
        "10.1/omitted-author\tINCLUDE_STAFF\tmsd-fernando\tLead Author; Shantha Fernando\t"
        "Department of Computer Science and Engineering, University of Moratuwa\t"
        "https://evidence.test/confirmed\tPublisher confirmed\n",
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.csv"
    verified = tmp_path / "verified.csv"
    audit = tmp_path / "audit.csv"

    summary = build_cse_uom_dataset(
        input_path=source,
        roster_path=roster,
        candidate_output=candidates,
        verified_output=verified,
        corrections_path=corrections,
        audit_output=audit,
    )

    assert summary["rejected_count"] == 1
    assert summary["verified_count"] == 1
    with verified.open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["authors"] == "Lead Author; Shantha Fernando"
    assert row["uom_cse_researcher_ids"] == "msd-fernando"
    assert row["cse_evidence_url"] == "https://evidence.test/confirmed"
    with audit.open(encoding="utf-8") as handle:
        decisions = {
            row["doi"]: row["cse_validation_decision"]
            for row in csv.DictReader(handle)
        }
    assert decisions == {
        "10.1/wrong-person": "REJECT",
        "10.1/omitted-author": "VERIFIED",
    }
