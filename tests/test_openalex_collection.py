"""Tests for OpenAlex Sri Lanka collection using sample publication records.

The tests avoid live network calls and exercise the reusable collector plus the
Kaggle CLI wrapper through small OpenAlex-shaped fixtures.
"""

import argparse
import csv
import json
import logging
import sys
from datetime import date
from types import SimpleNamespace

import pytest

from scripts.collection import kaggle_collect_openalex_sri_lanka as openalex_script
from src.collectors import openalex_collector as openalex


def sample_work(country_code: str = "LK") -> dict:
    """Create a minimal OpenAlex-like work record for collector tests."""
    # This fixture intentionally includes nested optional fields so flattening
    # tests cover the analysis columns without calling the live OpenAlex API.
    return {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1234/example",
        "title": "Sample Sri Lankan Research Publication",
        "publication_year": 2024,
        "publication_date": "2024-01-15",
        "type": "article",
        "is_retracted": False,
        "cited_by_count": 7,
        "authorships": [
            {
                "author": {"display_name": "A. Researcher"},
                "raw_affiliation_strings": [
                    "Department of Public Health, University of Colombo, Sri Lanka",
                ],
                "countries": [country_code],
                "institutions": [
                    {
                        "display_name": "University of Colombo",
                        "country_code": country_code,
                    }
                ],
            },
            {
                "author": {"display_name": "B. Collaborator"},
                "raw_affiliation_strings": [
                    "Department of Epidemiology, Example University, United States",
                ],
                "countries": ["US"],
                "institutions": [
                    {
                        "display_name": "Example University",
                        "country_code": "US",
                    }
                ],
            },
        ],
        "primary_location": {
            "landing_page_url": "https://example.org/paper",
            "pdf_url": "https://example.org/paper.pdf",
            "license": "cc-by",
            "source": {
                "display_name": "Example Journal",
                "host_organization_name": "Example Publisher",
                "type": "journal",
                "issn_l": "1234-5678",
            },
        },
        "locations": [
            {
                "landing_page_url": "https://example.org/paper",
                "pdf_url": "https://example.org/paper.pdf",
                "license": "cc-by",
                "version": "publishedVersion",
                "source": {
                    "display_name": "Example Journal",
                    "type": "journal",
                },
            },
            {
                "landing_page_url": "https://repository.example.edu/paper",
                "pdf_url": "https://repository.example.edu/paper.pdf",
                "license": "cc-by",
                "version": "acceptedVersion",
                "source": {
                    "display_name": "Example Repository",
                    "type": "repository",
                },
            },
        ],
        "open_access": {"is_oa": True, "oa_status": "gold", "license": "cc-by"},
        "referenced_works_count": 3,
        "referenced_works": [
            "https://openalex.org/W1",
            "https://openalex.org/W2",
            "https://openalex.org/W3",
        ],
        "concepts": [
            {"display_name": "Medicine"},
            {"display_name": "Public health"},
        ],
        "topics": [
            {
                "display_name": "Dengue epidemiology",
                "field": {"display_name": "Medicine"},
                "subfield": {"display_name": "Epidemiology"},
                "domain": {"display_name": "Health Sciences"},
            },
            {"display_name": "Vector control"},
        ],
        "primary_topic": {
            "display_name": "Dengue epidemiology",
            "field": {"display_name": "Medicine"},
            "subfield": {"display_name": "Epidemiology"},
            "domain": {"display_name": "Health Sciences"},
        },
        "language": "en",
        "biblio": {
            "volume": "12",
            "issue": "3",
            "first_page": "45",
            "last_page": "59",
        },
    }


def test_has_sri_lankan_author_accepts_lk_authorship():
    """A work with an LK authorship should be treated as Sri Lankan-affiliated."""
    assert openalex.has_sri_lankan_author(sample_work("LK")) is True


def test_has_sri_lankan_author_rejects_non_lk_authorships():
    """A work with no LK authorship or institution should be rejected."""
    work = sample_work("IN")
    work["authorships"][1]["countries"] = ["GB"]
    work["authorships"][1]["institutions"][0]["country_code"] = "GB"

    assert openalex.has_sri_lankan_author(work) is False


def test_strict_sri_lanka_only_accepts_only_lk_country_codes():
    """Strict LK-only filtering should reject international collaborations."""
    lk_only_work = sample_work("LK")
    lk_only_work["authorships"] = [lk_only_work["authorships"][0]]

    collaborative_work = sample_work("LK")

    assert openalex.is_strict_sri_lanka_only(lk_only_work) is True
    assert openalex.is_strict_sri_lanka_only(collaborative_work) is False


def test_iter_sri_lankan_work_pages_supports_strict_lk_only(monkeypatch):
    """Strict page iteration should keep only records with country-code set LK."""
    lk_only_work = sample_work("LK")
    lk_only_work["id"] = "https://openalex.org/W-LK"
    lk_only_work["authorships"] = [lk_only_work["authorships"][0]]

    collaborative_work = sample_work("LK")
    collaborative_work["id"] = "https://openalex.org/W-COLLAB"

    def fake_fetch_works(**_kwargs):
        return {
            "results": [lk_only_work, collaborative_work],
            "meta": {"next_cursor": None},
        }

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "fetch_works", fake_fetch_works)

    pages = list(
        collector.iter_sri_lankan_work_pages(
            filters=[openalex.LK_AUTHORSHIP_FILTER],
            strict_lk_only=True,
        )
    )

    assert pages[0].works == [lk_only_work]
    assert pages[0].skipped_count == 1


def test_iter_sri_lankan_work_pages_requires_unique_openalex_ids(monkeypatch):
    """OpenAlex ID should behave as the required primary key for collected works."""
    first_work = sample_work("LK")
    first_work["id"] = "https://openalex.org/W1"
    duplicate_work = sample_work("LK")
    duplicate_work["id"] = "https://openalex.org/W1"
    missing_id_work = sample_work("LK")
    missing_id_work.pop("id")
    second_work = sample_work("LK")
    second_work["id"] = "https://openalex.org/W2"

    def fake_fetch_works(**_kwargs):
        return {
            "results": [first_work, duplicate_work, missing_id_work, second_work],
            "meta": {"next_cursor": None},
        }

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "fetch_works", fake_fetch_works)

    pages = list(
        collector.iter_sri_lankan_work_pages(filters=[openalex.LK_AUTHORSHIP_FILTER])
    )

    assert [work["id"] for work in pages[0].works] == [
        "https://openalex.org/W1",
        "https://openalex.org/W2",
    ]
    assert pages[0].skipped_count == 2


def test_work_to_row_flattens_expected_openalex_fields():
    """Sample OpenAlex records should produce the expected flat CSV fields."""
    row = openalex.work_to_row(sample_work("LK"))

    assert row["openalex_id"] == "https://openalex.org/W123"
    assert row["doi"] == "10.1234/example"
    assert row["title"] == "Sample Sri Lankan Research Publication"
    assert row["publication_year"] == 2024
    assert row["author_count"] == 2
    assert row["authors"] == "A. Researcher; B. Collaborator"
    assert row["sri_lankan_authors"] == "A. Researcher"
    assert row["institutions"] == "University of Colombo; Example University"
    assert row["sri_lankan_institutions"] == "University of Colombo"
    assert (
        row["raw_affiliation_strings"]
        == "Department of Public Health, University of Colombo, Sri Lanka; "
        "Department of Epidemiology, Example University, United States"
    )
    assert (
        row["sri_lankan_raw_affiliation_strings"]
        == "Department of Public Health, University of Colombo, Sri Lanka"
    )
    assert row["countries"] == "LK; US"
    assert row["source_name"] == "Example Journal"
    assert row["publisher"] == "Example Publisher"
    assert row["is_retracted"] is False
    assert row["is_oa"] is True
    assert row["landing_page_url"] == "https://example.org/paper"
    assert row["pdf_url"] == "https://example.org/paper.pdf"
    assert row["locations_count"] == 2
    assert (
        row["location_landing_page_urls"]
        == "https://example.org/paper; https://repository.example.edu/paper"
    )
    assert (
        row["location_pdf_urls"]
        == "https://example.org/paper.pdf; https://repository.example.edu/paper.pdf"
    )
    assert row["location_source_names"] == "Example Journal; Example Repository"
    assert row["location_source_types"] == "journal; repository"
    assert row["location_licenses"] == "cc-by"
    assert row["location_versions"] == "publishedVersion; acceptedVersion"
    assert row["referenced_works_count"] == 3
    assert row["concepts"] == "Medicine; Public health"
    assert row["topics"] == "Dengue epidemiology; Vector control"
    assert row["primary_topic"] == "Dengue epidemiology"
    assert row["primary_field"] == "Medicine"
    assert row["primary_subfield"] == "Epidemiology"
    assert row["primary_domain"] == "Health Sciences"
    assert row["language"] == "en"
    assert row["oa_status"] == "gold"
    assert row["license"] == "cc-by"
    assert row["source_type"] == "journal"
    assert row["issn_l"] == "1234-5678"
    assert row["volume"] == "12"
    assert row["issue"] == "3"
    assert row["first_page"] == "45"
    assert row["last_page"] == "59"


def test_work_to_row_normalizes_mixed_case_doi_urls():
    """Flat OpenAlex rows should use DOI keys without URL prefixes."""
    work = sample_work("LK")
    work["doi"] = "HTTPS://DOI.ORG/10.1234/Example.Article"

    row = openalex.work_to_row(work)

    assert row["doi"] == "10.1234/example.article"


def test_work_to_row_flags_retracted_works():
    """OpenAlex retraction status should be available in the flat CSV row."""
    work = sample_work("LK")
    work["is_retracted"] = True

    row = openalex.work_to_row(work)

    assert row["is_retracted"] is True


def test_work_to_row_defaults_missing_retraction_status_to_false():
    """Missing or null OpenAlex retraction status should become a clear flag."""
    work = sample_work("LK")
    work["is_retracted"] = None

    row = openalex.work_to_row(work)

    assert row["is_retracted"] is False


def test_work_to_row_normalizes_publication_year_and_date():
    """Flat rows should keep publication year as int and date as ISO date."""
    work = sample_work("LK")
    work["publication_year"] = "2024"
    work["publication_date"] = "2024-01-15"

    row = openalex.work_to_row(work)

    assert row["publication_year"] == 2024
    assert isinstance(row["publication_year"], int)
    assert row["publication_date"] == "2024-01-15"


def test_work_to_row_blanks_invalid_publication_year_and_date():
    """Invalid year/date values should not leak into clean flat rows."""
    work = sample_work("LK")
    work["publication_year"] = "not-a-year"
    work["publication_date"] = "2024-99-99"

    row = openalex.work_to_row(work)

    assert row["publication_year"] is None
    assert row["publication_date"] is None


def test_csv_columns_include_extra_flattened_analysis_fields():
    """The flat CSV schema should expose fields used by analysis notebooks."""
    expected_columns = {
        "referenced_works_count",
        "concepts",
        "topics",
        "primary_topic",
        "primary_field",
        "primary_subfield",
        "primary_domain",
        "language",
        "is_retracted",
        "raw_affiliation_strings",
        "sri_lankan_raw_affiliation_strings",
        "locations_count",
        "location_landing_page_urls",
        "location_pdf_urls",
        "location_source_names",
        "location_source_types",
        "location_licenses",
        "location_versions",
        "oa_status",
        "license",
        "source_type",
        "issn_l",
        "volume",
        "issue",
        "first_page",
        "last_page",
    }

    assert expected_columns.issubset(openalex.CSV_COLUMNS)


def test_build_filters_adds_publication_year_range():
    """Year arguments should be converted into an OpenAlex publication-year filter."""
    assert openalex.build_filters(
        [openalex.LK_AUTHORSHIP_FILTER],
        from_year=2020,
        to_year=2024,
    ) == [
        openalex.LK_AUTHORSHIP_FILTER,
        "publication_year:2020-2024",
    ]


def test_build_filters_defaults_to_2016_2026_year_range():
    """Default collection should cover publication years 2016 through 2026."""
    assert openalex.build_filters([openalex.LK_AUTHORSHIP_FILTER]) == [
        openalex.LK_AUTHORSHIP_FILTER,
        "publication_year:2016-2026",
    ]


def test_create_session_retries_transient_openalex_errors():
    """OpenAlex requests should retry rate limits and temporary server failures."""
    session = openalex.create_session()
    retries = session.adapters["https://"].max_retries

    assert retries.total == 5
    assert retries.backoff_factor == 2
    assert retries.respect_retry_after_header is True
    assert set(retries.status_forcelist) == {429, 500, 502, 503, 504}
    assert set(retries.allowed_methods) == {"GET"}


def test_collector_fetch_works_sends_openalex_request_metadata():
    """Collector requests should include filters, pagination, email, and API key."""
    calls = []

    class FakeResponse:
        ok = True
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    class FakeSession:
        def get(self, url, *, params, timeout):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeResponse()

    collector = openalex.OpenAlexCollector(
        email="tester@example.com",
        api_key="test-key",
        session=FakeSession(),
    )

    assert collector.fetch_works(
        filters=[openalex.LK_AUTHORSHIP_FILTER],
        cursor="*",
        per_page=25,
    ) == {"results": []}
    assert calls == [
        {
            "url": f"{openalex.OPENALEX_BASE_URL}/works",
            "params": {
                "filter": openalex.LK_AUTHORSHIP_FILTER,
                "cursor": "*",
                "per-page": 25,
                "mailto": "tester@example.com",
                "api_key": "test-key",
            },
            "timeout": 60,
        }
    ]


def test_iter_sri_lankan_works_uses_sample_records_without_network(monkeypatch):
    """The collector should keep only LK-affiliated works from sample API pages."""
    lk_work = sample_work("LK")
    non_lk_work = sample_work("IN")
    calls = []

    def fake_fetch_works(**kwargs):
        calls.append(kwargs)
        return {
            "results": [lk_work, non_lk_work],
            "meta": {"next_cursor": None},
        }

    collector = openalex.OpenAlexCollector(email="tester@example.com")
    monkeypatch.setattr(collector, "fetch_works", fake_fetch_works)

    args = argparse.Namespace(
        filter=[openalex.LK_AUTHORSHIP_FILTER],
        from_year=openalex.DEFAULT_FROM_YEAR,
        to_year=openalex.DEFAULT_TO_YEAR,
        per_page=25,
        max_records=None,
        email="tester@example.com",
        api_key=None,
        strict_lk_only=False,
    )

    works = list(
        collector.iter_sri_lankan_works(
            filters=args.filter,
            from_year=args.from_year,
            to_year=args.to_year,
            per_page=args.per_page,
            max_records=args.max_records,
        )
    )

    assert works == [lk_work]
    assert calls == [
        {
            "filters": [
                openalex.LK_AUTHORSHIP_FILTER,
                "publication_year:2016-2026",
            ],
            "cursor": "*",
            "per_page": 25,
        }
    ]


def test_collector_logs_page_fetch_summary(monkeypatch, caplog):
    """Collector page iteration should log page-level progress information."""
    lk_work = sample_work("LK")
    non_lk_work = sample_work("IN")

    def fake_fetch_works(**_kwargs):
        return {
            "results": [lk_work, non_lk_work],
            "meta": {"next_cursor": None},
        }

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "fetch_works", fake_fetch_works)
    caplog.set_level(logging.INFO, logger=openalex.__name__)

    list(collector.iter_sri_lankan_work_pages(filters=[openalex.LK_AUTHORSHIP_FILTER]))

    assert "Starting OpenAlex page iteration" in caplog.text
    assert "Fetched OpenAlex page" in caplog.text
    assert "kept=1" in caplog.text
    assert "skipped=1" in caplog.text


def test_iter_sri_lankan_work_pages_can_start_from_saved_cursor(monkeypatch):
    """Page iteration should support resuming from a saved OpenAlex cursor."""
    calls = []

    def fake_fetch_works(**kwargs):
        calls.append(kwargs)
        return {
            "results": [sample_work("LK")],
            "meta": {"next_cursor": None},
        }

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "fetch_works", fake_fetch_works)

    pages = list(
        collector.iter_sri_lankan_work_pages(
            filters=[openalex.LK_AUTHORSHIP_FILTER],
            per_page=25,
            start_cursor="saved-cursor",
        )
    )

    assert len(pages) == 1
    assert pages[0].cursor == "saved-cursor"
    assert pages[0].next_cursor is None
    assert pages[0].works == [sample_work("LK")]
    assert calls == [
        {
            "filters": [
                openalex.LK_AUTHORSHIP_FILTER,
                "publication_year:2016-2026",
            ],
            "cursor": "saved-cursor",
            "per_page": 25,
        }
    ]


def test_iter_sri_lankan_work_pages_reports_pagination_progress(monkeypatch):
    """Page objects should expose count-based progress details for audit files."""
    first_work = sample_work("LK")
    first_work["id"] = "https://openalex.org/W1"
    second_work = sample_work("LK")
    second_work["id"] = "https://openalex.org/W2"
    responses = [
        {
            "results": [first_work],
            "meta": {
                "next_cursor": "cursor-2",
                "count": 4,
                "db_response_time_ms": 15,
            },
        },
        {
            "results": [second_work],
            "meta": {
                "next_cursor": None,
                "count": 4,
                "db_response_time_ms": 18,
            },
        },
    ]

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "fetch_works", lambda **_kwargs: responses.pop(0))

    pages = list(
        collector.iter_sri_lankan_work_pages(
            filters=[openalex.LK_AUTHORSHIP_FILTER],
            per_page=2,
        )
    )

    assert [page.page_number for page in pages] == [1, 2]
    assert [page.fetched_count for page in pages] == [1, 1]
    assert pages[0].api_total_count == 4
    assert pages[0].estimated_total_pages == 2
    assert pages[0].progress_percent == 50.0
    assert pages[1].progress_percent == 100.0
    assert pages[0].db_response_time_ms == 15


def test_iter_sri_lankan_work_pages_rejects_repeated_cursor(monkeypatch):
    """Pagination should fail loudly if OpenAlex returns a stuck cursor."""
    def fake_fetch_works(**kwargs):
        return {
            "results": [sample_work("LK")],
            "meta": {"next_cursor": kwargs["cursor"]},
        }

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "fetch_works", fake_fetch_works)

    with pytest.raises(RuntimeError, match="did not advance"):
        list(collector.iter_sri_lankan_work_pages(filters=[openalex.LK_AUTHORSHIP_FILTER]))


def test_kaggle_script_resume_appends_without_duplicate_ids(tmp_path, monkeypatch):
    """Resume should append new records and skip records already in the JSONL."""
    existing_work = sample_work("LK")
    existing_work["id"] = "https://openalex.org/W1"
    new_work = sample_work("LK")
    new_work["id"] = "https://openalex.org/W2"
    new_work["doi"] = "https://doi.org/10.1234/new"

    jsonl_output = tmp_path / "works.jsonl"
    csv_output = tmp_path / "works.csv"
    progress_output = tmp_path / "works_progress.json"
    doi_conflicts_output = tmp_path / "doi_conflicts.csv"
    parquet_output = tmp_path / "works.parquet"
    pagination_output = tmp_path / "pagination_audit.json"

    jsonl_output.write_text(json.dumps(existing_work) + "\n", encoding="utf-8")
    openalex_script.save_progress(
        progress_output,
        next_cursor="saved-cursor",
        records_saved=0,
        filters=[openalex.LK_AUTHORSHIP_FILTER, "publication_year:2016-2026"],
    )

    class FakeCollector:
        def __init__(self, *, email, api_key):
            self.email = email
            self.api_key = api_key

        def iter_sri_lankan_work_pages(self, **kwargs):
            assert kwargs["start_cursor"] == "saved-cursor"
            yield openalex.OpenAlexWorkPage(
                cursor="saved-cursor",
                next_cursor=None,
                filters=[openalex.LK_AUTHORSHIP_FILTER],
                works=[existing_work, new_work],
            )

    args = argparse.Namespace(
        jsonl_output=jsonl_output,
        csv_output=csv_output,
        parquet_output=parquet_output,
        doi_conflicts_output=doi_conflicts_output,
        pagination_output=pagination_output,
        no_csv=False,
        no_parquet=True,
        resume=True,
        progress_output=progress_output,
        filter=[openalex.LK_AUTHORSHIP_FILTER],
        from_year=openalex.DEFAULT_FROM_YEAR,
        to_year=openalex.DEFAULT_TO_YEAR,
        per_page=25,
        max_records=None,
        email="tester@example.com",
        api_key=None,
        strict_lk_only=False,
    )

    monkeypatch.setattr(openalex_script, "parse_args", lambda: args)
    monkeypatch.setattr(openalex_script, "OpenAlexCollector", FakeCollector)

    openalex_script.main()

    jsonl_records = [
        json.loads(line)
        for line in jsonl_output.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["id"] for record in jsonl_records] == [
        "https://openalex.org/W1",
        "https://openalex.org/W2",
    ]

    with csv_output.open("r", encoding="utf-8", newline="") as csv_file:
        csv_rows = list(csv.DictReader(csv_file))
    assert [row["openalex_id"] for row in csv_rows] == [
        "https://openalex.org/W1",
        "https://openalex.org/W2",
    ]
    with doi_conflicts_output.open("r", encoding="utf-8", newline="") as csv_file:
        assert list(csv.DictReader(csv_file)) == []

    progress = openalex_script.load_progress(progress_output)
    assert progress == {
        "next_cursor": None,
        "records_saved": 2,
        "filters": [openalex.LK_AUTHORSHIP_FILTER, "publication_year:2016-2026"],
        "strict_lk_only": False,
    }
    pagination_audit = json.loads(pagination_output.read_text(encoding="utf-8"))
    assert pagination_audit["status"] == "complete"
    assert pagination_audit["pages_fetched"] == 1
    assert pagination_audit["records_saved"] == 2
    assert pagination_audit["pages"][0]["cursor"] == "saved-cursor"
    assert pagination_audit["pages"][0]["kept_count"] == 2


def test_kaggle_script_writes_initial_resume_metadata(tmp_path, monkeypatch):
    """Fresh runs should create progress metadata before page collection starts."""
    jsonl_output = tmp_path / "works.jsonl"
    csv_output = tmp_path / "works.csv"
    progress_output = tmp_path / "works_progress.json"
    doi_conflicts_output = tmp_path / "doi_conflicts.csv"
    parquet_output = tmp_path / "works.parquet"
    pagination_output = tmp_path / "pagination_audit.json"

    class FakeCollector:
        def __init__(self, *, email, api_key):
            self.email = email
            self.api_key = api_key

        def iter_sri_lankan_work_pages(self, **kwargs):
            assert kwargs["strict_lk_only"] is True
            return
            yield

    args = argparse.Namespace(
        jsonl_output=jsonl_output,
        csv_output=csv_output,
        parquet_output=parquet_output,
        doi_conflicts_output=doi_conflicts_output,
        pagination_output=pagination_output,
        no_csv=True,
        no_parquet=True,
        resume=False,
        progress_output=progress_output,
        filter=[openalex.LK_AUTHORSHIP_FILTER],
        from_year=openalex.DEFAULT_FROM_YEAR,
        to_year=openalex.DEFAULT_TO_YEAR,
        per_page=25,
        max_records=None,
        email=None,
        api_key=None,
        strict_lk_only=True,
    )

    monkeypatch.setattr(openalex_script, "parse_args", lambda: args)
    monkeypatch.setattr(openalex_script, "OpenAlexCollector", FakeCollector)

    openalex_script.main()

    assert openalex_script.load_progress(progress_output) == {
        "next_cursor": "*",
        "records_saved": 0,
        "filters": [openalex.LK_AUTHORSHIP_FILTER, "publication_year:2016-2026"],
        "strict_lk_only": True,
    }
    with doi_conflicts_output.open("r", encoding="utf-8", newline="") as csv_file:
        assert list(csv.DictReader(csv_file)) == []
    pagination_audit = json.loads(pagination_output.read_text(encoding="utf-8"))
    assert pagination_audit["status"] == "partial"
    assert pagination_audit["pages_fetched"] == 0
    assert pagination_audit["next_cursor"] == "*"


def test_write_pagination_audit_report_outputs_page_details(tmp_path):
    """Pagination audit JSON should keep page-level monitoring details."""
    audit_output = tmp_path / "pagination.json"
    pages = [
        {
            "page_number": 1,
            "run_page_number": 1,
            "cursor": "*",
            "next_cursor": "cursor-2",
            "fetched_count": 200,
            "kept_count": 180,
            "skipped_count": 20,
            "records_saved_total": 180,
            "records_skipped_total": 20,
            "api_total_count": 400,
            "estimated_total_pages": 2,
            "progress_percent": 50.0,
            "db_response_time_ms": 12,
            "filters": [openalex.LK_AUTHORSHIP_FILTER],
        }
    ]

    openalex_script.write_pagination_audit_report(
        audit_output,
        pages=pages,
        filters=[openalex.LK_AUTHORSHIP_FILTER],
        strict_lk_only=False,
        records_saved=180,
        records_skipped=20,
        next_cursor="cursor-2",
        status="partial",
    )

    audit = json.loads(audit_output.read_text(encoding="utf-8"))
    assert audit["status"] == "partial"
    assert audit["pages_fetched"] == 1
    assert audit["records_saved"] == 180
    assert audit["api_total_count"] == 400
    assert audit["estimated_total_pages"] == 2
    assert audit["progress_percent"] == 50.0
    assert audit["pages"] == pages


def test_default_output_dir_supports_environment_override(tmp_path, monkeypatch):
    """Local users can override the default output directory without Kaggle paths."""
    monkeypatch.setenv("OPENALEX_OUTPUT_DIR", str(tmp_path))

    assert openalex_script.default_output_dir() == tmp_path


def test_default_progress_output_uses_dataset_filename_shape(tmp_path):
    """Default progress metadata should keep lower snake-case dataset naming."""
    jsonl_output = tmp_path / "openalex_sri_lanka_works.jsonl"

    assert (
        openalex_script.default_progress_output(jsonl_output)
        == tmp_path / "openalex_sri_lanka_works_progress.json"
    )


def test_setup_logging_can_write_to_log_file(tmp_path):
    """CLI logging should support mirroring logs to a file."""
    log_file = tmp_path / "openalex_sri_lanka_collection.log"
    openalex_script.setup_logging("INFO", log_file)

    logging.getLogger("openalex-test").info("hello logging")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "hello logging" in log_file.read_text(encoding="utf-8")


def test_collect_quality_report_summarizes_saved_jsonl(tmp_path):
    """The collection report should summarize the final JSONL dataset."""
    first_work = sample_work("LK")
    first_work["id"] = "https://openalex.org/W1"
    first_work["doi"] = "https://doi.org/10.1234/duplicate"
    first_work["publication_year"] = 2022

    duplicate_work = sample_work("LK")
    duplicate_work["id"] = "https://openalex.org/W1"
    duplicate_work["doi"] = "https://doi.org/10.1234/DUPLICATE"
    duplicate_work["publication_year"] = 2024
    duplicate_work["is_retracted"] = True

    conflict_work = sample_work("LK")
    conflict_work["id"] = "https://openalex.org/W4"
    conflict_work["doi"] = "10.1234/duplicate"
    conflict_work["title"] = "Different OpenAlex Record With Same DOI"
    conflict_work["publication_year"] = 2025

    missing_work = sample_work("LK")
    missing_work["id"] = "https://openalex.org/W3"
    missing_work["doi"] = None
    missing_work["title"] = None
    missing_work.pop("display_name", None)
    missing_work["publication_year"] = None

    jsonl_output = tmp_path / "works.jsonl"
    jsonl_output.write_text(
        "\n".join(
            [
                json.dumps(first_work),
                json.dumps(duplicate_work),
                json.dumps(conflict_work),
                json.dumps(missing_work),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert openalex_script.collect_quality_report(
        jsonl_output,
        records_skipped=5,
    ) == {
        "total_saved": 4,
        "records_skipped": 5,
        "missing_doi_count": 1,
        "missing_title_count": 1,
        "retracted_record_count": 1,
        "doi_conflict_count": 1,
        "duplicate_openalex_ids": 1,
        "duplicate_doi_count": 1,
        "year_range": "2022-2025",
        "countries_found": ["LK", "US"],
    }


def test_write_doi_conflict_report_outputs_different_ids_for_same_doi(tmp_path):
    """DOI conflicts should be exported separately from the main works dataset."""
    first_work = sample_work("LK")
    first_work["id"] = "https://openalex.org/W1"
    first_work["doi"] = "https://doi.org/10.1234/conflict"
    first_work["title"] = "First DOI Record"

    second_work = sample_work("LK")
    second_work["id"] = "https://openalex.org/W2"
    second_work["doi"] = "10.1234/CONFLICT"
    second_work["title"] = "Second DOI Record"

    same_id_duplicate = sample_work("LK")
    same_id_duplicate["id"] = "https://openalex.org/W1"
    same_id_duplicate["doi"] = "10.1234/conflict"

    jsonl_output = tmp_path / "works.jsonl"
    conflict_output = tmp_path / "doi_conflicts.csv"
    jsonl_output.write_text(
        "\n".join(
            [
                json.dumps(first_work),
                json.dumps(second_work),
                json.dumps(same_id_duplicate),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert openalex_script.write_doi_conflict_report(
        jsonl_output,
        conflict_output,
    ) == 1

    with conflict_output.open("r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert rows == [
        {
            "doi": "10.1234/conflict",
            "openalex_id_count": "2",
            "record_count": "3",
            "openalex_ids": "https://openalex.org/W1; https://openalex.org/W2",
            "titles": "First DOI Record; Second DOI Record; Sample Sri Lankan Research Publication",
            "publication_years": "2024",
        }
    ]


def test_extract_openalex_dois_returns_unique_normalized_values(tmp_path):
    jsonl_output = tmp_path / "works.jsonl"
    jsonl_output.write_text(
        "\n".join(
            [
                json.dumps({"doi": "https://doi.org/10.1234/Example"}),
                json.dumps({"doi": "10.1234/example"}),
                json.dumps({"doi": None}),
                "not-json",
                json.dumps({"doi": "DOI: 10.5678/Other"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert openalex_script.extract_openalex_dois(jsonl_output) == [
        "10.1234/example",
        "10.5678/other",
    ]


def test_enrich_crossref_from_openalex_skips_existing_and_writes_found(tmp_path):
    openalex_jsonl = tmp_path / "openalex.jsonl"
    crossref_output = tmp_path / "crossref_enriched.jsonl"
    openalex_jsonl.write_text(
        "\n".join(
            [
                json.dumps({"doi": "10.1234/existing"}),
                json.dumps({"doi": "https://doi.org/10.1234/found"}),
                json.dumps({"doi": "10.1234/missing"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    crossref_output.write_text(
        json.dumps({"DOI": "10.1234/existing"}) + "\n",
        encoding="utf-8",
    )
    calls = []

    class FakeCrossrefCollector:
        def fetch_work_by_doi(self, doi):
            calls.append(doi)
            if doi == "10.1234/missing":
                return None
            return {
                "DOI": doi,
                "type": "journal-article",
                "title": ["Found Crossref Work"],
            }

    report = openalex_script.enrich_crossref_from_openalex(
        openalex_jsonl=openalex_jsonl,
        crossref_output=crossref_output,
        collector=FakeCrossrefCollector(),
        delay=0,
    )

    assert calls == ["10.1234/found", "10.1234/missing"]
    assert report == {
        "total_openalex_dois": 3,
        "skipped_existing": 1,
        "looked_up": 2,
        "found": 1,
        "missing": 1,
        "normalization_failed": 0,
        "output": str(crossref_output),
    }
    records = [
        json.loads(line)
        for line in crossref_output.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["DOI"] for record in records] == [
        "10.1234/existing",
        "10.1234/found",
    ]


def test_kaggle_script_runs_crossref_enrichment_when_enabled(tmp_path, monkeypatch):
    jsonl_output = tmp_path / "works.jsonl"
    csv_output = tmp_path / "works.csv"
    progress_output = tmp_path / "works_progress.json"
    doi_conflicts_output = tmp_path / "doi_conflicts.csv"
    parquet_output = tmp_path / "works.parquet"
    pagination_output = tmp_path / "pagination_audit.json"
    crossref_output = tmp_path / "crossref_enriched.jsonl"
    enrichment_calls = []

    class FakeCollector:
        def __init__(self, *, email, api_key):
            self.email = email
            self.api_key = api_key

        def iter_sri_lankan_work_pages(self, **kwargs):
            yield openalex.OpenAlexWorkPage(
                cursor="*",
                next_cursor=None,
                filters=[openalex.LK_AUTHORSHIP_FILTER],
                works=[sample_work("LK")],
            )

    def fake_enrich_crossref_from_openalex(**kwargs):
        enrichment_calls.append(kwargs)
        return {
            "total_openalex_dois": 1,
            "skipped_existing": 0,
            "looked_up": 1,
            "found": 1,
            "missing": 0,
            "normalization_failed": 0,
            "output": str(kwargs["crossref_output"]),
        }

    args = argparse.Namespace(
        jsonl_output=jsonl_output,
        csv_output=csv_output,
        parquet_output=parquet_output,
        doi_conflicts_output=doi_conflicts_output,
        pagination_output=pagination_output,
        no_csv=True,
        no_parquet=True,
        resume=False,
        progress_output=progress_output,
        filter=[openalex.LK_AUTHORSHIP_FILTER],
        from_year=openalex.DEFAULT_FROM_YEAR,
        to_year=openalex.DEFAULT_TO_YEAR,
        per_page=25,
        max_records=None,
        email="openalex@example.com",
        api_key=None,
        strict_lk_only=False,
        enrich_crossref=True,
        crossref_output=crossref_output,
        crossref_email="crossref@example.com",
        crossref_delay=0,
    )

    monkeypatch.setattr(openalex_script, "parse_args", lambda: args)
    monkeypatch.setattr(openalex_script, "OpenAlexCollector", FakeCollector)
    monkeypatch.setattr(
        openalex_script,
        "enrich_crossref_from_openalex",
        fake_enrich_crossref_from_openalex,
    )

    openalex_script.main()

    assert len(enrichment_calls) == 1
    assert enrichment_calls[0]["openalex_jsonl"] == jsonl_output
    assert enrichment_calls[0]["crossref_output"] == crossref_output
    assert enrichment_calls[0]["email"] == "crossref@example.com"
    assert enrichment_calls[0]["delay"] == 0


def test_write_parquet_from_jsonl_writes_flat_rows(tmp_path, monkeypatch):
    """Parquet export should write the same flattened rows as the CSV path."""
    work = sample_work("LK")
    jsonl_output = tmp_path / "works.jsonl"
    parquet_output = tmp_path / "works.parquet"
    jsonl_output.write_text(json.dumps(work) + "\n", encoding="utf-8")
    calls = []

    class FakeDataFrame:
        def __init__(self, rows, columns):
            self.rows = rows
            self.columns = columns

        def __len__(self):
            return len(self.rows)

        def to_parquet(self, path, *, index):
            calls.append(
                {
                    "path": path,
                    "index": index,
                    "rows": self.rows,
                    "columns": self.columns,
                }
            )

    fake_pandas = SimpleNamespace(DataFrame=FakeDataFrame)
    monkeypatch.setitem(sys.modules, "pandas", fake_pandas)

    assert openalex_script.write_parquet_from_jsonl(
        jsonl_output,
        parquet_output,
    ) == 1

    assert calls[0]["path"] == parquet_output
    assert calls[0]["index"] is False
    assert calls[0]["columns"] == openalex.CSV_COLUMNS
    assert calls[0]["rows"][0]["openalex_id"] == "https://openalex.org/W123"
    assert calls[0]["rows"][0]["doi"] == "10.1234/example"
    assert calls[0]["rows"][0]["publication_date"] == date(2024, 1, 15)
