"""End-to-end author profile workflow against a real PostgreSQL database.

Opt-in: set RESEARCHLANKA_TEST_DATABASE_URL to a disposable database, e.g.

    docker run --rm -d -p 55433:5432 -e POSTGRES_USER=rltest \
        -e POSTGRES_PASSWORD=rltest -e POSTGRES_DB=rltest postgres:16
    RESEARCHLANKA_TEST_DATABASE_URL=postgresql://rltest:rltest@localhost:55433/rltest pytest tests/test_author_profiles_postgres.py

Each run applies every migration inside its own schema and drops it after.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from src.api.core.errors import APIError
from src.api.services import author_profiles as authors
from src.database.load_records import retire_stale_publications
from src.database.loader import ensure_database_schema, load_final_publications


DATABASE_URL = os.getenv("RESEARCHLANKA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set RESEARCHLANKA_TEST_DATABASE_URL to run PostgreSQL integration tests.",
)

AUTHOR = {"id": "usr_author", "email": "chinthaka@uom.lk", "name": "Chinthaka Jayatilake"}
OTHER = {"id": "usr_other", "email": "someone@gmail.com", "name": "Someone"}
ADMIN = {"id": "usr_admin", "email": "admin@example.com", "name": "Admin"}


def publication(key_suffix: str, **overrides):
    record = {
        "source_dataset": "openalex",
        "source_record_id": f"W{key_suffix}",
        "doi": f"10.1000/{key_suffix}",
        "title": f"Original title {key_suffix} on machine learning for Sinhala",
        "abstract": "An abstract about machine learning.",
        "publication_date": "2023-05-01",
        "type": "article",
        "authors": "Chinthaka Jayatilake; Gamage Upeksha Ganegoda",
        "author_orcids": "https://orcid.org/0000-0002-1825-0097",
        "institutions": "University of Moratuwa",
        "countries": "LK",
        "ownership_decision": "INCLUDE",
        "ownership_confidence": "HIGH",
        "needs_manual_review": "false",
        "ai_classification_label": "AI",
        "ai_classification_confidence": "0.97",
    }
    record.update(overrides)
    return record


@pytest.fixture
def connection():
    psycopg = pytest.importorskip("psycopg")
    connection = psycopg.connect(DATABASE_URL)
    schema = f"author_test_{uuid4().hex[:10]}"
    connection.execute(f'CREATE SCHEMA "{schema}"')
    # public stays on the path so extensions installed there (pg_trgm) resolve.
    connection.execute(f'SET search_path TO "{schema}", public')
    connection.commit()
    try:
        ensure_database_schema(connection)
        load_final_publications(
            [
                publication("a"),
                publication("b", authors="Jayatilake, C; Roshan Ragel"),
                publication("c", doi=None, source_record_id="W5", openalex_id="W5"),
            ],
            connection=connection,
            ensure_schema=False,
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        connection.commit()
        connection.close()


def fetch(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def apply(connection):
    connection.execute("SELECT refresh_public_publication_views()")


def approved_author(connection) -> dict:
    authors.submit_application(
        connection,
        AUTHOR,
        {
            "display_name": "Chinthaka Jayatilake",
            "name_variants": ["Jayatilake, C"],
            "orcid": "0000-0002-1825-0097",
            "institution": "University of Moratuwa",
            "claims": [
                {"publication_key": "doi:10.1000/a", "name_as_listed": "Chinthaka Jayatilake"},
                {"publication_key": "doi:10.1000/b", "name_as_listed": "jayatilake, c"},
                {"publication_key": "openalex:W5", "name_as_listed": "Chinthaka Jayatilake"},
            ],
        },
    )
    profile = authors.list_applications(connection)["records"][0]
    authors.decide_application(
        connection,
        ADMIN,
        {"profile_id": profile["profile_id"], "decision": "approve", "record_version": profile["record_version"]},
    )
    connection.commit()
    return profile


def test_application_review_cycle_and_evidence(connection) -> None:
    with pytest.raises(APIError) as error:
        authors.submit_application(
            connection,
            AUTHOR,
            {
                "display_name": "Chinthaka Jayatilake",
                "institution": "University of Moratuwa",
                "claims": [{"publication_key": "doi:10.1000/a", "name_as_listed": "Roshan Ragel"}],
            },
        )
    assert error.value.code == "author_not_listed"
    connection.rollback()

    workspace = authors.submit_application(
        connection,
        AUTHOR,
        {
            "display_name": "Chinthaka Jayatilake",
            "orcid": "0000-0002-1825-0097",
            "institution": "University of Moratuwa",
            "claims": [
                {"publication_key": "doi:10.1000/a", "name_as_listed": "chinthaka jayatilake"},
                {"publication_key": "doi:10.1000/b", "name_as_listed": "Jayatilake, C"},
            ],
        },
    )
    connection.commit()
    assert workspace["profile"]["status"] == "pending"
    # The stored name is the publication's spelling, not the applicant's typing.
    assert {claim["name_as_listed"] for claim in workspace["claims"]} == {"Chinthaka Jayatilake", "Jayatilake, C"}

    queue = authors.list_applications(connection)
    record = queue["records"][0]
    evidence = {claim["publication_key"]: claim["evidence"] for claim in record["claims"]}
    assert record["evidence"]["email"]["kind"] == "sri_lankan_organisation"
    assert evidence["doi:10.1000/a"]["name_match"] == "exact"
    assert evidence["doi:10.1000/b"]["name_match"] == "initials"
    assert evidence["doi:10.1000/a"]["orcid_match"] is True

    with pytest.raises(APIError) as error:
        authors.decide_application(connection, ADMIN, {"profile_id": record["profile_id"], "decision": "reject"})
    assert error.value.code == "reason_required"

    returned = authors.decide_application(
        connection,
        ADMIN,
        {"profile_id": record["profile_id"], "decision": "request_changes", "reason": "Add your department."},
    )
    connection.commit()
    assert returned["status"] == "changes_requested"

    with pytest.raises(APIError) as error:
        authors.decide_application(
            connection,
            ADMIN,
            {"profile_id": record["profile_id"], "decision": "approve"},
        )
    assert error.value.code == "already_decided"
    connection.rollback()

    authors.submit_application(
        connection,
        AUTHOR,
        {
            "display_name": "Chinthaka Jayatilake",
            "institution": "University of Moratuwa",
            "department": "CSE",
            "claims": [
                {"publication_key": "doi:10.1000/a", "name_as_listed": "Chinthaka Jayatilake"},
                {"publication_key": "doi:10.1000/b", "name_as_listed": "Jayatilake, C"},
            ],
        },
    )
    connection.commit()
    record = authors.list_applications(connection)["records"][0]
    with pytest.raises(APIError) as error:
        authors.decide_application(
            connection,
            ADMIN,
            {"profile_id": record["profile_id"], "decision": "approve", "record_version": 1},
        )
    assert error.value.code == "stale_application"
    connection.rollback()

    claim_b = next(claim for claim in record["claims"] if claim["publication_key"] == "doi:10.1000/b")
    approved = authors.decide_application(
        connection,
        ADMIN,
        {
            "profile_id": record["profile_id"],
            "decision": "approve",
            "record_version": record["record_version"],
            "claim_decisions": {claim_b["claim_id"]: "rejected"},
        },
    )
    assert approved["status"] == "approved"
    assert approved["already_decided"] is False
    again = authors.decide_application(connection, ADMIN, {"profile_id": record["profile_id"], "decision": "approve"})
    assert again["already_decided"] is True

    statuses = dict(fetch(connection, "SELECT publication_key, status FROM author_publication_claims"))
    assert statuses == {"doi:10.1000/a": "approved", "doi:10.1000/b": "rejected"}

    with pytest.raises(APIError) as error:
        authors.submit_application(
            connection, AUTHOR, {"display_name": "Chinthaka Jayatilake", "institution": "UoM"}
        )
    assert error.value.code == "application_closed"


def test_public_profile_shows_live_bio_and_only_approved_claims(connection) -> None:
    approved_author(connection)

    authors.update_profile(
        connection,
        AUTHOR,
        {"bio": "Works on Sinhala NLP.", "links": {"google_scholar_url": "https://scholar.google.com/x"}},
    )
    profile = authors.public_profile(connection, "chinthaka-jayatilake")
    assert profile["bio"] == "Works on Sinhala NLP."
    assert profile["links"]["google_scholar_url"] == "https://scholar.google.com/x"
    assert profile["stats"]["publication_count"] == 3
    assert "user_email" not in profile

    page = authors.public_profile_publications(connection, "chinthaka-jayatilake", page=1, page_size=2)
    assert page["pagination"]["total"] == 3
    assert len(page["data"]) == 2

    matches = authors.list_public_profiles(connection, name="C Jayatilake")
    assert [match["slug"] for match in matches] == ["chinthaka-jayatilake"]
    assert authors.list_public_profiles(connection, name="Roshan Ragel") == []

    with pytest.raises(APIError) as error:
        authors.public_profile(connection, "nobody")
    assert error.value.status == 404

    with pytest.raises(APIError) as error:
        authors.update_profile(connection, OTHER, {"bio": "Not mine"})
    assert error.value.code == "author_profile_required"


def test_claims_follow_the_record_when_the_loader_canonicalises_its_key(connection) -> None:
    approved_author(connection)

    load_final_publications(
        [publication("c", doi="10.1000/c", source_record_id="W5", openalex_id="W5")],
        connection=connection,
        ensure_schema=False,
    )

    keys = [row[0] for row in fetch(connection, "SELECT publication_key FROM author_publication_claims ORDER BY 1")]
    assert "doi:10.1000/c" in keys
    assert "openalex:W5" not in keys


def test_approved_edit_survives_a_pipeline_reload(connection) -> None:
    approved_author(connection)

    with pytest.raises(APIError) as error:
        authors.propose_edit(connection, OTHER, {"publication_key": "doi:10.1000/a", "changes": {"title": "Mine now"}})
    assert error.value.status == 403
    connection.rollback()

    editable = authors.get_editable_publication(connection, AUTHOR, "doi:10.1000/a")
    assert editable["values"]["publication_year"] == 2023
    assert editable["name_as_listed"] == "Chinthaka Jayatilake"
    assert editable["pending_edit"] is None
    with pytest.raises(APIError) as error:
        authors.get_editable_publication(connection, OTHER, "doi:10.1000/a")
    assert error.value.status == 403
    connection.rollback()

    edit = authors.propose_edit(
        connection,
        AUTHOR,
        {
            "publication_key": "doi:10.1000/a",
            "changes": {"title": "Corrected title for the Sinhala paper", "publication_year": 2022},
            "note": "Typo in the title; published 2022.",
        },
    )
    connection.commit()
    assert edit["base_snapshot"]["publication_year"] == 2023

    with pytest.raises(APIError) as error:
        authors.propose_edit(
            connection, AUTHOR, {"publication_key": "doi:10.1000/a", "changes": {"volume": "7"}}
        )
    assert error.value.code == "edit_already_pending"
    connection.rollback()

    queue = authors.list_contributions(connection)["records"]
    assert queue[0]["current"]["title"] == "Original title a on machine learning for Sinhala"
    assert queue[0]["stale_fields"] == []

    authors.decide_contribution(
        connection,
        ADMIN,
        {"contribution_id": edit["contribution_id"], "decision": "approve", "record_version": edit["record_version"]},
    )

    def public_row():
        return fetch(
            connection,
            "SELECT title, publication_year, has_author_corrections FROM public_eligible_publications WHERE publication_key = %s",
            ("doi:10.1000/a",),
        )[0]

    assert public_row() == ("Corrected title for the Sinhala paper", 2022, True)

    # A monthly reload rewrites every pipeline column...
    load_final_publications([publication("a")], connection=connection, ensure_schema=False)
    assert fetch(connection, "SELECT title FROM final_publications WHERE publication_key = 'doi:10.1000/a'")[0][0] == (
        "Original title a on machine learning for Sinhala"
    )
    # ...and the correction still shows, including after the views are rebuilt.
    assert public_row()[0] == "Corrected title for the Sinhala paper"
    apply(connection)
    assert public_row()[0] == "Corrected title for the Sinhala paper"

    withdrawn = authors.propose_edit(
        connection, AUTHOR, {"publication_key": "doi:10.1000/a", "changes": {"volume": "7"}}
    )
    assert authors.withdraw_contribution(connection, AUTHOR, {"contribution_id": withdrawn["contribution_id"]})[
        "status"
    ] == "withdrawn"


def fake_lookup(doi):
    return {
        "source": "openalex",
        "doi": doi,
        "openalex_id": "W999",
        "fields": {"title": "From OpenAlex", "authors": [{"name": "Chinthaka Jayatilake"}]},
        "ownership": {"ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
        "countries": "LK",
        "institutions": "University of Moratuwa",
        "sri_lankan_institutions": "University of Moratuwa",
    }


def fake_category(record):
    return {"field": "Computer Science", "subfield": "Artificial Intelligence", "available": True, "reason": None}


def submission(**overrides):
    payload = {
        "doi": "10.1000/new",
        "title": "Graph neural networks for Sri Lankan traffic forecasting",
        "abstract": "We forecast traffic in Colombo using graph neural networks trained on sensor data.",
        "publication_year": 2025,
        "type": "article",
        "journal": "Journal of Urban AI",
        "authors": [
            {"name": "Chinthaka Jayatilake", "institution": "University of Moratuwa", "is_submitter": True},
            {"name": "Roshan Ragel", "institution": "University of Peradeniya"},
        ],
    }
    payload.update(overrides)
    return payload


def test_new_publication_is_checked_reviewed_and_protected_from_retirement(connection) -> None:
    approved_author(connection)
    ai_model = lambda record: {"label": "AI", "confidence": "0.91", "model": "test.joblib", "reason": None, "available": True}

    with pytest.raises(APIError) as error:
        authors.submit_new_publication(
            connection, AUTHOR, submission(doi="10.1000/a"), classifier=ai_model, lookup=fake_lookup, categorizer=fake_category
        )
    assert error.value.code == "duplicate_publication"
    assert error.value.details["matches"][0]["is_public"] is True
    connection.rollback()

    contribution = authors.submit_new_publication(
        connection, AUTHOR, submission(), classifier=ai_model, lookup=fake_lookup, categorizer=fake_category
    )
    connection.commit()
    assert contribution["classifier"]["label"] == "AI"
    assert contribution["lookup_source"] == "openalex"
    assert contribution["lookup_evidence"]["openalex_id"] == "W999"

    with pytest.raises(APIError) as error:
        authors.submit_new_publication(connection, AUTHOR, submission(), classifier=ai_model, lookup=fake_lookup, categorizer=fake_category)
    assert error.value.code == "submission_already_pending"
    connection.rollback()

    queue = authors.list_contributions(connection, contribution_type="new_publication")["records"]
    assert queue[0]["duplicates"] == []
    assert queue[0]["name_match"] == "exact"

    for missing in ({}, {"ai_decision": "AI"}):
        with pytest.raises(APIError):
            authors.decide_contribution(
                connection,
                ADMIN,
                {"contribution_id": contribution["contribution_id"], "decision": "approve", **missing},
            )
        connection.rollback()

    authors.decide_contribution(
        connection,
        ADMIN,
        {
            "contribution_id": contribution["contribution_id"],
            "decision": "approve",
            "ai_decision": "AI",
            "ownership_verified": True,
        },
    )

    row = fetch(
        connection,
        """
        SELECT v.title, v.publication_year, v.source_dataset, v.review_status, v.openalex_id, v.institutions
        FROM public_eligible_publications v WHERE v.publication_key = 'doi:10.1000/new'
        """,
    )
    assert row == [
        (
            "Graph neural networks for Sri Lankan traffic forecasting",
            2025,
            "author_submission",
            "human_accepted",
            "W999",
            "University of Moratuwa; University of Peradeniya",
        )
    ]
    events = fetch(connection, "SELECT event_type FROM ai_review_events WHERE publication_key = 'doi:10.1000/new'")
    assert ("author_submission_accepted",) in events
    claims = fetch(
        connection,
        "SELECT name_as_listed, author_position, status FROM author_publication_claims WHERE publication_key = 'doi:10.1000/new'",
    )
    assert claims == [("Chinthaka Jayatilake", 1, "approved")]
    assert authors.public_profile(connection, "chinthaka-jayatilake")["stats"]["publication_count"] == 4

    retired = retire_stale_publications(
        connection,
        active_publication_keys={"doi:10.1000/a", "doi:10.1000/b", "openalex:W5"},
    )
    assert retired == 0
    assert fetch(connection, "SELECT retired_at FROM final_publications WHERE publication_key = 'doi:10.1000/new'") == [(None,)]

    # The pipeline later harvests the same DOI: the record is refreshed in
    # place and keeps its human AI decision and the author's claim.
    load_final_publications([publication("new")], connection=connection, ensure_schema=False)
    assert fetch(
        connection,
        "SELECT review_status FROM ai_review_records WHERE publication_key = 'doi:10.1000/new'",
    ) == [("human_accepted",)]
    assert fetch(connection, "SELECT count(*) FROM author_publication_claims WHERE publication_key = 'doi:10.1000/new'") == [(1,)]


def test_model_disagreement_needs_a_written_reason_and_rejection_needs_one_too(connection) -> None:
    approved_author(connection)
    non_ai = lambda record: {"label": "non-AI", "confidence": "0.12", "model": "test.joblib", "reason": None, "available": True}
    contribution = authors.submit_new_publication(
        connection, AUTHOR, submission(doi="", url="https://repo.example.lk/123"), classifier=non_ai, lookup=fake_lookup, categorizer=fake_category
    )
    connection.commit()
    assert contribution["lookup_source"] == "manual"

    decision = {
        "contribution_id": contribution["contribution_id"],
        "decision": "approve",
        "ai_decision": "AI",
        "ownership_verified": True,
    }
    with pytest.raises(APIError) as error:
        authors.decide_contribution(connection, ADMIN, decision)
    assert error.value.code == "reason_required"
    connection.rollback()

    with pytest.raises(APIError) as error:
        authors.decide_contribution(
            connection, ADMIN, {"contribution_id": contribution["contribution_id"], "decision": "reject"}
        )
    assert error.value.code == "reason_required"
    connection.rollback()

    rejected = authors.decide_contribution(
        connection,
        ADMIN,
        {"contribution_id": contribution["contribution_id"], "decision": "reject", "reason": "Not AI research."},
    )
    assert rejected["status"] == "rejected"
    assert fetch(connection, "SELECT count(*) FROM final_publications WHERE source_dataset = 'author_submission'") == [(0,)]


def test_additional_claims_go_through_the_claim_queue(connection) -> None:
    approved_author(connection)
    load_final_publications(
        [publication("d", authors="Roshan Ragel; C. Jayatilake")], connection=connection, ensure_schema=False
    )
    workspace = authors.request_claims(
        connection, AUTHOR, {"claims": [{"publication_key": "doi:10.1000/d", "name_as_listed": "C. Jayatilake"}]}
    )
    assert workspace["claims_added"] == 1

    queue = authors.list_claim_requests(connection)["records"]
    assert [claim["publication_key"] for claim in queue] == ["doi:10.1000/d"]
    assert queue[0]["profile"]["display_name"] == "Chinthaka Jayatilake"
    assert authors.admin_summary(connection) == {"applications": 0, "claims": 1, "contributions": 0}

    authors.decide_claims(connection, ADMIN, {"claim_decisions": {queue[0]["claim_id"]: "approved"}})
    assert authors.public_profile(connection, "chinthaka-jayatilake")["stats"]["publication_count"] == 4


SECOND = {"id": "usr_second", "email": "roshan@eng.pdn.ac.lk", "name": "Roshan Ragel"}


def approve_second_author(connection) -> None:
    authors.submit_application(
        connection,
        SECOND,
        {
            "display_name": "Roshan Ragel",
            "institution": "University of Peradeniya",
            "claims": [{"publication_key": "doi:10.1000/b", "name_as_listed": "Roshan Ragel"}],
        },
    )
    profile = next(
        record for record in authors.list_applications(connection)["records"] if record["display_name"] == "Roshan Ragel"
    )
    authors.decide_application(connection, ADMIN, {"profile_id": profile["profile_id"], "decision": "approve"})
    connection.commit()


def test_lookups_find_names_institutions_and_who_claimed_a_name(connection) -> None:
    from src.api.services import author_reference as reference

    before = reference.lookup_author_names(connection, "jayatil")
    assert {row["name"] for row in before["names"]} == {"Chinthaka Jayatilake", "Jayatilake, C"}
    assert all(row["profile"] is None for row in before["names"])

    approved_author(connection)
    after = {row["name"]: row for row in reference.lookup_author_names(connection, "jayatil")["names"]}
    # Both printed spellings now point at the one verified profile.
    assert after["Chinthaka Jayatilake"]["profile"]["slug"] == "chinthaka-jayatilake"
    assert after["Jayatilake, C"]["profile"]["slug"] == "chinthaka-jayatilake"
    assert authors.profiles_by_names(connection, ["Jayatilake, C", "Gamage Upeksha Ganegoda"]) == {
        "Jayatilake, C": {
            "slug": "chinthaka-jayatilake",
            "display_name": "Chinthaka Jayatilake",
            "institution": "University of Moratuwa",
            "claimed_count": 1,
        }
    }
    matches = authors.list_public_profiles(connection, name="Jayatilake, C")
    assert [(match["slug"], match["match"], match["claimed_count"]) for match in matches] == [
        ("chinthaka-jayatilake", "claimed", 1)
    ]

    institutions = {row["label"]: row for row in reference.lookup_institutions(connection, "moratuwa")}
    assert institutions["University of Moratuwa"]["sri_lankan"] is True
    assert institutions["University of Moratuwa"]["publication_count"] == 3
    assert reference.lookup_institutions(connection, "m") == []


def test_coauthors_are_linked_and_each_institution_is_counted(connection) -> None:
    approved_author(connection)
    approve_second_author(connection)

    def ai_model(record):
        return {"label": "AI", "confidence": "0.95", "model": "test.joblib", "reason": None, "available": True}

    with pytest.raises(APIError) as error:
        authors.submit_new_publication(
            connection,
            AUTHOR,
            submission(
                authors=[
                    {"name": "Chinthaka Jayatilake", "institution": "UOM", "is_submitter": True},
                    {"name": "Roshan Ragel", "institution": "University of Peradeniya", "profile_slug": "nobody"},
                ]
            ),
            classifier=ai_model,
            lookup=fake_lookup,
            categorizer=fake_category,
        )
    assert error.value.code == "profile_not_found"
    assert error.value.details["index"] == 1
    connection.rollback()

    contribution = authors.submit_new_publication(
        connection,
        AUTHOR,
        submission(
            doi="10.1000/coauthored",
            title="Federated learning for clinical text in Sinhala and Tamil hospitals",
            authors=[
                {"name": "Chinthaka Jayatilake", "institution": "UOM", "is_submitter": True},
                {"name": "Roshan Ragel", "institution": "University of Peradeniya", "profile_slug": "roshan-ragel"},
                {"name": "Jane Doe", "institution": "University of Oxford", "country_code": "GB"},
            ],
            primary_field="Computer Science",
            primary_subfield="Artificial Intelligence",
        ),
        classifier=ai_model,
        lookup=fake_lookup,
        categorizer=fake_category,
    )
    connection.commit()
    rows = contribution["proposed"]["authors"]
    assert [(row["profile_slug"], row["institution"], row["country_code"]) for row in rows] == [
        ("chinthaka-jayatilake", "University of Moratuwa", "LK"),
        ("roshan-ragel", "University of Peradeniya", "LK"),
        (None, "University of Oxford", "GB"),
    ]
    assert contribution["classifier"]["category"]["field"] == "Computer Science"

    authors.decide_contribution(
        connection,
        ADMIN,
        {
            "contribution_id": contribution["contribution_id"],
            "decision": "approve",
            "ai_decision": "AI",
            "ownership_verified": True,
        },
    )
    connection.commit()

    assert fetch(
        connection,
        "SELECT institutions, sri_lankan_institutions, countries, sri_lankan_authors, primary_field, primary_subfield "
        "FROM public_eligible_publications WHERE publication_key = %s",
        ("doi:10.1000/coauthored",),
    ) == [
        (
            "University of Moratuwa; University of Peradeniya; University of Oxford",
            "University of Moratuwa; University of Peradeniya",
            "LK; GB",
            "Chinthaka Jayatilake; Roshan Ragel",
            "Computer Science",
            "Artificial Intelligence",
        )
    ]
    claims = fetch(
        connection,
        "SELECT p.slug, c.name_as_listed, c.institution, c.status "
        "FROM author_publication_claims c JOIN author_profiles p USING (profile_id) "
        "WHERE c.publication_key = %s ORDER BY c.author_position",
        ("doi:10.1000/coauthored",),
    )
    assert claims == [
        ("chinthaka-jayatilake", "Chinthaka Jayatilake", "University of Moratuwa", "approved"),
        ("roshan-ragel", "Roshan Ragel", "University of Peradeniya", "approved"),
    ]
    events = fetch(
        connection,
        "SELECT event_type FROM author_profile_events WHERE event_type = %s",
        ("claim_added_by_coauthor_submission",),
    )
    assert len(events) == 1

    # The linked co-author can take a wrong attribution off their profile.
    workspace = authors.get_author_workspace(connection, SECOND)
    coauthored = next(claim for claim in workspace["claims"] if claim["publication_key"] == "doi:10.1000/coauthored")
    authors.remove_claim(connection, SECOND, {"claim_id": coauthored["claim_id"]})
    connection.commit()
    assert authors.public_profile(connection, "roshan-ragel")["stats"]["publication_count"] == 1
    with pytest.raises(APIError) as error:
        authors.remove_claim(connection, AUTHOR, {"claim_id": coauthored["claim_id"]})
    assert error.value.status == 404


def test_moving_institution_is_reflected_per_period_on_the_profile(connection) -> None:
    approved_author(connection)
    load_final_publications(
        [
            publication(
                "moved",
                publication_date="2024-03-01",
                institutions="University of Moratuwa; University of Peradeniya",
                authors="Chinthaka Jayatilake; Someone Else",
            )
        ],
        connection=connection,
        ensure_schema=False,
    )
    authors.request_claims(
        connection, AUTHOR, {"claims": [{"publication_key": "doi:10.1000/moved", "name_as_listed": "Chinthaka Jayatilake"}]}
    )
    claim = next(
        item for item in authors.list_claim_requests(connection)["records"] if item["publication_key"] == "doi:10.1000/moved"
    )
    authors.decide_claims(connection, ADMIN, {"claim_decisions": {claim["claim_id"]: "approved"}})
    connection.commit()

    with pytest.raises(APIError, match="end before they start"):
        authors.update_profile(
            connection, AUTHOR, {"affiliations": [{"institution": "UOM", "start_year": 2021, "end_year": 2015}]}
        )
    connection.rollback()

    workspace = authors.update_profile(
        connection,
        AUTHOR,
        {
            "bio": "Bio",
            "affiliations": [
                {"institution": "UOM", "start_year": 2012, "end_year": 2023, "position_title": "Lecturer"},
                {"institution": "University of Peradeniya", "start_year": 2024, "position_title": "Senior Lecturer"},
            ],
        },
    )
    connection.commit()
    assert [item["institution"] for item in workspace["profile"]["affiliations"]] == [
        "University of Peradeniya",
        "University of Moratuwa",
    ]
    # Saving without the history section leaves the history alone.
    authors.update_profile(connection, AUTHOR, {"bio": "New bio"})
    connection.commit()

    profile = authors.public_profile(connection, "chinthaka-jayatilake")
    assert len(profile["affiliations"]) == 2
    breakdown = {item["institution"]: item for item in profile["institution_breakdown"]["institutions"]}
    # The 2023 papers stay with Moratuwa; the 2024 paper, whose record lists
    # both universities, goes to Peradeniya because he had moved by then.
    assert breakdown["University of Moratuwa"]["publication_count"] == 3
    assert breakdown["University of Moratuwa"]["year_max"] == 2023
    assert breakdown["University of Peradeniya"] == {
        "institution": "University of Peradeniya",
        "publication_count": 1,
        "year_min": 2024,
        "year_max": 2024,
    }
    # Nothing about the move rewrote the dataset itself.
    assert fetch(
        connection, "SELECT institutions FROM final_publications WHERE publication_key = %s", ("doi:10.1000/a",)
    ) == [("University of Moratuwa",)]


def test_merged_spellings_join_the_profile_but_lookalikes_do_not(connection) -> None:
    approved_author(connection)
    # Merged sources print the author twice, next to a co-author with a
    # similar name who is someone else.
    load_final_publications(
        [publication("merged", authors="Chinthaka Jayatilake; C. Jayatilake; Ruwan Jayatilake")],
        connection=connection,
        ensure_schema=False,
    )
    authors.request_claims(
        connection,
        AUTHOR,
        {
            "claims": [{"publication_key": "doi:10.1000/merged", "name_as_listed": "Chinthaka Jayatilake"}],
            "name_variants": ["C. Jayatilake", "chinthaka jayatilake"],
        },
    )
    claim = next(
        item for item in authors.list_claim_requests(connection)["records"] if item["publication_key"] == "doi:10.1000/merged"
    )
    authors.decide_claims(connection, ADMIN, {"claim_decisions": {claim["claim_id"]: "approved"}})
    connection.commit()

    variants = fetch(connection, "SELECT name_variants FROM author_profiles WHERE slug = %s", ("chinthaka-jayatilake",))
    # The display name is not repeated as a variant.
    assert variants == [(["Jayatilake, C", "C. Jayatilake"],)]

    owned = authors.profiles_by_names(connection, ["C. Jayatilake", "Ruwan Jayatilake", "Jayatilake, C"])
    assert set(owned) == {"C. Jayatilake", "Jayatilake, C"}
    assert owned["C. Jayatilake"]["claimed_count"] == 1

    profile = authors.public_profile(connection, "chinthaka-jayatilake")
    counts = {row["name_as_listed"]: row["publication_count"] for row in profile["listed_name_counts"]}
    assert counts == {"Chinthaka Jayatilake": 3, "C. Jayatilake": 1, "Jayatilake, C": 1}

    assert [match["match"] for match in authors.list_public_profiles(connection, name="C. Jayatilake")] == ["claimed"]
    assert [match["match"] for match in authors.list_public_profiles(connection, name="Ruwan Jayatilake")] == []
