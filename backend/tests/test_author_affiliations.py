"""Author rows on new publications, categories, and institution history."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.api.core.errors import APIError
from src.api.services import author_profiles as authors
from src.api.services.author_publication_lookup import openalex_author
from src.api.services.author_reference import (
    canonical_institution,
    institution_at_time,
    institution_breakdown,
)


def row(name, institution="University of Moratuwa", **extra):
    return {"name": name, "institution": institution, **extra}


# ------------------------------------------------------------ author rows


def test_each_author_needs_the_institution_they_were_at() -> None:
    with pytest.raises(APIError) as error:
        authors.validate_submission_authors([row("A One"), {"name": "B Two"}])

    assert error.value.code == "institution_required"
    assert error.value.details == {"field": "institution", "index": 1}


def test_registry_aliases_become_the_label_rankings_count() -> None:
    rows = authors.validate_submission_authors(
        [
            row("A One", "UOM"),
            row("B Two", "University of Oxford", country_code="gb"),
            row("C Three", "Some Local Institute"),
        ]
    )

    assert [(item["institution"], item["country_code"]) for item in rows] == [
        ("University of Moratuwa", "LK"),
        ("University of Oxford", "GB"),
        ("Some Local Institute", None),
    ]


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ([row("A One"), row("a  one")], "duplicate_author"),
        ([row("A One", country_code="Sri Lanka")], "invalid_country"),
    ],
)
def test_author_row_errors_point_at_the_row(rows, code) -> None:
    with pytest.raises(APIError) as error:
        authors.validate_submission_authors(rows)
    assert error.value.code == code
    assert error.value.details["index"] == len(rows) - 1


def test_exactly_one_row_is_the_submitter() -> None:
    rows = authors.validate_submission_authors([row("A One"), row("B Two", is_submitter=True)])
    assert authors.mark_submitter(rows, None)["name"] == "B Two"

    # Older clients name the submitter instead of flagging the row.
    rows = authors.validate_submission_authors([row("A One"), row("B Two")])
    assert authors.mark_submitter(rows, "a one")["name"] == "A One"

    with pytest.raises(APIError, match="Mark which listed author you are"):
        authors.mark_submitter(authors.validate_submission_authors([row("A One")]), None)
    with pytest.raises(APIError, match="Only one author can be you"):
        authors.mark_submitter(
            authors.validate_submission_authors([row("A One", is_submitter=True), row("B Two", is_submitter=True)]),
            None,
        )


def test_openalex_authorship_keeps_its_own_institution_and_country() -> None:
    author = openalex_author(
        {
            "author": {"display_name": "Roshan Ragel"},
            "institutions": [{"display_name": "University of Peradeniya", "country_code": "LK"}],
        }
    )
    foreign = openalex_author(
        {
            "author": {"display_name": "Jane Doe"},
            "institutions": [{"display_name": "University of Oxford", "country_code": "gb"}],
        }
    )

    assert author["name"] == "Roshan Ragel"
    assert (author["institution"], author["country_code"]) == ("University of Peradeniya", "LK")
    assert (foreign["institution"], foreign["country_code"]) == ("University of Oxford", "GB")


# -------------------------------------------------------------- categories


def test_category_must_come_from_the_taxonomy() -> None:
    assert authors.validate_category("Computer Science", "Artificial Intelligence") == {
        "primary_field": "Computer Science",
        "primary_subfield": "Artificial Intelligence",
    }
    assert authors.validate_category("", "") == {"primary_field": "", "primary_subfield": ""}
    with pytest.raises(APIError, match="field from the list"):
        authors.validate_category("Alchemy", "")
    with pytest.raises(APIError, match="not part of the chosen field"):
        authors.validate_category("Computer Science", "Plant Science")
    with pytest.raises(APIError, match="field first"):
        authors.validate_category("", "Artificial Intelligence")


def test_category_resolution_order() -> None:
    contribution = {
        "proposed": {"primary_field": "", "primary_subfield": ""},
        "lookup_evidence": {
            "category": {"primary_field": "Engineering", "primary_subfield": "Control and Systems Engineering", "primary_domain": "Physical Sciences"}
        },
        "classifier": {"category": {"field": "Computer Science", "subfield": "Artificial Intelligence"}},
    }
    domains = {"Computer Science": "Physical Sciences", "Medicine": "Health Sciences"}

    assert authors.resolve_category(contribution, None, domains)["source"] == "openalex"
    assert authors.resolve_category(contribution, {"primary_field": "Medicine"}, domains) == {
        "primary_field": "Medicine",
        "primary_subfield": None,
        "primary_domain": "Health Sciences",
        "source": "administrator",
    }
    contribution["lookup_evidence"] = {}
    assert authors.resolve_category(contribution, None, domains)["primary_field"] == "Computer Science"
    contribution["proposed"] = {"primary_field": "Medicine", "primary_subfield": "Radiology, Nuclear Medicine and Imaging"}
    assert authors.resolve_category(contribution, None, domains)["source"] == "author"


def test_submission_record_files_under_the_resolved_category() -> None:
    contribution = {
        "contribution_id": UUID(int=1),
        "proposed": authors.validate_new_publication(
            {
                "doi": "10.1234/x",
                "title": "A study of something about artificial intelligence",
                "abstract": "An abstract long enough to pass the minimum length for the check here.",
                "publication_year": 2024,
                "authors": [row("A One", is_submitter=True)],
            }
        ),
        "lookup_evidence": {"category": {"topics": "Machine learning", "primary_topic": "Deep Learning"}},
        "classifier": {},
    }
    record = authors.submission_record(
        contribution,
        {"email": "admin@example.com"},
        {"primary_field": "Computer Science", "primary_subfield": "Artificial Intelligence", "primary_domain": "Physical Sciences"},
    )

    assert (record["primary_field"], record["primary_subfield"], record["primary_domain"]) == (
        "Computer Science",
        "Artificial Intelligence",
        "Physical Sciences",
    )
    assert record["topics"] == "Machine learning"
    assert record["institutions"] == "University of Moratuwa"


# ------------------------------------------------------ institution history


def test_affiliation_history_is_validated_and_current_first() -> None:
    history = authors.validate_affiliations(
        [
            {"institution": "UOM", "start_year": 2012, "end_year": 2020},
            {"institution": "University of Peradeniya", "start_year": "2021"},
        ]
    )

    assert [(item["institution"], item["start_year"], item["end_year"]) for item in history] == [
        ("University of Peradeniya", 2021, None),
        ("University of Moratuwa", 2012, 2020),
    ]
    with pytest.raises(APIError, match="end before they start"):
        authors.validate_affiliations([{"institution": "UOM", "start_year": 2020, "end_year": 2012}])
    with pytest.raises(APIError) as error:
        authors.validate_affiliations([{"institution": "UOM"}, {"institution": ""}])
    assert error.value.details == {"field": "affiliations", "index": 1}


HISTORY = [
    {"institution": "University of Peradeniya", "start_year": 2021, "end_year": None},
    {"institution": "University of Moratuwa", "start_year": 2012, "end_year": 2020},
]


def test_a_paper_is_attributed_to_the_institution_of_its_year() -> None:
    # Co-authors from both universities on one paper: the year decides.
    both = ["University of Moratuwa", "University of Peradeniya"]
    assert institution_at_time(both, 2018, HISTORY) == "University of Moratuwa"
    assert institution_at_time(both, 2023, HISTORY) == "University of Peradeniya"
    # Outside every period, any institution from the history still counts.
    assert institution_at_time(["Univ. of Moratuwa"], 2005, HISTORY) == "Univ. of Moratuwa"
    assert institution_at_time(["University of Oxford"], 2018, HISTORY) is None


def test_moving_institution_keeps_earlier_work_with_the_earlier_institution() -> None:
    papers = [
        {"institutions": "University of Moratuwa; University of Oxford", "publication_year": 2016},
        {"institutions": "University of Moratuwa", "publication_year": 2019},
        {"institutions": "University of Peradeniya", "publication_year": 2022},
        {"institutions": "University of Peradeniya", "publication_year": 2025, "author_institution": "University of Peradeniya"},
        {"institutions": "Unknown Institute", "publication_year": 2024},
    ]

    breakdown = institution_breakdown(papers, HISTORY)

    assert breakdown == {
        "institutions": [
            {"institution": "University of Peradeniya", "publication_count": 2, "year_min": 2022, "year_max": 2025},
            {"institution": "University of Moratuwa", "publication_count": 2, "year_min": 2016, "year_max": 2019},
        ],
        "unattributed": 1,
    }


def test_canonical_institution_knows_registry_aliases() -> None:
    assert canonical_institution("Univ. of Moratuwa") == {
        "label": "University of Moratuwa",
        "country_code": "LK",
        "registered": True,
    }
    assert canonical_institution("Nowhere College")["registered"] is False
