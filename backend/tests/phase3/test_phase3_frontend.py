"""Phase 3 — frontend contract checks (static + Vitest bridge)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.phase3, pytest.mark.frontend]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = REPO_ROOT / "frontend"


def test_api_client_uses_server_side_base_url_and_timeout():
    api_ts = (FRONTEND_ROOT / "src" / "services" / "api.ts").read_text(encoding="utf-8")
    assert "API_BASE_URL" in api_ts
    assert "REQUEST_TIMEOUT_MS" in api_ts
    assert "20_000" in api_ts or "20000" in api_ts
    assert "ApiResult" in api_ts
    assert "unreachable" in api_ts
    assert "timeout" in api_ts


def test_next_rewrite_proxies_api_v1_same_origin():
    config = (FRONTEND_ROOT / "next.config.ts").read_text(encoding="utf-8")
    assert "/api/v1/:path*" in config
    assert "API_BASE_URL" in config


def test_frontend_permissions_gate_admin_pipeline():
    permissions = (
        FRONTEND_ROOT / "src" / "services" / "auth" / "permissions.ts"
    ).read_text(encoding="utf-8")
    assert "admin.pipeline.run" in permissions
    assert "admin.pipeline.view" in permissions


def test_vitest_suite_passes():
    """Run the frontend unit suite and fail Phase 3 if Vitest is red."""
    if os.environ.get("PHASE3_SKIP_VITEST") == "1":
        pytest.skip("PHASE3_SKIP_VITEST=1")
    if not FRONTEND_ROOT.exists():
        pytest.skip("frontend package missing")
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("npm not available")

    completed = subprocess.run(
        [npm, "test", "--silent"],
        cwd=FRONTEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            "Frontend Vitest failed:\n"
            + (completed.stdout[-2000:] if completed.stdout else "")
            + (completed.stderr[-2000:] if completed.stderr else "")
        )


def test_package_json_exposes_test_script():
    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    assert "test" in package["scripts"]
    assert "vitest" in package["scripts"]["test"]
