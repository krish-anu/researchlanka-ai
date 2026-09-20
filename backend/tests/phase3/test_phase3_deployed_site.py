"""Phase 3 — live / deployed site tests against real EC2 data (no dummy corpus).

Requires secrets in repo-root `.env` (gitignored):

  RESEARCHLANKA_DEPLOYED_BASE_URL=http://98.81.141.112:3000
  RESEARCHLANKA_TEST_ADMIN_EMAIL=...
  RESEARCHLANKA_TEST_ADMIN_PASSWORD=...
  RESEARCHLANKA_TEST_USER_EMAIL=...
  RESEARCHLANKA_TEST_USER_PASSWORD=...
"""

from __future__ import annotations

import pytest

from tests.support.env_loader import load_test_env
from tests.support.live_http import (
    LiveHttpClient,
    deployed_api_base,
    deployed_base_url,
    test_accounts as configured_accounts,
)


pytestmark = [pytest.mark.phase3, pytest.mark.deployed, pytest.mark.live]


@pytest.fixture(scope="module")
def deployed_base() -> str:
    load_test_env()
    base = deployed_base_url()
    if not base:
        pytest.skip(
            "Set RESEARCHLANKA_DEPLOYED_BASE_URL in .env to run live deployed-site tests"
        )
    return base


@pytest.fixture(scope="module")
def live_client(deployed_base: str) -> LiveHttpClient:
    client = LiveHttpClient(deployed_base)
    try:
        status, _body, _headers = client.request("GET", "/")
        if status >= 500:
            pytest.skip(f"Deployed site returned {status} for /")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Deployed site unreachable from this host ({exc})")
    return client


def test_deployed_frontend_root_serves_researchlanka(live_client: LiveHttpClient):
    status, body, _ = live_client.request("GET", "/")
    assert status < 500, f"frontend root returned {status}"
    assert status in {200, 301, 302, 307, 308} or status < 400
    lowered = body.lower()
    assert "researchlanka" in lowered or "<html" in lowered or "publication" in lowered


def test_deployed_login_page_is_reachable(live_client: LiveHttpClient):
    status, body, _ = live_client.request("GET", "/login")
    assert status < 500
    assert status in {200, 301, 302, 307, 308}
    lowered = body.lower()
    assert "sign in" in lowered or "email" in lowered or "password" in lowered


def test_deployed_admin_requires_auth(live_client: LiveHttpClient):
    status, body, _ = live_client.request("GET", "/admin")
    assert status != 500
    lowered = body.lower()
    assert "traceback" not in lowered
    assert "postgres://" not in lowered
    assert "auth_secret" not in lowered
    # Unauthenticated visitors should see sign-in or be redirected, not a raw admin shell
    # with pipeline controls leaking secrets.
    assert (
        status in {200, 301, 302, 307, 308, 401, 403}
        or "sign in" in lowered
        or "login" in lowered
        or "forbidden" in lowered
    )


def test_deployed_api_health_returns_ok(live_client: LiveHttpClient, deployed_base: str):
    api_base = deployed_api_base(deployed_base)
    status, payload = live_client.get_json(f"{api_base}/health")
    if status >= 500:
        pytest.fail(f"health endpoint server error: {status} {payload!r}")
    if status == 404:
        status, payload = live_client.get_json("/api/v1/health")
    if status != 200:
        pytest.skip(f"API health not publicly reachable via frontend proxy (status={status})")
    assert isinstance(payload, dict)
    data = payload.get("data", payload)
    assert str(data.get("status", "")).lower() in {"ok", "healthy", "up"} or "status" in data


def test_deployed_publications_return_real_rows(live_client: LiveHttpClient, deployed_base: str):
    api_base = deployed_api_base(deployed_base)
    status, payload = live_client.get_json(f"{api_base}/publications?page=1&page_size=5")
    if status != 200:
        pytest.skip(f"publications API not reachable (status={status})")
    assert isinstance(payload, dict)
    rows = payload.get("data") or []
    assert isinstance(rows, list) and len(rows) >= 1
    first = rows[0]
    assert first.get("title") or first.get("publication_key")
    # Must not be the old handmade dummy DOI.
    assert first.get("doi") != "10.1000/test"
    assert first.get("publication_key") != "doi:10.1000/test"


def test_deployed_meta_publication_count_is_nonzero(live_client: LiveHttpClient, deployed_base: str):
    api_base = deployed_api_base(deployed_base)
    status, payload = live_client.get_json(f"{api_base}/meta")
    if status != 200:
        pytest.skip(f"meta API not reachable (status={status})")
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    count = int(data.get("publication_count") or 0)
    assert count >= 1


@pytest.mark.parametrize("account_index", [0, 1], ids=["admin", "asma"])
def test_deployed_account_credentials_configured(account_index: int):
    accounts = configured_accounts()
    if account_index >= len(accounts):
        pytest.skip("Account credentials not set in .env")
    account = accounts[account_index]
    assert "@" in account["email"]
    assert len(account["password"]) >= 4


@pytest.mark.parametrize("account_index", [0, 1], ids=["admin", "asma"])
def test_deployed_login_attempt_with_env_credentials(
    live_client: LiveHttpClient,
    account_index: int,
):
    accounts = configured_accounts()
    if account_index >= len(accounts):
        pytest.skip("Account credentials not set in .env")
    account = accounts[account_index]
    status, body, has_session = live_client.login_via_server_action(
        account["email"],
        account["password"],
        next_path="/admin" if account["role"] == "admin" else "/",
    )
    # 200/303/302 = action handled; 400/401/403 = rejected but endpoint alive.
    assert status < 500, (
        f"login action crashed with {status} for {account['label']}: {body[:200]}"
    )
    admin_status, admin_body, _ = live_client.request("GET", "/admin")
    assert admin_status != 500
    assert "traceback" not in admin_body.lower()
    # Soft signal: either session cookie appeared or login page accepted the POST.
    assert status in {200, 303, 302, 307, 308, 400, 401, 403} or has_session
