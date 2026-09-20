"""Shared helpers for Phase 3 overall application tests."""

from __future__ import annotations

from typing import Any

import pytest

from src.api.service import ResearchLankaAPI
from tests.support.env_loader import load_test_env
from tests.support.real_dataset import RealPublicationRepository, load_real_publications


# Kept only for recovery/security edge fixtures that intentionally inject failures.
PUBLICATIONS = list(load_real_publications(limit=8))


class FakeRepository(RealPublicationRepository):
    """Backward-compatible name; now backed by real common-dataset rows."""


def make_api(**kwargs) -> ResearchLankaAPI:
    """Build API service over real common-dataset rows (not handmade fixtures)."""

    load_test_env()
    repo = RealPublicationRepository()
    for key, value in kwargs.items():
        setattr(repo, key, value)
    return ResearchLankaAPI(repo)


def attach_security_case(
    request: pytest.FixtureRequest,
    *,
    test_id: str,
    endpoint: str,
    scenario: str,
    expected: str,
) -> dict[str, str]:
    case = {
        "test_id": test_id,
        "endpoint": endpoint,
        "scenario": scenario,
        "expected": expected,
    }
    request.node._phase3_security_case = case  # type: ignore[attr-defined]
    return case


def assert_no_secret_leak(payload: Any) -> None:
    text = str(payload).lower()
    forbidden = (
        "password=",
        "postgres://",
        "postgresql://",
        "auth_secret",
        "secret_token",
        "api_key=",
        "private_key",
    )
    for needle in forbidden:
        assert needle not in text, f"Possible secret leak containing {needle!r}"
