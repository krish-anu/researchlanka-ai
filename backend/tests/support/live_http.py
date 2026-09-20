"""HTTP helpers for live deployed ResearchLanka checks (real site, no dummy pages)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from typing import Any

from tests.support.env_loader import env_str, load_test_env


def deployed_base_url() -> str | None:
    load_test_env()
    value = env_str(
        "RESEARCHLANKA_DEPLOYED_BASE_URL",
        "RESEARCHLANKA_LIVE_BASE_URL",
        "DEPLOYED_BASE_URL",
    )
    return value.rstrip("/") if value else None


def deployed_api_base(site_base: str | None = None) -> str:
    load_test_env()
    configured = env_str(
        "RESEARCHLANKA_DEPLOYED_API_BASE_URL",
        "RESEARCHLANKA_LIVE_API_BASE_URL",
    )
    if configured:
        return configured.rstrip("/")
    base = site_base or deployed_base_url() or ""
    return f"{base.rstrip('/')}/api/v1"


def test_accounts() -> list[dict[str, str]]:
    """Accounts from .env — never hardcode passwords in source."""

    load_test_env()
    accounts: list[dict[str, str]] = []
    admin_email = env_str("RESEARCHLANKA_TEST_ADMIN_EMAIL", "ADMIN_EMAIL")
    admin_password = env_str("RESEARCHLANKA_TEST_ADMIN_PASSWORD", "ADMIN_PASSWORD")
    if admin_email and admin_password:
        accounts.append(
            {
                "label": "admin",
                "email": admin_email,
                "password": admin_password,
                "role": "admin",
            }
        )
    user_email = env_str("RESEARCHLANKA_TEST_USER_EMAIL", "ASMA_EMAIL")
    user_password = env_str("RESEARCHLANKA_TEST_USER_PASSWORD", "ASMA_PASSWORD")
    user_name = env_str("RESEARCHLANKA_TEST_USER_NAME", default="asma") or "asma"
    if user_email and user_password:
        accounts.append(
            {
                "label": user_name,
                "email": user_email,
                "password": user_password,
                "role": "user",
            }
        )
    return accounts


@dataclass
class LiveHttpClient:
    base_url: str
    timeout: float = 30.0
    jar: CookieJar = field(default_factory=CookieJar)
    opener: urllib.request.OpenerDirector = field(init=False)

    def __post_init__(self) -> None:
        # Avoid corporate/local proxies that break EC2 IP access from some hosts.
        for key in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "all_proxy",
        ):
            os.environ.pop(key, None)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.ProxyHandler({}),
        )

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
    ) -> tuple[int, str, dict[str, str]]:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = f"{self.base_url.rstrip('/')}/{path_or_url.lstrip('/')}"

        req_headers = {
            "User-Agent": "researchlanka-live-tests/1.0",
            "Accept": "*/*",
        }
        body = data
        if form is not None:
            body = urllib.parse.urlencode(form).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        if headers:
            req_headers.update(headers)

        request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                return int(response.status), text, resp_headers
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            resp_headers = {
                k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])
            }
            return int(exc.code), text, resp_headers

    def get_json(self, path_or_url: str) -> tuple[int, Any]:
        status, text, _headers = self.request("GET", path_or_url)
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            return status, text

    def login_via_server_action(
        self,
        email: str,
        password: str,
        *,
        next_path: str = "/admin",
    ) -> tuple[int, str, bool]:
        """Best-effort Next.js server-action sign-in using credentials from .env.

        Returns (status, body_snippet, session_cookie_present).
        """

        status, html, _ = self.request("GET", f"/login?next={urllib.parse.quote(next_path)}")
        if status >= 500:
            return status, html[:500], False

        action_id = None
        for pattern in (
            r'\$ACTION_ID_([a-f0-9]+)',
            r'"id"\s*:\s*"([a-f0-9]{40,})"',
            r'next-action["\s:=]+([a-f0-9]{40,})',
            r'action\s*=\s*\{[^}]*?([a-f0-9]{40,})',
        ):
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                action_id = match.group(1)
                break

        boundary = "----ResearchLankaBoundary7MA4YWxkTrZu0gW"
        # Field names match AuthForm: email, password, next (useActionState wraps as 1_*).
        parts = [
            f"--{boundary}",
            'Content-Disposition: form-data; name="1_email"',
            "",
            email,
            f"--{boundary}",
            'Content-Disposition: form-data; name="1_password"',
            "",
            password,
            f"--{boundary}",
            'Content-Disposition: form-data; name="1_next"',
            "",
            next_path,
            f"--{boundary}",
            'Content-Disposition: form-data; name="0"',
            "",
            '[{},"$K1"]',
            f"--{boundary}--",
            "",
        ]
        body = "\r\n".join(parts).encode("utf-8")
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "text/x-component,*/*",
            "Next-Action": action_id or "signIn",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/login?next={urllib.parse.quote(next_path)}",
        }
        status, text, resp_headers = self.request(
            "POST",
            f"/login?next={urllib.parse.quote(next_path)}",
            data=body,
            headers=headers,
        )
        cookie_names = {c.name.lower() for c in self.jar}
        has_session = any("session" in name or "auth" in name for name in cookie_names)
        # Also treat Set-Cookie presence in headers as success signal.
        if not has_session and "set-cookie" in resp_headers:
            has_session = "session" in resp_headers["set-cookie"].lower()
        return status, text[:800], has_session
