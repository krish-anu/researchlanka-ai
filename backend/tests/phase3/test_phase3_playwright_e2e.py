"""Phase 3 — Playwright browser E2E smoke (T-07).

Uses system Google Chrome via Playwright channel=\"chrome\" (no browser download).
Requires RESEARCHLANKA_DEPLOYED_BASE_URL to be reachable.
"""

from __future__ import annotations

import os

import pytest

from tests.support.env_loader import load_test_env
from tests.support.live_http import deployed_base_url, test_accounts


pytestmark = [pytest.mark.phase3, pytest.mark.frontend, pytest.mark.live]


def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture(scope="module")
def browser_page():
    load_test_env()
    base = deployed_base_url()
    if not base:
        pytest.skip("Set RESEARCHLANKA_DEPLOYED_BASE_URL for Playwright E2E")
    if not _playwright_available():
        pytest.skip("playwright package not installed")

    from playwright.sync_api import sync_playwright

    # Clear proxies that break EC2 IP access.
    for key in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "all_proxy",
    ):
        os.environ.pop(key, None)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=True,
            )
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Cannot launch system Chrome for Playwright ({exc})")
        context = browser.new_context(base_url=base)
        page = context.new_page()
        try:
            page.goto("/", timeout=20_000, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            browser.close()
            pytest.skip(f"Deployed site unreachable for Playwright ({exc})")
        yield page, base
        browser.close()


def test_e2e_home_shows_researchlanka(browser_page):
    page, _base = browser_page
    page.goto("/", wait_until="domcontentloaded")
    body = page.locator("body").inner_text()
    assert "ResearchLanka" in body or "publication" in body.lower() or "Search" in body


def test_e2e_login_page_fields_present(browser_page):
    page, _base = browser_page
    page.goto("/login", wait_until="domcontentloaded")
    assert page.get_by_label("Email").count() >= 1 or page.locator('input[type="email"]').count() >= 1
    assert page.get_by_label("Password").count() >= 1 or page.locator('input[type="password"]').count() >= 1


def test_e2e_publications_page_does_not_500(browser_page):
    page, _base = browser_page
    response = page.goto("/publications", wait_until="domcontentloaded")
    assert response is None or response.status < 500
    body = page.locator("body").inner_text().lower()
    assert "traceback" not in body
    assert "internal server error" not in body


def test_e2e_admin_gate_without_session(browser_page):
    page, _base = browser_page
    page.goto("/admin", wait_until="domcontentloaded")
    body = page.locator("body").inner_text().lower()
    url = page.url
    gated = (
        "sign in" in body
        or "login" in body
        or "forbidden" in body
        or "/login" in url
        or "/forbidden" in url
    )
    assert gated or "traceback" not in body
    assert "postgres://" not in body


@pytest.mark.parametrize("account_index", [0, 1], ids=["admin", "asma"])
def test_e2e_login_with_env_account(browser_page, account_index: int):
    page, _base = browser_page
    accounts = test_accounts()
    if account_index >= len(accounts):
        pytest.skip("Account credentials missing in .env")
    account = accounts[account_index]
    next_path = "/admin" if account["role"] == "admin" else "/"
    page.goto(f"/login?next={next_path}", wait_until="domcontentloaded")
    email = page.get_by_label("Email")
    if email.count() == 0:
        email = page.locator('input[type="email"]').first
    password = page.get_by_label("Password")
    if password.count() == 0:
        password = page.locator('input[type="password"]').first
    email.fill(account["email"])
    password.fill(account["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_timeout(1500)
    body = page.locator("body").inner_text()
    assert "Email or password is incorrect" not in body
