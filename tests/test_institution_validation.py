"""Tests for scripts/validate_institutions.py and scripts/detect_registry_drift.py.

Both read files on disk, so the tests monkeypatch the small helpers that
touch the filesystem and drive the pure validation logic directly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load(module_name: str):
    spec = importlib.util.spec_from_file_location(
        module_name, PROJECT_ROOT / "scripts" / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_institutions = _load("validate_institutions")
detect_registry_drift = _load("detect_registry_drift")


def entry(**overrides):
    base = {
        "id": "test",
        "name": "Test University",
        "group": "A",
        "status": "confirmed_live",
        "phase": "phase_1",
        "repository_url": "https://example.ac.lk",
        "oai_endpoint": "https://example.ac.lk/oai/request",
    }
    base.update(overrides)
    return base


@pytest.fixture
def no_records(monkeypatch):
    monkeypatch.setattr(validate_institutions, "count_records", lambda directory, i: 0)


def checks(findings, name):
    return [f for f in findings if f["check"] == name]


def test_duplicate_ids_are_errors(no_records):
    findings = validate_institutions.validate(
        [entry(id="dup", name="One"), entry(id="dup", name="Two")], {"institutions": []}
    )
    assert checks(findings, "duplicate_id")
    assert all(f["severity"] == "error" for f in checks(findings, "duplicate_id"))


def test_duplicate_names_are_detected_case_insensitively(no_records):
    findings = validate_institutions.validate(
        [entry(id="a", name="University of Test"), entry(id="b", name="university  of  test")],
        {"institutions": []},
    )
    assert checks(findings, "duplicate_name")


def test_live_status_requires_a_reachable_route(no_records):
    findings = validate_institutions.validate(
        [entry(oai_endpoint=None, rest_api_endpoint=None)], {"institutions": []}
    )
    missing = checks(findings, "missing_required_field")
    assert any("neither oai_endpoint nor rest_api_endpoint" in f["message"] for f in missing)
    assert any(f["severity"] == "error" for f in missing)


def test_rest_only_target_is_accepted(no_records):
    findings = validate_institutions.validate(
        [entry(oai_endpoint=None, rest_api_endpoint="https://example.ac.lk/server/api")],
        {"institutions": []},
    )
    assert not [f for f in checks(findings, "missing_required_field") if f["severity"] == "error"]


def test_undocumented_dead_end_is_a_warning_not_an_error(no_records):
    """Missing prose is incomplete, not provably wrong -- it must not gate CI."""
    findings = validate_institutions.validate(
        [entry(status="no_repository_found", notes=None, phase="not_applicable")],
        {"institutions": []},
    )
    notes_findings = checks(findings, "missing_required_field")
    assert notes_findings
    assert all(f["severity"] == "warning" for f in notes_findings)


def test_records_contradicting_no_repository_status_are_errors(monkeypatch):
    monkeypatch.setattr(
        validate_institutions,
        "count_records",
        lambda directory, i: 500 if directory.name == "repositories" else 0,
    )
    findings = validate_institutions.validate(
        [entry(status="no_repository_found", notes="checked", phase="not_applicable")],
        {"institutions": []},
    )
    assert checks(findings, "contradicted_by_data")
    assert all(f["severity"] == "error" for f in checks(findings, "contradicted_by_data"))


def test_missing_reference_institution_is_a_coverage_gap(no_records):
    findings = validate_institutions.validate(
        [entry(id="present")],
        {"institutions": [{"registry_id": "absent", "name": "Missing University"}]},
    )
    gaps = [f for f in checks(findings, "coverage_gap") if f["id"] == "absent"]
    assert gaps and gaps[0]["severity"] == "error"


def test_hosted_by_must_point_at_a_real_entry(no_records):
    findings = validate_institutions.validate(
        [entry(id="child", status="no_own_repository", notes="hosted", hosted_by="ghost")],
        {"institutions": []},
    )
    assert any(f["severity"] == "error" for f in checks(findings, "hosted_by"))


def test_recovery_route_without_its_query_is_an_error(no_records):
    findings = validate_institutions.validate(
        [
            entry(
                status="blocked_for_automated_requests",
                notes="blocked",
                recovery_routes=["crossref_affiliation"],
            )
        ],
        {"institutions": []},
    )
    assert checks(findings, "incomplete_recovery_config")


# --- drift detection -------------------------------------------------


def validation_report(institution_id, **oai):
    return {"results": [{"id": institution_id, "oai": oai}]}


@pytest.fixture
def no_raw(monkeypatch):
    monkeypatch.setattr(detect_registry_drift, "actual_route", lambda i: (None, 0))


def drifts(findings, kind):
    return [f for f in findings if f["drift"] == kind]


def test_live_status_with_dead_endpoint_is_drift(no_raw):
    findings = detect_registry_drift.detect(
        [entry(id="ruh", status="confirmed_live")],
        validation_report("ruh", reachable=False, error="timed out"),
    )
    assert drifts(findings, "endpoint_died")


def test_dead_status_with_live_endpoint_is_drift(no_raw):
    findings = detect_registry_drift.detect(
        [entry(id="sab", status="unreachable")],
        validation_report("sab", reachable=True),
    )
    assert drifts(findings, "endpoint_recovered")


def test_self_reported_baseurl_is_not_treated_as_a_move(no_raw):
    """busl answers on one host but advertises another; that is a source-side
    config quirk, not evidence the endpoint moved."""
    findings = detect_registry_drift.detect(
        [entry(id="busl", oai_endpoint="https://dl-busl.nsf.gov.lk/server/oai/request")],
        validation_report(
            "busl",
            reachable=True,
            endpoint_tried="https://dl-busl.nsf.gov.lk/server/oai/request",
            base_url="https://repo.busl.ac.lk/server/oai/request",
        ),
    )
    assert not drifts(findings, "endpoint_moved")


def test_explicit_default_port_is_not_a_move(no_raw):
    findings = detect_registry_drift.detect(
        [entry(id="vpa", oai_endpoint="http://repo.vpa.ac.lk/oai/request")],
        validation_report(
            "vpa", reachable=True, endpoint_tried="http://repo.vpa.ac.lk:80/oai/request"
        ),
    )
    assert not drifts(findings, "endpoint_moved")


def test_genuine_fallback_url_is_reported_as_a_move(no_raw):
    findings = detect_registry_drift.detect(
        [entry(id="x", oai_endpoint="https://x.ac.lk/oai/request")],
        validation_report(
            "x", reachable=True, endpoint_tried="https://x.ac.lk/server/oai/request"
        ),
    )
    assert drifts(findings, "endpoint_moved")


def test_route_mismatch_between_registry_and_disk(monkeypatch):
    monkeypatch.setattr(detect_registry_drift, "actual_route", lambda i: ("rest", 8452))
    findings = detect_registry_drift.detect(
        [entry(id="cmb", harvest_route="html")], {"results": []}
    )
    assert drifts(findings, "route_mismatch")


def test_no_drift_when_registry_matches_evidence(no_raw):
    findings = detect_registry_drift.detect(
        [entry(id="uom", status="confirmed_live", endpoint_verified_live=True)],
        validation_report(
            "uom",
            reachable=True,
            has_records=True,
            endpoint_tried="https://example.ac.lk/oai/request",
        ),
    )
    assert findings == []
