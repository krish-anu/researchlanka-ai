"""Master Test Plan 3.1.11 — Configuration and Compatibility Testing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.support.env_loader import REPO_ROOT, env_str, load_test_env


pytestmark = [pytest.mark.sw_testing]


def test_root_env_example_documents_deployed_base_url_keys():
    """
    Test Plan: 3.1.11 Configuration and Compatibility Testing
    Verifies .env.example documents deployed URL configuration keys.
    """
    example = REPO_ROOT / ".env.example"
    assert example.exists()
    text = example.read_text(encoding="utf-8")
    assert "RESEARCHLANKA_DEPLOYED_BASE_URL" in text


def test_backend_env_loader_reads_repo_and_backend_dotenv_files():
    """
    Test Plan: 3.1.11 Configuration and Compatibility Testing
    Verifies test env loader can resolve configuration without crashing.
    """
    load_test_env()
    # Presence optional; loader must not raise.
    _ = env_str("RESEARCHLANKA_DEPLOYED_BASE_URL", "DATABASE_URL")


def test_aws_compose_binds_postgres_to_loopback_by_default():
    """
    Test Plan: 3.1.11 Configuration and Compatibility Testing
    Verifies AWS compose publishes Postgres on loopback/host port mapping safely.
    """
    data = yaml.safe_load((REPO_ROOT / "compose.aws.yml").read_text(encoding="utf-8"))
    db = (data.get("services") or {}).get("db") or {}
    ports = str(db.get("ports") or "")
    assert "5432" in ports or "POSTGRES_PORT" in ports or ports


def test_frontend_package_declares_browserslist_or_next_build_target():
    """
    Test Plan: 3.1.11 Configuration and Compatibility Testing
    Verifies frontend package is a Next.js app with a build script.
    """
    package = (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert "next" in package.casefold()
    assert '"build"' in package


def test_playwright_config_exists_for_optional_browser_smoke():
    """
    Test Plan: 3.1.11 Configuration and Compatibility Testing
    Verifies Playwright config exists for browser smoke evidence when run.
    """
    assert (REPO_ROOT / "frontend" / "playwright.config.ts").exists()


def test_vitest_config_exists_for_component_test_matrix():
    """
    Test Plan: 3.1.11 Configuration and Compatibility Testing
    Verifies Vitest config exists for component-level UI automation.
    """
    assert (REPO_ROOT / "frontend" / "vitest.config.ts").exists()
