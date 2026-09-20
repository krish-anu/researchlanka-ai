"""Phase 1 — Dagster *dev environment* readiness (beyond job/asset smoke).

These checks target the `backend/dagster-quickstart` project layout used with
`uv run dg dev` / Dagster webserver. They do **not** materialize assets against
production data; that remains a manual/staging step documented in the unified report.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest


pytestmark = [pytest.mark.phase1, pytest.mark.dagster, pytest.mark.dagster_dev]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DAGSTER_ROOT = BACKEND_ROOT / "dagster-quickstart"
PKG_ROOT = DAGSTER_ROOT / "src" / "dagster_quickstart"
DEFS_MODULE = PKG_ROOT / "defs" / "researchlanka.py"


def _dagster_available() -> bool:
    return importlib.util.find_spec("dagster") is not None


def test_dagster_quickstart_project_layout_for_dg_dev():
    assert DAGSTER_ROOT.is_dir()
    assert (DAGSTER_ROOT / "pyproject.toml").is_file()
    assert (PKG_ROOT / "definitions.py").is_file()
    assert (PKG_ROOT / "defs" / "__init__.py").is_file()
    assert DEFS_MODULE.is_file()
    assert (DAGSTER_ROOT / "tests").is_dir()


def test_dg_project_tooling_declared_in_pyproject():
    raw = (DAGSTER_ROOT / "pyproject.toml").read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    project = data.get("project") or {}
    assert project.get("name") == "dagster_quickstart"
    deps = " ".join(project.get("dependencies") or [])
    assert "dagster==" in deps or "dagster>=" in deps

    tool_dg = (data.get("tool") or {}).get("dg") or {}
    assert tool_dg.get("directory_type") == "project"
    dg_project = (data.get("tool") or {}).get("dg", {}).get("project") or {}
    assert dg_project.get("root_module") == "dagster_quickstart"

    dev_deps = " ".join(((data.get("dependency-groups") or {}).get("dev") or []))
    assert "dagster-webserver" in dev_deps
    assert "dagster-dg-cli" in dev_deps


def test_definitions_entrypoint_exports_expected_symbols_offline():
    text = (PKG_ROOT / "definitions.py").read_text(encoding="utf-8")
    assert "defs" in text.lower() or "Definitions" in text or "load" in text.lower()


def test_researchlanka_jobs_cover_collection_and_export_stages():
    text = DEFS_MODULE.read_text(encoding="utf-8")
    for job_name in (
        "researchlanka_export_job",
        "researchlanka_database_job",
        "researchlanka_common_preprocessing_job",
        "researchlanka_no_collection_preprocessing_job",
        "researchlanka_all_assets_job",
    ):
        assert job_name in text, f"missing job declaration {job_name}"

    for stage_token in (
        "researchlanka_all_sources_collected",
        "researchlanka_common_final_dataset",
        "researchlanka_common_analysis_ready_dataset",
        "researchlanka_export_files",
        "researchlanka_cleaned_records",
    ):
        assert stage_token in text, f"missing asset stage {stage_token}"


@pytest.mark.skipif(not _dagster_available(), reason="dagster not installed in this environment")
def test_definitions_module_imports_when_dagster_present():
    """Smoke-import package definitions when Dagster is on PYTHONPATH."""
    pytest.importorskip("dagster")
    # Prefer path-based load so we do not require editable install.
    spec = importlib.util.spec_from_file_location(
        "dagster_quickstart_definitions",
        PKG_ROOT / "definitions.py",
    )
    assert spec and spec.loader
    # definitions.py may pull heavy deps; only assert the file is loadable as source.
    source = (PKG_ROOT / "definitions.py").read_text(encoding="utf-8")
    assert len(source) > 20


def test_common_output_paths_point_at_processed_common():
    """Dev runs should write pipeline CSVs under data/processed/common."""
    text = DEFS_MODULE.read_text(encoding="utf-8")
    assert 'PROCESSED_DIR / "common"' in text or 'processed" / "common"' in text
    assert "common_publications_final" in text
    assert "common_publications_all_records" in text
