from __future__ import annotations

import pytest

from src.api.core.errors import APIError
from src.api.services.ai_review import (
    Reviewer,
    assign_initial_pending,
    initial_review_status,
    normalize_ai_label,
    normalize_confidence,
    numeric_confidence,
    overflow_chunks,
    sheet_value,
)


def test_high_explicit_ai_auto_accepts() -> None:
    assert initial_review_status("AI", "HIGH") == ("auto_accepted", "auto")
    assert initial_review_status("ai-related", "high") == ("auto_accepted", "auto")
    assert initial_review_status("AI", "0.85") == ("auto_accepted", "auto")
    assert initial_review_status("AI", "0.93") == ("auto_accepted", "auto")


@pytest.mark.parametrize(
    ("label", "confidence"),
    [
        ("AI", "MEDIUM"),
        ("AI", "LOW"),
        ("AI", ""),
        ("AI", "0.5"),
        ("AI", "0.849999"),
        ("review", "HIGH"),
        ("unexpected", "HIGH"),
    ],
)
def test_all_other_predictions_enter_manual_review(label: str, confidence: str) -> None:
    assert initial_review_status(label, confidence) == ("pending_review", None)


@pytest.mark.parametrize("confidence", ["0", "0.49", "0.499999"])
def test_low_numeric_ai_confidence_is_rejected(confidence: str) -> None:
    assert initial_review_status("AI", confidence) == ("human_rejected", None)


@pytest.mark.parametrize("confidence", ["HIGH", "0.99", "0.4", ""])
def test_non_ai_predictions_are_rejected(confidence: str) -> None:
    assert initial_review_status("NON_AI", confidence) == ("human_rejected", None)


def test_safe_label_and_confidence_normalization() -> None:
    assert normalize_ai_label("Non-AI") == "NON_AI"
    assert normalize_ai_label("yes") == "AI"
    assert normalize_ai_label(None) == "REVIEW"
    assert normalize_ai_label("maybe artificial") == "UNRECOGNIZED"
    assert normalize_confidence("HIGH") == "HIGH"
    assert normalize_confidence("medium") == "MEDIUM"
    assert normalize_confidence(None) is None
    assert normalize_confidence("0.88") == "UNRECOGNIZED"
    assert numeric_confidence("0.88") == 0.88
    assert numeric_confidence("1.2") is None


def test_literal_sheet_values_and_overflow() -> None:
    assert sheet_value("=IMPORTXML(A1)") == "'=IMPORTXML(A1)"
    assert sheet_value("+SUM(A:A)") == "'+SUM(A:A)"
    assert sheet_value("தமிழ் / Sinhala") == "தமிழ் / Sinhala"
    chunks = overflow_chunks("pub1", "abstract", "x" * 100_001)
    assert [chunk["chunk_number"] for chunk in chunks] == ["1", "2", "3"]
    assert "".join(chunk["content"] for chunk in chunks) == "x" * 100_001


class FakeCursor:
    def __init__(self, connection: "FakeAssignmentConnection") -> None:
        self.connection = connection
        self.rowcount = 0
        self._rows = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        if "assigned_reviewer_email AS email" in sql:
            self._rows = []
        elif "SELECT publication_key" in sql:
            self._rows = [{"publication_key": key} for key in self.connection.unassigned]
        elif "UPDATE ai_review_records" in sql:
            reviewer_email = params[1]
            publication_key = params[3]
            if publication_key in self.connection.unassigned:
                self.connection.unassigned.remove(publication_key)
                self.connection.assignments[publication_key] = reviewer_email
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "INSERT INTO ai_review_events" in sql:
            self.connection.events.append(params)
            self.rowcount = 1
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self._rows


class FakeAssignmentConnection:
    def __init__(self, keys: list[str]) -> None:
        self.unassigned = keys
        self.assignments: dict[str, str] = {}
        self.events = []

    def cursor(self, *_, **__) -> FakeCursor:
        return FakeCursor(self)


def test_equal_initial_assignment_is_deterministic_and_idempotent() -> None:
    connection = FakeAssignmentConnection(["p1", "p2", "p3", "p4", "p5"])
    reviewers = [
        Reviewer("1", "b@example.com", "B"),
        Reviewer("2", "a@example.com", "A"),
        Reviewer("3", "c@example.com", "C"),
    ]

    first = assign_initial_pending(connection, reviewers)
    second = assign_initial_pending(connection, reviewers)

    assert first["assigned"] == 5
    assert second["assigned"] == 0
    assert first["imbalance"] == 1
    assert connection.assignments == {
        "p1": "a@example.com",
        "p2": "b@example.com",
        "p3": "c@example.com",
        "p4": "a@example.com",
        "p5": "b@example.com",
    }


def test_assignment_requires_configured_reviewers() -> None:
    with pytest.raises(APIError):
        assign_initial_pending(FakeAssignmentConnection(["p1"]), [])
