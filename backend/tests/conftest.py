"""Pytest hooks for Phase 1 + Phase 2 + Phase 3 structured reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.env_loader import load_test_env

load_test_env()

from tests.reporting.phase1_results import (
    DEFAULT_REPORT_DIR as PHASE1_REPORT_DIR,
    TestResultRow as Phase1Row,
    infer_category as infer_phase1_category,
    write_phase1_report,
)
from tests.reporting.phase2_results import (
    DEFAULT_REPORT_DIR as PHASE2_REPORT_DIR,
    ApiMatrixRow,
    TestResultRow as Phase2Row,
    infer_phase2_category,
    write_phase2_report,
)
from tests.reporting.phase3_results import (
    DEFAULT_REPORT_DIR as PHASE3_REPORT_DIR,
    SecurityMatrixRow,
    TestResultRow as Phase3Row,
    infer_phase3_category,
    write_phase3_report,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    phase1 = parser.getgroup("phase1")
    phase1.addoption(
        "--phase1-report-dir",
        action="store",
        default=str(PHASE1_REPORT_DIR),
        help="Directory for Phase 1 structured test reports (CSV/MD/JSON).",
    )
    phase1.addoption(
        "--phase1-report",
        action="store_true",
        default=False,
        help="Always write a Phase 1 report for the collected session results.",
    )

    phase2 = parser.getgroup("phase2")
    phase2.addoption(
        "--phase2-report-dir",
        action="store",
        default=str(PHASE2_REPORT_DIR),
        help="Directory for Phase 2 structured test reports (CSV/MD/JSON/API matrix).",
    )
    phase2.addoption(
        "--phase2-report",
        action="store_true",
        default=False,
        help="Always write a Phase 2 report for the collected session results.",
    )

    phase3 = parser.getgroup("phase3")
    phase3.addoption(
        "--phase3-report-dir",
        action="store",
        default=str(PHASE3_REPORT_DIR),
        help="Directory for Phase 3 structured test reports (CSV/MD/JSON/security matrix).",
    )
    phase3.addoption(
        "--phase3-report",
        action="store_true",
        default=False,
        help="Always write a Phase 3 report for the collected session results.",
    )


def pytest_configure(config: pytest.Config) -> None:
    for marker in (
        "cleaning: Phase 1 cleaning / normalization tests",
        "preprocessing: Phase 1 preprocessing tests",
        "transforming: Phase 1 field transform / schema mapping tests",
        "deduplication: Phase 1 duplicate detection tests",
        "disambiguation: Phase 1 author disambiguation tests",
        "entity_resolution: Phase 1 institution entity resolution tests",
        "e2e_ingestion: Phase 1 end-to-end ingestion pipeline tests",
        "dagster: Phase 1 Dagster asset/job smoke tests",
        "dagster_dev: Phase 1 Dagster dg/dev environment readiness tests",
        "database: Phase 1 database load contract tests",
        "phase1: Phase 1 ETL suite marker",
        "edge_case: Edge-case / adversarial input coverage",
        "phase2: Phase 2 DB integrity / ML / API suite marker",
        "database_integrity: Phase 2 database integrity tests",
        "classification: Phase 2 classification ML tests",
        "nmf_topic_modeling: Phase 2 NMF topic modeling tests",
        "semantic_search: Phase 2 semantic search tests",
        "api: Phase 2 API endpoint tests",
        "api_matrix: Phase 2 API matrix cases",
        "phase3: Phase 3 overall application suite marker",
        "frontend: Phase 3 frontend tests",
        "integration: Phase 3 integration tests",
        "performance: Phase 3 performance tests",
        "security: Phase 3 security tests",
        "load: Phase 3 load tests",
        "recovery: Phase 3 recovery tests",
        "accessibility: Phase 3 accessibility / error-contract tests",
        "deploy_config: Phase 3 deploy configuration tests",
        "deployed: Phase 3 live deployed-site smoke tests",
        "live: Live/staging/production HTTP tests",
    ):
        config.addinivalue_line("markers", marker)

    config._phase1_results = []  # type: ignore[attr-defined]
    config._phase2_results = []  # type: ignore[attr-defined]
    config._phase2_api_matrix = []  # type: ignore[attr-defined]
    config._phase3_results = []  # type: ignore[attr-defined]
    config._phase3_security_matrix = []  # type: ignore[attr-defined]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    # Record call outcomes, plus setup failures/skips (e.g. missing live BASE_URL).
    if report.when == "call":
        pass
    elif report.when == "setup" and report.outcome in {"failed", "skipped"}:
        pass
    else:
        return

    markers = sorted({marker.name for marker in item.iter_markers()})
    message = ""
    if report.failed or report.skipped:
        message = str(getattr(report, "longrepr", "") or "")

    is_phase1 = "phase1" in markers or "/phase1/" in item.nodeid.replace("\\", "/")
    is_phase2 = "phase2" in markers or "/phase2/" in item.nodeid.replace("\\", "/")
    is_phase3 = "phase3" in markers or "/phase3/" in item.nodeid.replace("\\", "/")

    if is_phase1:
        item.config._phase1_results.append(  # type: ignore[attr-defined]
            Phase1Row(
                test_id=item.name,
                nodeid=item.nodeid,
                category=infer_phase1_category(item),
                outcome=report.outcome,
                duration_seconds=float(getattr(report, "duration", 0.0) or 0.0),
                markers=",".join(markers),
                message=message.replace("\n", " ")[:2000],
                file=str(getattr(item, "path", "") or ""),
            )
        )

    if is_phase2:
        item.config._phase2_results.append(  # type: ignore[attr-defined]
            Phase2Row(
                test_id=item.name,
                nodeid=item.nodeid,
                category=infer_phase2_category(item),
                outcome=report.outcome,
                duration_seconds=float(getattr(report, "duration", 0.0) or 0.0),
                markers=",".join(markers),
                message=message.replace("\n", " ")[:2000],
                file=str(getattr(item, "path", "") or ""),
            )
        )

        case = getattr(item, "_phase2_api_case", None)
        if case is not None:
            result_label = {
                "passed": "PASS",
                "failed": "FAIL",
                "error": "ERROR",
                "skipped": "SKIP",
            }.get(report.outcome, report.outcome.upper())
            item.config._phase2_api_matrix.append(  # type: ignore[attr-defined]
                ApiMatrixRow(
                    test_id=case["test_id"],
                    endpoint=case["endpoint"],
                    scenario=case["scenario"],
                    expected=case["expected"],
                    result=result_label,
                    outcome=report.outcome,
                    message=message.replace("\n", " ")[:500],
                    duration_seconds=float(getattr(report, "duration", 0.0) or 0.0),
                )
            )

    if is_phase3:
        item.config._phase3_results.append(  # type: ignore[attr-defined]
            Phase3Row(
                test_id=item.name,
                nodeid=item.nodeid,
                category=infer_phase3_category(item),
                outcome=report.outcome,
                duration_seconds=float(getattr(report, "duration", 0.0) or 0.0),
                markers=",".join(markers),
                message=message.replace("\n", " ")[:2000],
                file=str(getattr(item, "path", "") or ""),
            )
        )

        case = getattr(item, "_phase3_security_case", None)
        if case is not None:
            result_label = {
                "passed": "PASS",
                "failed": "FAIL",
                "error": "ERROR",
                "skipped": "SKIP",
            }.get(report.outcome, report.outcome.upper())
            item.config._phase3_security_matrix.append(  # type: ignore[attr-defined]
                SecurityMatrixRow(
                    test_id=case["test_id"],
                    endpoint=case["endpoint"],
                    scenario=case["scenario"],
                    expected=case["expected"],
                    result=result_label,
                    outcome=report.outcome,
                    message=message.replace("\n", " ")[:500],
                    duration_seconds=float(getattr(report, "duration", 0.0) or 0.0),
                )
            )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    reporter = config.pluginmanager.get_plugin("terminalreporter")

    phase1_rows: list[Phase1Row] = getattr(config, "_phase1_results", [])
    write_phase1 = bool(config.getoption("--phase1-report"))
    auto_phase1 = any(
        "phase1" in row.markers or "/phase1/" in row.nodeid.replace("\\", "/")
        for row in phase1_rows
    )
    if phase1_rows and (write_phase1 or auto_phase1):
        paths = write_phase1_report(
            phase1_rows,
            report_dir=Path(config.getoption("--phase1-report-dir")),
        )
        if reporter is not None:
            reporter.write_sep("=", "Phase 1 ETL report written")
            for label, path in paths.items():
                reporter.write_line(f"{label}: {path}")

    phase2_rows: list[Phase2Row] = getattr(config, "_phase2_results", [])
    write_phase2 = bool(config.getoption("--phase2-report"))
    auto_phase2 = any(
        "phase2" in row.markers or "/phase2/" in row.nodeid.replace("\\", "/")
        for row in phase2_rows
    )
    if phase2_rows and (write_phase2 or auto_phase2):
        paths = write_phase2_report(
            phase2_rows,
            api_matrix=getattr(config, "_phase2_api_matrix", []),
            report_dir=Path(config.getoption("--phase2-report-dir")),
        )
        if reporter is not None:
            reporter.write_sep("=", "Phase 2 ML/API report written")
            for label, path in paths.items():
                reporter.write_line(f"{label}: {path}")

    phase3_rows: list[Phase3Row] = getattr(config, "_phase3_results", [])
    write_phase3 = bool(config.getoption("--phase3-report"))
    auto_phase3 = any(
        "phase3" in row.markers or "/phase3/" in row.nodeid.replace("\\", "/")
        for row in phase3_rows
    )
    if phase3_rows and (write_phase3 or auto_phase3):
        paths = write_phase3_report(
            phase3_rows,
            security_matrix=getattr(config, "_phase3_security_matrix", []),
            report_dir=Path(config.getoption("--phase3-report-dir")),
        )
        if reporter is not None:
            reporter.write_sep("=", "Phase 3 overall report written")
            for label, path in paths.items():
                reporter.write_line(f"{label}: {path}")
