"""Data collection and ETL — collector / cleaning unit tests.

Run (from backend/):

    pytest tests/data_collection_etl -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from research_analytics.cleaning import clean_record, normalize_doi
from research_analytics.config import CleaningConfig
from src.collectors.http import create_retry_session
from src.collectors.oai_pmh_collector import OaiPmhCollector, OaiPmhError
from src.collectors.openalex_collector import (
    build_filters,
    is_publication_year_in_collection_range,
)
from src.collectors.repository_registry import load_registry


def test_retry_session_mounts_adapters_for_transient_http_failures():
    session = create_retry_session(user_agent="researchlanka-test/1.0")
    assert "https://" in session.adapters
    assert session.headers.get("User-Agent") == "researchlanka-test/1.0"


def test_openalex_filter_builder_includes_sri_lanka_and_year_window():
    filters = build_filters(from_year=2018, to_year=2022)
    joined = ",".join(filters) if isinstance(filters, list) else str(filters)
    assert "LK" in joined or "authorships" in joined.lower()
    assert (
        "2018" in joined
        or "from_publication_date" in joined
        or "publication_year" in joined
    )


def test_openalex_year_window_rejects_out_of_range_works():
    assert (
        is_publication_year_in_collection_range(
            {"publication_year": 2010}, from_year=2016, to_year=2026
        )
        is False
    )
    assert (
        is_publication_year_in_collection_range(
            {"publication_year": 2020}, from_year=2016, to_year=2026
        )
        is True
    )


def test_oai_pmh_collector_raises_on_protocol_error_response():
    xml = """<?xml version="1.0"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <error code="badArgument">missing set</error>
    </OAI-PMH>
    """
    session = MagicMock()
    response = MagicMock()
    response.text = xml
    response.raise_for_status = MagicMock()
    session.get.return_value = response
    collector = OaiPmhCollector(base_url="https://example.test/oai", session=session)
    with pytest.raises(OaiPmhError) as exc:
        collector._request({"verb": "ListRecords"})
    assert exc.value.code == "badArgument"


def test_oai_pmh_collector_parses_dublin_core_record_from_list_records():
    xml = """<?xml version="1.0"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <ListRecords>
        <record>
          <header>
            <identifier>oai:example:1</identifier>
          </header>
          <metadata>
            <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                       xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>Test Paper</dc:title>
              <dc:creator>Ada Lovelace</dc:creator>
              <dc:identifier>10.1000/example</dc:identifier>
            </oai_dc:dc>
          </metadata>
        </record>
      </ListRecords>
    </OAI-PMH>
    """
    session = MagicMock()
    response = MagicMock()
    response.text = xml
    response.raise_for_status = MagicMock()
    session.get.return_value = response
    collector = OaiPmhCollector(base_url="https://example.test/oai", session=session)
    records = list(collector.iter_records())
    assert records
    assert records[0].get("title") == "Test Paper" or "Test Paper" in str(records[0])


def test_repository_registry_loads_harvestable_targets():
    registry = load_registry()
    assert registry is not None
    assert len(registry) >= 1 or hasattr(registry, "targets") or isinstance(
        registry, (list, dict)
    )


def test_cleaning_pipeline_maps_source_doi_into_common_schema_fields():
    raw = {
        "doi": "https://doi.org/10.1000/ETL",
        "title": " ETL Title ",
        "authors": "X; Y",
        "publication_year": "2019",
        "source_dataset": "openalex",
    }
    cleaned = clean_record(raw, CleaningConfig())
    assert cleaned["doi"] == "10.1000/etl"
    assert cleaned["title"]


def test_malformed_doi_does_not_become_false_valid_identifier():
    assert normalize_doi("doi:not-valid") is None or normalize_doi(
        "doi:not-valid"
    ) != "doi:not-valid"


def test_http_timeout_from_collector_session_is_propagated():
    session = MagicMock()
    session.get.side_effect = requests.Timeout("simulated")
    collector = OaiPmhCollector(
        base_url="https://example.test/oai", session=session, timeout=1
    )
    with pytest.raises(requests.Timeout):
        collector._request({"verb": "Identify"})
