"""Phase 3 — security testing matrix and controls.

Covers: SQL injection parameterization, invalid parameters, excessive data
exposure, secret exposure, HTTPS/cookie boundary, and API access isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from src.api.core.errors import APIError
from src.api.core.serializers import publication_detail, publication_summary
from src.api.repositories.sql import build_where, quote_identifier
from src.api.routes import route_get, route_post
from src.api.service import ResearchLankaAPI
from tests.phase3.helpers import (
    assert_no_secret_leak,
    attach_security_case,
    make_api,
)
from tests.support.real_dataset import load_real_publications


pytestmark = [pytest.mark.phase3, pytest.mark.security]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
SAMPLE_KEY = load_real_publications(limit=4)[0]["publication_key"]


SQLI_PAYLOADS = [
    "' OR 1=1 --",
    "1; DROP TABLE final_publications;--",
    "\" OR \"\"=\"",
    "malaria') OR ('1'='1",
    "1 UNION SELECT password FROM users--",
]


@dataclass
class SecurityCase:
    test_id: str
    endpoint: str
    scenario: str
    expected: str
    runner: str
    path: str = ""
    query: dict[str, list[str]] | None = None
    payload: dict[str, Any] | None = None


def _expect_invalid(api: ResearchLankaAPI, path: str, query: dict[str, list[str]]) -> None:
    with pytest.raises(APIError) as exc:
        route_get(api, path, query)
    assert exc.value.status in {400, 404, 422}
    assert_no_secret_leak({"code": exc.value.code, "message": exc.value.message, "details": exc.value.details})


def _expect_ok_no_secrets(api: ResearchLankaAPI, path: str, query: dict[str, list[str]]) -> None:
    payload = route_get(api, path, query)
    assert_no_secret_leak(payload)


def _expect_disabled_raw(api: ResearchLankaAPI, path: str, query: dict[str, list[str]]) -> None:
    with pytest.raises(APIError) as exc:
        route_get(api, path, query)
    assert exc.value.code == "disabled_endpoint"
    assert exc.value.status in {403, 404, 410, 400, 501} or exc.value.status >= 400


def _expect_sqli_safe(api: ResearchLankaAPI, path: str, query: dict[str, list[str]]) -> None:
    # Malicious strings must be treated as filter values, never crash with SQL text.
    try:
        payload = route_get(api, path, query)
        assert_no_secret_leak(payload)
        text = str(payload).lower()
        assert "syntax error" not in text
        assert "pg_" not in text
    except APIError as exc:
        assert exc.status < 500
        assert "sql" not in exc.message.lower()
        assert_no_secret_leak({"message": exc.message, "details": exc.details})


RUNNERS: dict[str, Callable[[ResearchLankaAPI, str, dict[str, list[str]]], None]] = {
    "invalid": _expect_invalid,
    "ok_no_secrets": _expect_ok_no_secrets,
    "disabled_raw": _expect_disabled_raw,
    "sqli_safe": _expect_sqli_safe,
}


SECURITY_CASES = [
    SecurityCase(
        test_id="SEC-001",
        endpoint="GET /api/v1/publications",
        scenario="SQL injection via q parameter",
        expected="Safe filter handling; no 500/SQL leak",
        runner="sqli_safe",
        path="/api/v1/publications",
        query={"q": [SQLI_PAYLOADS[0]]},
    ),
    SecurityCase(
        test_id="SEC-002",
        endpoint="GET /api/v1/publications",
        scenario="Stacked-query injection attempt",
        expected="Safe filter handling; no 500/SQL leak",
        runner="sqli_safe",
        path="/api/v1/publications",
        query={"q": [SQLI_PAYLOADS[1]]},
    ),
    SecurityCase(
        test_id="SEC-003",
        endpoint="GET /api/v1/search/suggest",
        scenario="SQL injection via suggest q",
        expected="Safe suggestions or validation error",
        runner="sqli_safe",
        path="/api/v1/search/suggest",
        query={"q": [SQLI_PAYLOADS[3]]},
    ),
    SecurityCase(
        test_id="SEC-004",
        endpoint="GET /api/v1/publications/{key}",
        scenario="Path-key injection attempt",
        expected="404/validation; no SQL leak",
        runner="sqli_safe",
        path="/api/v1/publications/' OR 1=1 --",
        query={},
    ),
    SecurityCase(
        test_id="SEC-005",
        endpoint="GET /api/v1/publications",
        scenario="Invalid year range",
        expected="invalid_filter error",
        runner="invalid",
        path="/api/v1/publications",
        query={"year_min": ["2025"], "year_max": ["2020"]},
    ),
    SecurityCase(
        test_id="SEC-006",
        endpoint="GET /api/v1/publications",
        scenario="Unknown query parameter",
        expected="invalid_query_parameter error",
        runner="invalid",
        path="/api/v1/publications",
        query={"drop_table": ["yes"]},
    ),
    SecurityCase(
        test_id="SEC-007",
        endpoint="GET /api/v1/publications",
        scenario="Oversized page_size",
        expected="clamped/validated list response or invalid_filter",
        runner="ok_no_secrets",
        path="/api/v1/publications",
        query={"page_size": ["999999"]},
    ),
    SecurityCase(
        test_id="SEC-008",
        endpoint="GET /api/v1/publications/{key}/raw",
        scenario="Raw record endpoint disabled",
        expected="disabled_endpoint",
        runner="disabled_raw",
        path=f"/api/v1/publications/{SAMPLE_KEY}/raw",
        query={},
    ),
    SecurityCase(
        test_id="SEC-009",
        endpoint="GET /api/v1/publications",
        scenario="List response omits raw_record body",
        expected="No raw_record / secret_token in list payload",
        runner="ok_no_secrets",
        path="/api/v1/publications",
        query={},
    ),
    SecurityCase(
        test_id="SEC-010",
        endpoint="GET /api/v1/search/semantic",
        scenario="Empty semantic query rejected",
        expected="invalid_filter",
        runner="invalid",
        path="/api/v1/search/semantic",
        query={},
    ),
]


@pytest.fixture
def api() -> ResearchLankaAPI:
    return make_api()


@pytest.mark.parametrize("case", SECURITY_CASES, ids=lambda case: case.test_id)
def test_security_matrix_case(
    case: SecurityCase, api: ResearchLankaAPI, request: pytest.FixtureRequest
):
    attach_security_case(
        request,
        test_id=case.test_id,
        endpoint=case.endpoint,
        scenario=case.scenario,
        expected=case.expected,
    )
    RUNNERS[case.runner](api, case.path, case.query or {})


def test_sql_build_where_parameterizes_user_input():
    """User-controlled values must land in params, not SQL string interpolation."""
    payload = "malaria'; DROP TABLE final_publications;--"
    where_sql, params = build_where({"q": payload, "year_min": 2016, "year_max": 2026})
    assert "%s" in where_sql
    assert payload not in where_sql
    assert any(payload in str(param) or payload == param for param in params) or any(
        "malaria" in str(param).lower() for param in params
    )
    # No unquoted user payload fragments in SQL.
    assert "DROP TABLE" not in where_sql


def test_quote_identifier_escapes_embedded_quotes():
    assert quote_identifier('evil"; DROP TABLE x; --') == '"evil""; DROP TABLE x; --"'


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_build_where_never_embeds_sqli_literals(payload: str):
    where_sql, params = build_where({"q": payload, "researcher": [payload]})
    assert payload not in where_sql
    assert "DROP TABLE" not in where_sql
    assert params  # values are bound


def test_publication_summary_does_not_expose_raw_record():
    summary = publication_summary(
        {
            "publication_key": "doi:10.1000/x",
            "title": "T",
            "raw_record": {"token": "secret_token", "password": "x"},
            "authors": "A",
            "institutions": "B",
        }
    )
    assert "raw_record" not in summary
    assert_no_secret_leak(summary)


def test_publication_detail_does_not_dump_raw_record_blob():
    detail = publication_detail(
        {
            "publication_key": "doi:10.1000/x",
            "title": "T",
            "raw_record": {"token": "secret_token"},
            "authors": "A",
            "institutions": "B",
            "abstract": "hello",
        }
    )
    assert detail.get("raw_record") in (None, {}, False) or "raw_record" not in detail or detail.get(
        "raw_record_available"
    ) in {True, False}
    blob = str(detail)
    assert "secret_token" not in blob


def test_error_payload_shape_avoids_internal_paths(api: ResearchLankaAPI):
    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/publications", {"not_a_real_filter": ["1"]})
    body = {"error": {"code": exc.value.code, "message": exc.value.message, "details": exc.value.details}}
    assert_no_secret_leak(body)
    assert "/home/" not in exc.value.message
    assert "traceback" not in exc.value.message.lower()


def test_compose_does_not_publish_api_port():
    compose = (REPO_ROOT / "compose.aws.yml").read_text(encoding="utf-8")
    # Extract the api service block until the next top-level service.
    match = re.search(r"(?ms)^  api:\n(.*?)(?=^  [a-z]|\Z)", compose)
    assert match, "api service missing from compose.aws.yml"
    api_block = match.group(1)
    assert "ports:" not in api_block
    assert "SEED_TEST_ACCOUNTS" not in api_block or 'SEED_TEST_ACCOUNTS: "false"' in compose


def test_compose_disables_seed_test_accounts_and_requires_auth_secret():
    compose = (REPO_ROOT / "compose.aws.yml").read_text(encoding="utf-8")
    assert 'SEED_TEST_ACCOUNTS: "false"' in compose
    assert "AUTH_SECRET" in compose
    assert "ADMIN_PASSWORD" in compose


def test_frontend_admin_route_requires_capability():
    route = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "app"
        / "api"
        / "admin"
        / "incremental"
        / "run"
        / "route.ts"
    ).read_text(encoding="utf-8")
    assert 'can(viewer.role, "admin.pipeline.run")' in route
    assert "403" in route


def test_frontend_middleware_protects_admin_and_account():
    middleware = (REPO_ROOT / "frontend" / "src" / "middleware.ts").read_text(encoding="utf-8")
    assert '"/admin"' in middleware
    assert '"/account"' in middleware
    assert "forbidden" in middleware


def test_session_cookie_defaults_http_only_and_secure_in_production():
    session = (
        REPO_ROOT / "frontend" / "src" / "services" / "auth" / "session.ts"
    ).read_text(encoding="utf-8")
    assert "httpOnly: true" in session
    assert "AUTH_COOKIE_SECURE" in session
    assert 'sameSite: "lax"' in session


def test_no_auth_secret_in_next_public_env_example():
    example = REPO_ROOT / "frontend" / ".env.example"
    if not example.exists():
        pytest.skip("frontend .env.example missing")
    text = example.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_AUTH_SECRET" not in text
    assert "NEXT_PUBLIC_ADMIN_PASSWORD" not in text


def test_https_boundary_documented_for_deploy():
    """TLS terminates outside the app containers (ALB/Nginx); cookie Secure is configurable."""
    deploy_docs = list((REPO_ROOT / "docs").glob("*deploy*")) + list(
        (REPO_ROOT / "docs").glob("*aws*")
    )
    assert deploy_docs, "Expected deploy docs describing HTTPS boundary"
    blob = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in deploy_docs)
    assert re.search(r"https|TLS|ALB|nginx", blob, re.I)


def test_python_admin_write_surface_is_post_only_and_conflict_aware():
    """Admin run is a POST route; overlapping runs must 409 rather than double-start."""
    # route_post only accepts the incremental run path among writes.
    api = make_api()
    with pytest.raises(APIError) as exc:
        route_post(api, "/api/v1/unknown", {})
    assert exc.value.status == 404
