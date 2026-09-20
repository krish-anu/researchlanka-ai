"""AI review workflow unit tests.

Run (from backend/):

    pytest tests/ai_review -v
"""

from __future__ import annotations

import pytest

from src.api.core.errors import APIError
from src.api.services.ai_review import (
    Reviewer,
    assign_initial_pending,
    initial_review_status,
    normalize_ai_label,
    normalize_confidence,
)


def test_high_confidence_ai_label_auto_accepts_review_state():
    status, decision = initial_review_status("AI", "HIGH")
    assert status == "auto_accepted"
    assert decision == "auto"


def test_medium_or_borderline_ai_prediction_requires_human_review():
    status, decision = initial_review_status("AI", "MEDIUM")
    assert status == "pending_review"
    assert decision is None


def test_non_ai_prediction_is_rejected():
    status, _ = initial_review_status("NON_AI", "HIGH")
    assert status == "human_rejected"


def test_low_numeric_ai_confidence_is_rejected():
    status, _ = initial_review_status("AI", "0.4")
    assert status == "human_rejected"


def test_ai_label_normalization_maps_aliases_to_canonical_labels():
    assert normalize_ai_label("Non-AI") == "NON_AI"
    assert normalize_ai_label("yes") == "AI"
    assert normalize_ai_label(None) == "REVIEW"


def test_confidence_normalization_accepts_named_levels():
    assert normalize_confidence("high") == "HIGH"
    assert normalize_confidence("medium") == "MEDIUM"


class _FakeCursor:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params=None):
        self.connection.statements.append((sql, params))
        self.rowcount = 1

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list = []

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        return None


def test_assign_initial_pending_requires_at_least_one_reviewer():
    with pytest.raises((APIError, ValueError, AssertionError, Exception)):
        assign_initial_pending(_FakeConnection(), [])


def test_reviewer_dataclass_carries_identity_for_assignment():
    reviewer = Reviewer(id="r1", email="reviewer@example.com", name="Reviewer One")
    assert reviewer.email == "reviewer@example.com"
    assert reviewer.id == "r1"
