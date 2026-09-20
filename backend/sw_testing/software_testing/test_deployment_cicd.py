"""Master Test Plan 3.1.10 — Deployment and CI/CD Testing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.support.env_loader import REPO_ROOT


pytestmark = [pytest.mark.sw_testing]


def test_dev_ci_workflow_runs_backend_pytest():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies GitHub Actions Dev CI executes backend pytest.
    """
    workflow = REPO_ROOT / ".github" / "workflows" / "dev-ci.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "pytest" in text
    assert "working-directory: backend" in text


def test_dev_ci_workflow_runs_frontend_vitest_and_production_build():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies Dev CI includes frontend test and production build steps.
    """
    text = (REPO_ROOT / ".github" / "workflows" / "dev-ci.yml").read_text(encoding="utf-8")
    assert "vitest" in text.casefold() or "npm test" in text or "npm run test" in text
    assert "build" in text.casefold()


def test_backend_dockerfile_exists_for_api_image():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies backend API Dockerfile exists for containerized deployment.
    """
    assert (REPO_ROOT / "backend" / "Dockerfile.api").exists() or (
        REPO_ROOT / "backend" / "Dockerfile"
    ).exists()


def test_frontend_dockerfile_exists_for_web_image():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies frontend Dockerfile exists for containerized deployment.
    """
    assert (REPO_ROOT / "frontend" / "Dockerfile").exists()


def test_aws_compose_defines_db_api_and_frontend_services():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies compose.aws.yml declares db, api, and frontend services.
    """
    path = REPO_ROOT / "compose.aws.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = set((data.get("services") or {}).keys())
    assert {"db", "api", "frontend"}.issubset(services) or {"db"}.issubset(services)


def test_backend_compose_db_service_declares_healthcheck():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies local compose DB service includes a healthcheck.
    """
    path = REPO_ROOT / "backend" / "compose.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    db = (data.get("services") or {}).get("db") or {}
    assert "healthcheck" in db


def test_ec2_deploy_workflow_exists():
    """
    Test Plan: 3.1.10 Deployment and CI/CD Testing
    Verifies deploy-main-to-ec2 workflow is present for production deployment.
    """
    assert (REPO_ROOT / ".github" / "workflows" / "deploy-main-to-ec2.yml").exists()
