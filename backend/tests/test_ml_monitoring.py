"""Unit tests for Real ML Monitoring module."""

import pytest
from src.api.services.ml_monitoring import (
    compute_psi,
    percent,
    get_period_dates,
    compute_ml_monitoring,
    CONFIDENCE_MEAN_DELTA_ALERT,
    PSI_ALERT_THRESHOLD,
)


def test_percent_calculation():
    assert percent(50, 100) == 50.0
    assert percent(1, 3) == 33.33
    assert percent(0, 100) == 0.0
    assert percent(10, 0) == 0.0
    assert percent(None, 100) == 0.0
    assert percent("invalid", 100) == 0.0


def test_compute_psi_identical_distributions():
    dist = {"AI": 0.5, "NON_AI": 0.5}
    psi = compute_psi(dist, dist)
    assert psi == 0.0


def test_compute_psi_shifted_distribution():
    base = {"AI": 0.2, "NON_AI": 0.8}
    shifted = {"AI": 0.7, "NON_AI": 0.3}
    psi = compute_psi(shifted, base)
    assert psi > PSI_ALERT_THRESHOLD


def test_get_period_dates():
    start, end = get_period_dates("2026-08")
    assert start == "2026-08-01"
    assert end == "2026-09-01"

    start_dec, end_dec = get_period_dates("2025-12")
    assert start_dec == "2025-12-01"
    assert end_dec == "2026-01-01"


class MockCursor:
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return {}

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []


class MockConnection:
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self.cursor_obj = MockCursor(fetchone_results, fetchall_results)

    def cursor(self, row_factory=None):
        return self.cursor_obj


def test_compute_ml_monitoring_empty():
    conn = MockConnection(fetchone_results=[], fetchall_results=[[]])
    report = compute_ml_monitoring(conn)
    assert report["status"] == "insufficient_data"
    assert report["overall_alert"] is False


def test_compute_ml_monitoring_synthetic_drift():
    # 1. determine_date_basis_and_periods (returns loaded_at months)
    # 2. curr query_period_stats (stats, review_stats, institutions)
    # 3. prev query_period_stats (stats, review_stats, institutions)
    mock_curr_stats = {
        "total": 100,
        "ai_count": 60,
        "non_ai_count": 40,
        "review_count": 0,
        "avg_p_ai": 0.81,
        "median_p_ai": 0.82,
        "std_p_ai": 0.15,
        "p_low": 10,
        "p_mid": 20,
        "p_high": 70,
        "avg_title_words": 14.0,
        "avg_abstract_words": 150.0,
        "with_abstract_count": 90,
        "missing_abstract": 10,
        "missing_doi": 5,
        "missing_inst": 0,
        "openalex_count": 94,
        "crossref_count": 6,
        "sljol_count": 0,
        "repo_count": 0,
    }
    mock_prev_stats = {
        "total": 100,
        "ai_count": 25,
        "non_ai_count": 75,
        "review_count": 0,
        "avg_p_ai": 0.62,
        "median_p_ai": 0.60,
        "std_p_ai": 0.18,
        "p_low": 40,
        "p_mid": 35,
        "p_high": 25,
        "avg_title_words": 13.5,
        "avg_abstract_words": 148.0,
        "with_abstract_count": 95,
        "missing_abstract": 5,
        "missing_doi": 5,
        "missing_inst": 0,
        "openalex_count": 68,
        "crossref_count": 20,
        "sljol_count": 12,
        "repo_count": 0,
    }
    mock_review_stats = {
        "review_rows": 100,
        "total_human_decisions": 10,
        "fp_overturns": 0,
        "fn_overturns": 0,
    }

    conn = MockConnection(
        fetchone_results=[
            mock_curr_stats, mock_review_stats,
            mock_prev_stats, mock_review_stats,
        ],
        fetchall_results=[
            [{"month": "2026-09"}, {"month": "2026-08"}],  # loaded_at months
            [{"institution": "University of Moratuwa", "count": 40}],  # curr inst
            [{"institution": "University of Moratuwa", "count": 25}],  # prev inst
        ],
    )

    report = compute_ml_monitoring(conn)
    assert report["status"] == "success"
    assert report["current_period"] == "2026-09"
    assert report["previous_period"] == "2026-08"

    # Confidence drift: 0.62 -> 0.81 (+0.19 >= 0.10)
    assert report["confidence_drift"]["previous_mean_p_ai"] == 0.62
    assert report["confidence_drift"]["current_mean_p_ai"] == 0.81
    assert report["confidence_drift"]["mean_p_ai_delta"] == 0.19
    assert report["confidence_drift"]["alert"] is True

    # Source drift: OpenAlex shifted from 68% to 94% (+26% >= 20%)
    openalex_source = next(s for s in report["source_drift"]["sources"] if s["name"] == "OpenAlex")
    assert openalex_source["previous_pct"] == 68.0
    assert openalex_source["current_pct"] == 94.0
    assert openalex_source["delta_points"] == 26.0
    assert openalex_source["alert"] is True
    assert report["source_drift"]["alert"] is True

    # Prediction drift: 25% -> 60% (+35 points)
    assert report["prediction_drift"]["alert"] is True
    assert report["overall_alert"] is True
    assert len(report["active_alerts"]) >= 3
