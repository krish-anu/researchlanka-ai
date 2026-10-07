"""Tests for department tagging from raw affiliation strings."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline.build_department_tags import (
    DEPARTMENT,
    INSTITUTION_ONLY,
    OTHER_UNIT,
    affiliation_segments,
    build_department_tags,
    classify_authorship,
    classify_segment,
    load_departments,
    tag_department,
)


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configurations" / "sri_lanka" / "departments.json"


@pytest.fixture(scope="module")
def cse():
    (spec,) = load_departments(CONFIG_PATH, ["uom-cse"])
    return spec


def test_affiliation_segments_decode_entities_before_splitting():
    raw = "Department of Computer Science &amp; Engineering, University of Moratuwa; Dept &#x0026 X"
    assert affiliation_segments(raw) == [
        "Department of Computer Science & Engineering, University of Moratuwa",
        "Dept & X",
    ]
    assert affiliation_segments(None) == []
    assert affiliation_segments("nan") == []


@pytest.mark.parametrize(
    "segment",
    [
        "Department of Computer Science and Engineering, University of Moratuwa, Sri Lanka",
        "Dept. of Computer Science & Engineering , University of Moratuwa , Sri Lanka.",
        "Department of Computer Science & Eng., University of Moratuwa",
        "Computer Science And Engineeringuniversity Of Moratuwamoratuwasri Lanka",
        "University of Moratuwa,Dept.of CSE,Katubadda,Sri Lanka",
    ],
)
def test_classify_segment_recognises_department_variants(cse, segment):
    assert classify_segment(segment, cse, at_institution=False) == DEPARTMENT


def test_classify_segment_requires_the_target_institution(cse):
    peradeniya = "Department of Computer Science and Engineering, University of Peradeniya"
    assert classify_segment(peradeniya, cse, at_institution=False) is None
    # OpenAlex placing the authorship at Moratuwa does not override another university.
    assert classify_segment(peradeniya, cse, at_institution=True) is None
    # A bare department string is trusted when OpenAlex matched the institution.
    bare = "Department of Computer Science & Engineering"
    assert classify_segment(bare, cse, at_institution=True) == DEPARTMENT
    assert classify_segment(bare, cse, at_institution=False) is None


def test_classify_segment_separates_other_units_from_the_parent_faculty(cse):
    assert (
        classify_segment("Department of Electrical Engineering, University of Moratuwa", cse, at_institution=False)
        == OTHER_UNIT
    )
    assert (
        classify_segment("Faculty of Information Technology, University of Moratuwa", cse, at_institution=False)
        == OTHER_UNIT
    )
    assert (
        classify_segment("Faculty of Engineering, University of Moratuwa", cse, at_institution=False)
        == INSTITUTION_ONLY
    )
    assert classify_segment("University of Moratuwa, Moratuwa, LK", cse, at_institution=False) == INSTITUTION_ONLY


def test_classify_authorship_prefers_the_department_over_other_units(cse):
    raw = (
        "Department of Electrical Engineering, University of Moratuwa; "
        "Department of Computer Science and Engineering, University of Moratuwa"
    )
    label, evidence = classify_authorship(raw, cse, at_institution=False)
    assert label == DEPARTMENT
    assert evidence == "Department of Computer Science and Engineering, University of Moratuwa"
    # Matched to the institution by OpenAlex, but no string is about it.
    assert classify_authorship("University of Colombo", cse, at_institution=True) == (INSTITUTION_ONLY, None)
    assert classify_authorship("University of Colombo", cse, at_institution=False) == (None, None)


CSE_AFFILIATION = "Department of Computer Science and Engineering, University of Moratuwa, Sri Lanka"
EE_AFFILIATION = "Department of Electrical Engineering, University of Moratuwa, Sri Lanka"
UOM_ONLY = "University of Moratuwa, Moratuwa, Sri Lanka"


def openalex_row(work, author_id, name, raw, institution="University of Moratuwa"):
    return {
        "openalex_work_id": f"https://openalex.org/{work}",
        "openalex_author_id": author_id,
        "author_name": name,
        "raw_affiliation_strings": raw,
        "institution_name": institution,
    }


@pytest.fixture
def corpus():
    openalex = pd.DataFrame(
        [
            # W1: explicit CSE author.
            openalex_row("W1", "A1", "Nadeesha Perera", CSE_AFFILIATION),
            # W2, W3: history for A2 (two CSE works) and A3 (mostly EE).
            openalex_row("W2", "A2", "Kasun Silva", CSE_AFFILIATION),
            openalex_row("W3", "A2", "Kasun Silva", CSE_AFFILIATION),
            openalex_row("W2", "A3", "Ruwan Fernando", CSE_AFFILIATION),
            openalex_row("W3", "A3", "Ruwan Fernando", EE_AFFILIATION),
            openalex_row("W5", "A3", "Ruwan Fernando", EE_AFFILIATION),
            # W4: both list only the university -- A2 is inferred, A3 is not.
            openalex_row("W4", "A2", "Kasun Silva", UOM_ONLY),
            openalex_row("W4", "A3", "Ruwan Fernando", UOM_ONLY),
            # W6: an EE-only paper at Moratuwa.
            openalex_row("W6", "A4", "Isuri Jayasena", EE_AFFILIATION),
            # W7: no Moratuwa authors at all.
            openalex_row("W7", "A5", "Someone Else", "University of Colombo", institution="University of Colombo"),
        ]
    )
    crossref = pd.DataFrame(
        [
            # W8 has no OpenAlex authorship rows; Crossref names the department.
            {
                "doi": "https://doi.org/10.1000/W8",
                "author_name": "Perera, N.",
                "raw_affiliation_strings": "Dept. of Computer Science &amp; Engineering, University of Moratuwa",
            },
        ]
    )
    final = pd.DataFrame(
        [
            {"openalex_id": f"https://openalex.org/{work}", "doi": f"10.1000/{work}", "title": f"Paper {work}",
             "publication_date": "2024-05-01", "source_dataset": "openalex", "source_record_id": work,
             "sri_lankan_institutions": "University of Moratuwa" if work != "W7" else "University of Colombo"}
            for work in ["W1", "W4", "W6", "W7", "W8"]
        ]
    )
    return final, openalex, crossref


def test_tag_department_marks_explicit_and_inferred_publications(cse, corpus):
    final, openalex, crossref = corpus
    rows, summary = tag_department(final, openalex, crossref, cse)
    by_key = {}
    for row in rows:
        by_key.setdefault(row["publication_key"], []).append(row)

    assert set(by_key) == {"doi:10.1000/w1", "doi:10.1000/w4", "doi:10.1000/w8"}

    (w1,) = by_key["doi:10.1000/w1"]
    assert (w1["publication_match"], w1["author_id"], w1["author_match"]) == ("explicit", "A1", "explicit")
    assert w1["evidence"] == CSE_AFFILIATION
    # The final dataset carries only publication_date; the year is derived from it.
    assert w1["publication_year"] == 2024

    (w4,) = by_key["doi:10.1000/w4"]
    assert (w4["publication_match"], w4["author_id"], w4["author_match"]) == ("inferred", "A2", "inferred")
    assert w4["author_department_works"] == 2
    assert "named CSE on 2 other works" in w4["evidence"]

    (w8,) = by_key["doi:10.1000/w8"]
    assert (w8["author_name"], w8["author_id"], w8["publication_match"]) == ("Perera, N.", None, "explicit")

    counts = summary["counts"]
    assert counts["institution_publications"] == 4
    assert counts["department_publications"] == 3
    assert counts["explicit_publications"] == 2
    assert counts["inferred_publications"] == 1
    assert counts["other_unit_publications"] == 1
    assert counts["department_authors"] == 3


def test_tag_department_respects_history_thresholds(cse, corpus):
    final, openalex, crossref = corpus
    rows, summary = tag_department(final, openalex, crossref, cse, min_history=3)
    assert "doi:10.1000/w4" not in {row["publication_key"] for row in rows}
    assert summary["counts"]["inferred_publications"] == 0
    assert summary["counts"]["institution_only_publications"] == 1


def test_build_department_tags_writes_sidecar_files(cse, corpus, tmp_path):
    final, openalex, crossref = corpus
    final_csv = tmp_path / "final.csv"
    openalex_csv = tmp_path / "openalex.csv"
    crossref_csv = tmp_path / "crossref.csv"
    final.to_csv(final_csv, index=False)
    openalex.to_csv(openalex_csv, index=False)
    crossref.to_csv(crossref_csv, index=False)

    payload = build_department_tags(
        input_csv=final_csv,
        openalex_authorships_csv=openalex_csv,
        crossref_authorships_csv=crossref_csv,
        config_json=CONFIG_PATH,
        output_dir=tmp_path / "departments",
    )

    written = pd.read_csv(tmp_path / "departments" / "department_publication_authors.csv")
    assert written["publication_key"].nunique() == 3
    summary = json.loads((tmp_path / "departments" / "department_tagging_summary.json").read_text())
    assert summary["departments"][0]["department_id"] == "uom-cse"
    assert payload["departments"][0]["counts"]["department_publications"] == 3


def test_load_departments_rejects_unknown_ids():
    with pytest.raises(ValueError, match="nope"):
        load_departments(CONFIG_PATH, ["nope"])
