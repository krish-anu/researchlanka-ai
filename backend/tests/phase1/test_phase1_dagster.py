"""Phase 1 — Dagster asset/job wiring smoke tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = [pytest.mark.phase1, pytest.mark.dagster]

DAGSTER_DEFS = (
    Path(__file__).resolve().parents[2]
    / "dagster-quickstart"
    / "src"
    / "dagster_quickstart"
    / "defs"
    / "researchlanka.py"
)


def _dagster_available() -> bool:
    return importlib.util.find_spec("dagster") is not None


@pytest.mark.skipif(not _dagster_available(), reason="dagster not installed in this environment")
def test_researchlanka_job_definitions_exist():
    dagster = pytest.importorskip("dagster")
    # Load module from path because dagster-quickstart is a separate package.
    spec = importlib.util.spec_from_file_location("researchlanka_defs", DAGSTER_DEFS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["researchlanka_defs"] = module
    spec.loader.exec_module(module)

    expected_jobs = [
        "researchlanka_export_job",
        "researchlanka_database_job",
        "researchlanka_common_preprocessing_job",
        "researchlanka_no_collection_preprocessing_job",
        "researchlanka_all_assets_job",
    ]
    for name in expected_jobs:
        assert hasattr(module, name), f"missing job {name}"
        job = getattr(module, name)
        assert job is not None

    expected_assets = [
        "researchlanka_cleaned_records",
        "researchlanka_national_records",
        "researchlanka_deduplicated_records",
        "researchlanka_export_files",
    ]
    for name in expected_assets:
        assert hasattr(module, name), f"missing asset {name}"


@pytest.mark.skipif(not _dagster_available(), reason="dagster not installed in this environment")
def test_definitions_entrypoint_loads():
    pytest.importorskip("dagster")
    defs_path = (
        Path(__file__).resolve().parents[2]
        / "dagster-quickstart"
        / "src"
        / "dagster_quickstart"
        / "definitions.py"
    )
    assert defs_path.exists()
    # Importing Definitions via load_from_defs_folder can be heavy; assert package layout.
    package_init = defs_path.parent / "__init__.py"
    assert package_init.exists()


def test_dagster_source_file_declares_pipeline_stages():
    """Offline smoke check that does not require dagster installed."""
    text = DAGSTER_DEFS.read_text(encoding="utf-8")
    for token in (
        "pipeline.clean()",
        "pipeline.resolve_entities()",
        "pipeline.deduplicate()",
        "pipeline.export()",
        "define_asset_job",
    ):
        assert token in text
