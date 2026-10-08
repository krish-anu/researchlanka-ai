from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

import pytest

from src.api.core.errors import APIError
from src.api.core.serializers import normalize_value
from src.api.routes import route_get, route_post
from src.api.services import author_profiles as authors
from src.api.services.author_publication_lookup import (
    abstract_from_inverted_index,
    crossref_lookup_payload,
    lookup_doi,
    split_page_range,
    strip_jats,
)
from src.database.final_schema import AUTHOR_SUBMISSION_SOURCE


MIGRATION = Path(__file__).resolve().parents[1] / "database" / "migrations" / "016_create_author_profiles.sql"


def application(**overrides):
    payload = {
        "display_name": "Chinthaka Jayatilake",
        "name_variants": "S. M. D. A. C. Jayatilake\nJayatilake, C",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
        "institution": "University of Moratuwa",
        "department": "Computer Science and Engineering",
        "claims": [{"publication_key": "doi:10.1/a", "name_as_listed": "Chinthaka Jayatilake"}],
    }
    payload.update(overrides)
    return payload


def new_publication(**overrides):
    payload = {
        "doi": "https://doi.org/10.1234/ABC.5678",
        "title": "Transformer models for Sinhala named entity recognition",
        "abstract": "We study transformer models for Sinhala named entity recognition " * 2,
        "publication_year": "2024",
        "type": "article",
        "authors": [
            {"name": "Chinthaka Jayatilake", "affiliation": "Department of CSE", "institution": "University of Moratuwa"},
            {"name": "Gamage Upeksha Ganegoda", "institution": "UOM", "country_code": "lk"},
            {"name": "Jane Doe", "institution": "University of Oxford", "country_code": "GB"},
        ],
        "your_author_name": "chinthaka  jayatilake",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------- validation


def test_orcid_is_normalised_and_checksum_verified() -> None:
    assert authors.normalize_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert authors.normalize_orcid("0000000218250097") == "0000-0002-1825-0097"
    assert authors.normalize_orcid("0000-0002-1694-233x") == "0000-0002-1694-233X"
    assert authors.normalize_orcid("") is None
    with pytest.raises(APIError, match="checksum"):
        authors.normalize_orcid("0000-0002-1825-0098")
    with pytest.raises(APIError, match="ORCID"):
        authors.normalize_orcid("orcid please")


def test_application_cleans_names_and_deduplicates_claims() -> None:
    data = authors.validate_application(
        application(
            name_variants=["Chinthaka Jayatilake", "Jayatilake, C", "jayatilake,  c", ""],
            claims=[
                {"publication_key": "doi:10.1/a", "name_as_listed": "C Jayatilake"},
                {"publication_key": "doi:10.1/a", "name_as_listed": "Chinthaka Jayatilake"},
            ],
        )
    )

    assert data["name_variants"] == ["Jayatilake, C"]
    assert data["orcid"] == "0000-0002-1825-0097"
    assert data["claims"] == [{"publication_key": "doi:10.1/a", "name_as_listed": "Chinthaka Jayatilake"}]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"display_name": "  "}, "display_name"),
        ({"institution": ""}, "institution"),
        ({"department": "x" * 201}, "department"),
        ({"claims": [{"publication_key": "doi:10.1/a"}]}, "name_as_listed"),
    ],
)
def test_application_rejects_missing_or_oversized_fields(overrides, field) -> None:
    with pytest.raises(APIError) as error:
        authors.validate_application(application(**overrides))
    assert error.value.details["field"] == field


def test_profile_links_must_point_at_the_named_service() -> None:
    updates = authors.validate_profile_update(
        {
            "bio": "Line one\r\n\r\n\r\nLine two\x00",
            "links": {
                "website_url": "https://example.lk/~me",
                "google_scholar_url": "https://scholar.google.com/citations?user=abc",
            },
        }
    )
    assert updates["bio"] == "Line one\n\nLine two"
    assert updates["researchgate_url"] is None

    with pytest.raises(APIError, match="Google Scholar link"):
        authors.validate_profile_update({"google_scholar_url": "https://evil.example/scholar"})
    with pytest.raises(APIError, match="https://"):
        authors.validate_profile_update({"website_url": "javascript:alert(1)"})


def test_edit_diff_keeps_only_real_changes_and_snapshots_the_old_values() -> None:
    current = {"title": "Old  title", "publication_year": 2023, "url": "https://a.example/x"}

    proposed, base = authors.diff_publication_changes(
        {"title": "Old title", "publication_year": "2024", "url": "https://a.example/y"},
        current,
    )

    assert proposed == {"publication_year": 2024, "url": "https://a.example/y"}
    assert base == {"publication_year": 2023, "url": "https://a.example/x"}


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({}, "no_changes"),
        ({"title": "Same"}, "no_changes"),
        ({"doi": "10.1/x"}, "field_not_editable"),
        ({"authors": "Someone Else"}, "field_not_editable"),
        ({"title": "   "}, "field_required"),
        ({"publication_year": "1066"}, "invalid_year"),
        ({"type": "blog-post"}, "invalid_type"),
    ],
)
def test_edit_diff_rejects_identity_fields_blanks_and_bad_values(changes, code) -> None:
    with pytest.raises(APIError) as error:
        authors.diff_publication_changes(changes, {"title": "Same"})
    assert error.value.code == code


def test_editable_fields_match_the_public_view_migration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    block = re.search(r"corrected_columns text\[\] := ARRAY\[(.*?)\];", sql, re.S)
    assert block is not None
    columns = re.findall(r"'([a-z_]+)'", block.group(1))
    assert columns == list(authors.EDITABLE_PUBLICATION_FIELDS)


def test_new_publication_validation_normalises_doi_and_resolves_the_author() -> None:
    record = authors.validate_new_publication(new_publication())

    assert record["doi"] == "10.1234/abc.5678"
    assert record["publication_year"] == 2024
    assert record["your_author_name"] == "Chinthaka Jayatilake"
    assert record["url"] is None


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"doi": "not a doi"}, "invalid_doi"),
        ({"abstract": "Too short."}, "abstract_too_short"),
        ({"doi": "", "url": ""}, "link_required"),
        ({"your_author_name": "Someone Else"}, "author_not_listed"),
        ({"authors": []}, "authors_required"),
        ({"authors": [{"name": "A One; B Two"}]}, "invalid_author_name"),
        ({"type": "tweet"}, "invalid_type"),
    ],
)
def test_new_publication_validation_errors(overrides, code) -> None:
    with pytest.raises(APIError) as error:
        authors.validate_new_publication(new_publication(**overrides))
    assert error.value.code == code


# ---------------------------------------------------------- name evidence


@pytest.mark.parametrize(
    ("listed", "profile_name", "expected"),
    [
        ("Chinthaka Jayatilake", "chinthaka jayatilake", "exact"),
        ("Senerath Mudalige Don Alexis Chinthaka Jayatilake", "Chinthaka Jayatilake", "initials"),
        ("Jayatilake, S.M.D.A.C.", "Chinthaka Jayatilake", "initials"),
        ("Perera A", "Anushka Perera", "initials"),
        ("Amaratunga, V", "Vinushi Amaratunga", "initials"),
        ("Anushka Perera", "Bimal Perera", "none"),
        ("Roshan Ragel", "Isuru Nawinne", "none"),
        ("", "Isuru Nawinne", "none"),
    ],
)
def test_name_match(listed, profile_name, expected) -> None:
    assert authors.name_match(listed, profile_name) == expected


def test_best_name_match_uses_every_variant() -> None:
    assert authors.best_name_match("Jayatilake, C", ["Someone Else", "C. Jayatilake"]) == "exact"


@pytest.mark.parametrize(
    ("email", "kind"),
    [
        ("me@cse.mrt.ac.lk", "academic"),
        ("me@uom.lk", "sri_lankan_organisation"),
        ("me@gmail.com", "free_webmail"),
        ("me@mit.edu", "academic"),
        ("me@company.com", "other"),
        ("broken", "unknown"),
    ],
)
def test_email_domain_evidence(email, kind) -> None:
    assert authors.email_domain_evidence(email)["kind"] == kind


def test_slugify_strips_marks_and_symbols() -> None:
    assert authors.slugify("Dr. Ānanda  Perera!") == "dr-ananda-perera"
    assert authors.slugify("!!!") == "author"


def test_title_key_matches_the_sql_normalisation() -> None:
    assert authors.title_key("Deep-Learning, for: SINHALA!") == "deeplearningforsinhala"


def test_hidden_reason_explains_why_a_duplicate_is_not_public() -> None:
    assert "retired" in authors.hidden_reason({"retired_at": "2026-01-01"})
    assert "not AI-related" in authors.hidden_reason({"review_status": "human_rejected"})
    assert "Sri Lanka-led" in authors.hidden_reason(
        {"review_status": "auto_accepted", "ownership_decision": "EXCLUDE", "ownership_confidence": "HIGH"}
    )


# ------------------------------------------------------- submission record


def test_submission_record_passes_both_public_gates_and_keeps_model_output() -> None:
    contribution = {
        "contribution_id": UUID("00000000-0000-0000-0000-000000000001"),
        "proposed": authors.validate_new_publication(new_publication()),
        "lookup_evidence": {
            "openalex_id": "W123",
            "institutions": "University of Moratuwa",
            "ownership": {"ownership_decision": "INCLUDE"},
        },
        "classifier": {"label": "non-AI", "confidence": "0.31", "model": "m.joblib", "reason": None},
    }

    record = authors.submission_record(contribution, {"email": "admin@example.com"})

    assert record["source_dataset"] == AUTHOR_SUBMISSION_SOURCE
    assert record["source_record_id"] == "00000000-0000-0000-0000-000000000001"
    assert record["authors"] == "Chinthaka Jayatilake; Gamage Upeksha Ganegoda; Jane Doe"
    assert record["author_affiliations"] == "Department of CSE, University of Moratuwa; University of Moratuwa; University of Oxford"
    # Each author's institution for this paper is what it counts towards.
    assert record["institutions"] == "University of Moratuwa; University of Oxford"
    assert record["sri_lankan_institutions"] == "University of Moratuwa"
    assert record["sri_lankan_authors"] == "Chinthaka Jayatilake; Gamage Upeksha Ganegoda"
    assert record["countries"] == "LK; GB"
    assert record["url"] == "https://doi.org/10.1234/abc.5678"
    assert record["ownership_decision"] == "INCLUDE"
    assert record["ownership_confidence"] == "HIGH"
    assert record["needs_manual_review"] == "false"
    # The model's own label is kept for traceability; the human decision is
    # recorded on the review record, not by rewriting this.
    assert record["ai_classification_label"] == "non-AI"
    assert "admin@example.com" in record["ownership_reason"]


def test_normalize_value_writes_uuid_and_decimal_as_json_types() -> None:
    from decimal import Decimal

    value = normalize_value({"id": UUID(int=5), "count": Decimal("3"), "score": Decimal("0.5")})
    assert value == {"id": "00000000-0000-0000-0000-000000000005", "count": 3, "score": 0.5}


# ----------------------------------------------------------------- lookup


def test_openalex_abstract_is_rebuilt_in_word_order() -> None:
    assert abstract_from_inverted_index({"models": [1], "Deep": [0], "work": [2, 4], "well": [3]}) == (
        "Deep models work well work"
    )
    assert abstract_from_inverted_index(None) == ""


def test_crossref_payload_maps_fields_and_strips_jats() -> None:
    payload = crossref_lookup_payload(
        {
            "title": ["A Crossref title"],
            "container-title": ["Journal of Tests"],
            "published-print": {"date-parts": [[2022, 3]]},
            "author": [{"given": "Anushka", "family": "Perera", "affiliation": [{"name": "SLIIT"}]}],
            "page": "11-19",
            "abstract": "<jats:p>Abstract Something <jats:italic>useful</jats:italic>.</jats:p>",
            "type": "journal-article",
        },
        "10.1/x",
    )
    fields = payload["fields"]
    assert payload["source"] == "crossref"
    assert fields["publication_year"] == 2022
    assert fields["journal"] == "Journal of Tests"
    assert (fields["first_page"], fields["last_page"]) == ("11", "19")
    assert fields["authors"] == [{"name": "Anushka Perera", "affiliation": "SLIIT", "institution": "", "country_code": ""}]
    assert fields["abstract"] == "Something useful ."
    assert "ownership_decision" in payload["ownership"]


def test_strip_jats_and_page_range_helpers() -> None:
    assert strip_jats(None) == ""
    assert split_page_range("e123") == ("e123", "")


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload

    def json(self):
        return self._payload


def test_lookup_falls_back_to_crossref_then_reports_not_found() -> None:
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "openalex" in url:
            return FakeResponse(404)
        return FakeResponse(200, {"message": {"title": ["Found in Crossref"], "author": []}})

    payload = lookup_doi("10.5555/abc", http_get=fake_get)
    assert payload["source"] == "crossref"
    assert payload["fields"]["title"] == "Found in Crossref"
    assert calls[0].endswith("/works/doi:10.5555/abc")

    with pytest.raises(APIError) as error:
        lookup_doi("10.5555/abc", http_get=lambda url, **kwargs: FakeResponse(404))
    assert error.value.code == "doi_not_found"

    with pytest.raises(APIError) as error:
        lookup_doi("nonsense")
    assert error.value.code == "invalid_doi"


def test_missing_model_leaves_the_decision_to_the_admin(monkeypatch, tmp_path) -> None:
    from src.api.services.author_publication_lookup import classify_submission

    monkeypatch.setenv("RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH", str(tmp_path / "missing.joblib"))

    result = classify_submission({"title": "A title", "abstract": "An abstract"})

    assert result == {
        "label": "review",
        "confidence": None,
        "model": None,
        "reason": "model_not_found",
        "available": False,
    }


# ---------------------------------------------------------------- routing


class MetaService:
    def _meta(self):
        return {"api_version": "v1"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/author/me"),
        ("get", "/api/v1/admin/authors/applications"),
        ("post", "/api/v1/author/applications"),
        ("post", "/api/v1/admin/authors/contributions/decide"),
    ],
)
def test_author_and_admin_routes_require_the_backend_token(monkeypatch, method, path) -> None:
    monkeypatch.setenv("RESEARCHLANKA_ADMIN_API_TOKEN", "secret")
    with pytest.raises(APIError) as error:
        if method == "get":
            route_get(MetaService(), path, {}, {"x-researchlanka-actor-id": "usr_1"})
        else:
            route_post(MetaService(), path, {}, {"x-researchlanka-actor-id": "usr_1"})
    assert error.value.status == 403


def test_author_workspace_requires_an_actor(monkeypatch) -> None:
    monkeypatch.setenv("RESEARCHLANKA_ADMIN_API_TOKEN", "secret")
    monkeypatch.setattr(authors, "with_connection", lambda operation: operation(object()))
    with pytest.raises(APIError) as error:
        route_get(MetaService(), "/api/v1/author/me", {}, {"x-researchlanka-admin-token": "secret"})
    assert error.value.status == 401


def test_public_profile_routes_win_over_researcher_names(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(authors, "with_connection", lambda operation: operation("connection"))
    monkeypatch.setattr(
        authors,
        "public_profile",
        lambda connection, slug: seen.append(("profile", slug)) or {"slug": slug},
    )
    monkeypatch.setattr(
        authors,
        "public_profile_publications",
        lambda connection, slug, **kwargs: seen.append(("publications", slug, kwargs["page"])) or {"data": []},
    )

    profile = route_get(MetaService(), "/api/v1/researchers/profiles/chinthaka-jayatilake", {}, {})
    route_get(MetaService(), "/api/v1/researchers/profiles/chinthaka-jayatilake/publications", {"page": ["2"]}, {})

    assert profile["data"] == {"slug": "chinthaka-jayatilake"}
    assert seen == [("profile", "chinthaka-jayatilake"), ("publications", "chinthaka-jayatilake", 2)]


def test_unrelated_paths_fall_through_the_author_dispatcher() -> None:
    from src.api.routing.author_routes import owns_path

    assert not owns_path("/api/v1/researchers/Chinthaka Jayatilake")
    assert not owns_path("/api/v1/authorship")
    assert owns_path("/api/v1/researchers/profiles")
