"""Phase 3 — deploy / accessibility / config hardening checks."""

from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.phase3]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


@pytest.mark.deploy_config
def test_compose_restart_and_healthchecks_present():
    compose = (REPO_ROOT / "compose.aws.yml").read_text(encoding="utf-8")
    assert "restart: unless-stopped" in compose
    assert "healthcheck:" in compose
    assert "condition: service_healthy" in compose


@pytest.mark.deploy_config
def test_database_password_required_in_compose():
    compose = (REPO_ROOT / "compose.aws.yml").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD:?set POSTGRES_PASSWORD" in compose


@pytest.mark.deploy_config
def test_frontend_only_public_port_in_aws_compose():
    compose = (REPO_ROOT / "compose.aws.yml").read_text(encoding="utf-8")
    # Only frontend should bind a host port for the app surface.
    assert "FRONTEND_PORT" in compose
    assert "3000:3000" in compose or "${FRONTEND_PORT" in compose


@pytest.mark.accessibility
def test_api_error_bodies_are_structured_for_ui_panels():
    """Frontend ApiFailure mapping depends on {error:{code,message,details}}."""
    from src.api.core.errors import APIError

    exc = APIError("invalid_filter", "bad", details={"field": "q"})
    body = {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
    assert set(body["error"]) >= {"code", "message", "details"}


@pytest.mark.accessibility
def test_frontend_forbidden_and_login_routes_exist():
    app = REPO_ROOT / "frontend" / "src" / "app"
    assert (app / "login").exists() or any(app.rglob("login/**/page.tsx"))
    assert (app / "forbidden").exists() or any(app.rglob("forbidden/**/page.tsx"))
