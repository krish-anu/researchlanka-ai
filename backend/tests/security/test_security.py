"""Security tests.

Run (from backend/):

    pytest tests/security -v
"""

from __future__ import annotations

import pytest

from src.api.core.errors import APIError
from src.api.repositories.sql import build_where
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.api.services.incremental_admin import require_admin_api_token
from tests.support.env_loader import REPO_ROOT


SQLI = "malaria'; DROP TABLE final_publications;--"


@pytest.fixture
def admin_token_env(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "test-security-admin-token"
    monkeypatch.setenv("RESEARCHLANKA_ADMIN_API_TOKEN", token)
    return token


def test_protected_admin_endpoint_requires_authentication(
    api: ResearchLankaAPI, admin_token_env: str
):
    """Unauthenticated users cannot access admin functionality."""
    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/admin/incremental/status", {}, headers={})
    assert exc.value.status in {401, 403}
    assert "admin" in str(exc.value).casefold() or "forbidden" in str(
        getattr(exc.value, "code", "")
    ).casefold() or exc.value.status == 403


def test_protected_reviewer_endpoint_requires_authentication(
    api: ResearchLankaAPI, admin_token_env: str
):
    """Reviewer-only functionality cannot be accessed anonymously."""
    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/admin/ai-review", {}, headers={})
    assert exc.value.status in {401, 403}


def test_invalid_authentication_is_rejected(
    api: ResearchLankaAPI, admin_token_env: str
):
    """Wrong/invalid credentials or authentication tokens are rejected."""
    with pytest.raises(APIError) as exc:
        route_get(
            api,
            "/api/v1/admin/incremental/status",
            {},
            headers={"x-researchlanka-admin-token": "wrong-token"},
        )
    assert exc.value.status == 403

    with pytest.raises(APIError):
        require_admin_api_token({"authorization": "Bearer totally-invalid"})


def test_non_admin_user_cannot_access_admin_functionality():
    """A normal/reviewer account cannot access admin-only operations."""
    permissions = (
        REPO_ROOT / "frontend" / "src" / "services" / "auth" / "permissions.ts"
    ).read_text(encoding="utf-8")
    middleware = (
        REPO_ROOT / "frontend" / "src" / "middleware.ts"
    ).read_text(encoding="utf-8")

    assert '"admin.access": ["admin"]' in permissions
    assert '"admin.pipeline.run": ["admin"]' in permissions
    assert '"admin.ai_review.manage": ["admin"]' in permissions
    assert '"admin.resolution.decide": ["admin"]' in permissions
    assert 'user.role !== "admin"' in middleware
    assert "forbidden" in middleware


def test_invalid_or_malformed_input_is_rejected_safely(api: ResearchLankaAPI):
    """Malformed request parameters don't cause unsafe behavior."""
    with pytest.raises(APIError) as bad_year:
        route_get(
            api,
            "/api/v1/publications",
            {"year_min": ["abcd"], "page_size": ["5"]},
        )
    assert bad_year.value.status in {400, 422} or "invalid" in str(
        getattr(bad_year.value, "code", bad_year.value)
    ).casefold() or "integer" in str(bad_year.value).casefold()

    result = route_get(
        api,
        "/api/v1/publications",
        {"q": ["\x00<<<>>>"], "page_size": ["5"]},
    )
    assert "data" in result

    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/publications/missing-key-xyz", {})
    text = str(getattr(exc.value, "payload", exc.value)).lower()
    assert "/home/" not in text
    assert "traceback" not in text


def test_sql_injection_payload_is_not_executed(api: ResearchLankaAPI):
    """Search/input parameters don't allow SQL injection."""
    where_sql, params = build_where({"q": SQLI, "year_min": 2016, "year_max": 2026})
    assert "%s" in where_sql
    assert SQLI not in where_sql
    assert "DROP TABLE" not in where_sql.upper()
    assert "DROP" not in where_sql.upper() or "%s" in where_sql
    assert params

    listing = route_get(
        api,
        "/api/v1/publications",
        {"q": [SQLI], "page_size": ["5"]},
    )
    assert "data" in listing
    blob = str(listing).lower()
    assert "syntax error" not in blob


def test_sensitive_configuration_is_not_exposed(api: ResearchLankaAPI):
    """API responses/errors don't expose passwords, tokens, or secrets."""
    health = route_get(api, "/api/v1/health", {})
    meta = route_get(api, "/api/v1/meta", {})
    joined = f"{health}{meta}".lower()
    for secret in (
        "password",
        "postgres://",
        "postgresql://",
        "auth_secret",
        "admin_password",
        "researchlanka_admin_api_token",
        "bearer ",
    ):
        assert secret not in joined

    example = REPO_ROOT / "frontend" / ".env.example"
    if example.exists():
        text = example.read_text(encoding="utf-8")
        assert "NEXT_PUBLIC_AUTH_SECRET" not in text
        assert "NEXT_PUBLIC_ADMIN_PASSWORD" not in text
        assert "postgresql://" not in text.lower()


def test_security_headers_are_present():
    """Important HTTP security headers are returned by the deployed/API application."""
    config = (REPO_ROOT / "frontend" / "next.config.ts").read_text(encoding="utf-8")
    required = (
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "poweredByHeader: false",
    )
    for header in required:
        assert header in config, f"Missing security header config: {header}"

    session = (
        REPO_ROOT / "frontend" / "src" / "services" / "auth" / "session.ts"
    ).read_text(encoding="utf-8")
    assert "httpOnly: true" in session
    assert 'sameSite: "lax"' in session

    csrf = (
        REPO_ROOT / "frontend" / "src" / "services" / "auth" / "csrf-constants.ts"
    ).read_text(encoding="utf-8")
    assert 'CSRF_FIELD = "csrf_token"' in csrf
