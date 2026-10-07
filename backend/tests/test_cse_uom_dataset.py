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
