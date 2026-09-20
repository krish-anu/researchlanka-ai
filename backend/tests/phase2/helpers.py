"""Shared helpers for Phase 2 API matrix tests."""

from __future__ import annotations

from typing import Any

import pytest


def attach_api_case(
    request: pytest.FixtureRequest,
    *,
    test_id: str,
    endpoint: str,
    scenario: str,
    expected: str,
) -> dict[str, str]:
    """Attach API matrix metadata so the session reporter can fill Result."""

    case = {
        "test_id": test_id,
        "endpoint": endpoint,
        "scenario": scenario,
        "expected": expected,
    }
    request.node._phase2_api_case = case  # type: ignore[attr-defined]
    return case


def assert_list_payload(payload: dict[str, Any]) -> None:
    assert "data" in payload
    assert "pagination" in payload
    assert "meta" in payload
    assert isinstance(payload["data"], list)


def assert_detail_payload(payload: dict[str, Any]) -> None:
    assert "data" in payload
    assert "meta" in payload
    assert isinstance(payload["data"], dict)
