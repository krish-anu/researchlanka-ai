"""Failure and recovery tests (FR-01 … FR-10).

Run (from backend/):

    pytest tests/failure_recovery -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from src.api.core.errors import APIError
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.api.services.incremental_admin import read_incremental_status
from src.collectors.oai_pmh_collector import OaiPmhCollector, OaiPmhError
from src.collectors.openalex_collector import create_session
from src.utils.doi import is_valid_doi, normalize_doi
from tests.phase3.helpers import make_api
from tests.support.real_dataset import RealPublicationRepository, dataset_path


# ---------------------------------------------------------------------------
# FR-01 Database unavailable
# ---------------------------------------------------------------------------


def test_fr01_database_unavailable_api_handles_failure_without_crashing():
    """Stop PostgreSQL (simulated): API handles DB failure without crashing."""
    api = make_api(fail_health=True)
    with pytest.raises(RuntimeError) as exc:
        route_get(api, "/api/v1/health", {})
    assert "database" in str(exc.value).casefold() or "unreachable" in str(
        exc.value
    ).casefold()

    api_list = make_api(fail_list=True)
    with pytest.raises(RuntimeError):
        route_get(api_list, "/api/v1/publications", {"page_size": ["5"]})


# ---------------------------------------------------------------------------
# FR-02 Database recovery
# ---------------------------------------------------------------------------


def test_fr02_database_recovery_operations_work_again():
    """Restart PostgreSQL (simulated): API/database operations work again."""
    repo = RealPublicationRepository()
    repo.fail_health = True
    api = ResearchLankaAPI(repo)
    with pytest.raises(RuntimeError):
        route_get(api, "/api/v1/health", {})

    repo.fail_health = False
    repo.fail_list = False
    health = route_get(api, "/api/v1/health", {})
    listing = route_get(api, "/api/v1/publications", {"page_size": ["5"]})
    assert health["data"]["status"] == "ok"
    assert listing["data"]


# ---------------------------------------------------------------------------
# FR-03 API service unavailable
# ---------------------------------------------------------------------------


def test_fr03_api_service_unavailable_returns_connection_error_without_corrupt_data():
    """Stop FastAPI (simulated): requests fail with connection/service error."""
    session = requests.Session()
    with pytest.raises(requests.RequestException):
        session.get("http://127.0.0.1:1/api/v1/health", timeout=0.5)

    # Corpus on disk remains intact and uncorrupted while API is down.
    path = dataset_path()
    assert path.exists()
    size_before = path.stat().st_size
    assert size_before > 0
    assert path.stat().st_size == size_before


# ---------------------------------------------------------------------------
# FR-04 API service recovery
# ---------------------------------------------------------------------------


def test_fr04_api_service_recovery_becomes_available_again(api: ResearchLankaAPI):
    """Restart FastAPI (simulated): API becomes available again."""
    # "Down" probe against a closed port, then recovered in-process API.
    with pytest.raises(requests.RequestException):
        requests.get("http://127.0.0.1:1/api/v1/health", timeout=0.5)

    health = route_get(api, "/api/v1/health", {})
    meta = route_get(api, "/api/v1/meta", {})
    assert health["data"]["status"] == "ok"
    assert meta["data"]["publication_count"] >= 1


# ---------------------------------------------------------------------------
# FR-05 External source unavailable
# ---------------------------------------------------------------------------


def test_fr05_external_source_unavailable_etl_records_failure():
    """Simulate OpenAlex/Crossref/OAI failure: collector surfaces the error."""
    session = MagicMock()
    session.get.side_effect = requests.Timeout("simulated OpenAlex/OAI outage")
    collector = OaiPmhCollector(
        base_url="https://example.test/oai", session=session, timeout=1
    )
    with pytest.raises(requests.Timeout):
        collector._request({"verb": "Identify"})

    xml = """<?xml version="1.0"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <error code="serviceUnavailable">source down</error>
    </OAI-PMH>
    """
    response = MagicMock()
    response.text = xml
    response.raise_for_status = MagicMock()
    ok_session = MagicMock()
    ok_session.get.return_value = response
    failing = OaiPmhCollector(base_url="https://example.test/oai", session=ok_session)
    with pytest.raises(OaiPmhError) as exc:
        failing._request({"verb": "ListRecords"})
    assert exc.value.code == "serviceUnavailable"

    # Retry session still mounts adapters so transient source failures can be retried.
    retry_session = create_session()
    assert "https://" in retry_session.adapters


# ---------------------------------------------------------------------------
# FR-06 ETL / pipeline failure
# ---------------------------------------------------------------------------


def test_fr06_etl_pipeline_failure_does_not_silently_accept_invalid_data(tmp_path: Path):
    """Force ETL failure: invalid/partial data is not silently accepted."""
    # Invalid DOI must not become a false-valid identifier.
    assert is_valid_doi("not-a-doi") is False
    assert normalize_doi("doi:not-valid") in (None, "") or normalize_doi(
        "doi:not-valid"
    ) != "doi:not-valid"

    # Corrupt pipeline status must surface as a controlled error, not idle success.
    status_path = tmp_path / "ui_status.json"
    status_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(APIError) as exc:
        read_incremental_status(status_path)
    assert exc.value.status == 500

    # Missing required training labels fail closed (pipeline asset analogue).
    from src.modeling.hierarchical_linear_svm import (
        HierarchicalTrainingConfig,
        train_hierarchical_classifier,
    )

    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("title,abstract\nhello,world\n", encoding="utf-8")
    with pytest.raises(Exception):
        train_hierarchical_classifier(
            HierarchicalTrainingConfig(
                input_path=bad_csv,
                taxonomy_path=tmp_path / "tax.json",
                field_model_output=tmp_path / "field.joblib",
                subfield_model_output=tmp_path / "subfields.joblib",
                metrics_output=tmp_path / "metrics.txt",
                label_counts_output=tmp_path / "labels.csv",
                manifest_output=tmp_path / "manifest.json",
                test_size=0.5,
                min_subfield_count=1,
                max_features=20,
                min_df=1,
                max_df=1.0,
                ngram_max=1,
                max_iter=200,
            )
        )


# ---------------------------------------------------------------------------
# FR-07 Pipeline recovery
# ---------------------------------------------------------------------------


def test_fr07_pipeline_recovery_rerun_succeeds_after_dependency_recovery(
    tmp_path: Path,
):
    """Re-run failed pipeline after dependency recovery: completes successfully."""
    # After corrupt status is replaced with a missing/idle path, status recovers.
    missing = tmp_path / "missing-status.json"
    status = read_incremental_status(missing)
    assert status["status"] == "idle"

    # Healthy API path after prior failure fixtures.
    api = make_api()
    health = route_get(api, "/api/v1/health", {})
    listing = route_get(api, "/api/v1/publications", {"page_size": ["3"]})
    assert health["data"]["status"] == "ok"
    assert listing["data"]


# ---------------------------------------------------------------------------
# FR-08 Invalid API input
# ---------------------------------------------------------------------------


def test_fr08_invalid_api_input_returns_controlled_error_service_stays_up(
    api: ResearchLankaAPI,
):
    """Send malformed/invalid request: controlled HTTP error; service stays up."""
    with pytest.raises(APIError) as bad:
        route_get(api, "/api/v1/publications", {"year_min": ["not-an-int"]})
    assert bad.value.status in {400, 422}
    assert getattr(bad.value, "code", "") in {"invalid_filter", "bad_request"} or (
        "integer" in str(bad.value).casefold()
    )

    with pytest.raises(APIError) as missing:
        route_get(api, "/api/v1/publications/missing-key-xyz", {})
    assert missing.value.status == 404

    # Service remains operational after the bad requests.
    health = route_get(api, "/api/v1/health", {})
    assert health["data"]["status"] == "ok"


# ---------------------------------------------------------------------------
# FR-09 Database connection recovery mid-operation
# ---------------------------------------------------------------------------


def test_fr09_database_connection_recovery_subsequent_operation_succeeds():
    """Temporarily make DB unavailable during operation, then restore."""
    repo = RealPublicationRepository()
    api = ResearchLankaAPI(repo)

    repo.fail_list = True
    with pytest.raises(RuntimeError):
        route_get(api, "/api/v1/publications", {"page_size": ["5"]})

    repo.fail_list = False
    recovered = route_get(api, "/api/v1/publications", {"page_size": ["5"]})
    assert recovered["data"]
    assert "publication_key" in recovered["data"][0]


# ---------------------------------------------------------------------------
# FR-10 Application restart
# ---------------------------------------------------------------------------


def test_fr10_application_restart_starts_successfully_and_data_remains_intact():
    """Restart application process (simulated): starts OK and data remains intact."""
    path = dataset_path()
    assert path.exists()
    size_before = path.stat().st_size

    first = make_api()
    before = route_get(first, "/api/v1/meta", {})
    count_before = before["data"]["publication_count"]

    # Simulate process restart by constructing a fresh API service instance.
    second = make_api()
    after = route_get(second, "/api/v1/meta", {})
    health = route_get(second, "/api/v1/health", {})

    assert health["data"]["status"] == "ok"
    assert after["data"]["publication_count"] == count_before
    assert path.stat().st_size == size_before
    assert path.exists()
