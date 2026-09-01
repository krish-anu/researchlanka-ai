"""Tests for reusable collector helper functions."""

import requests
import pytest

from src.collectors import crossref_collector as crossref
from src.collectors import openalex_collector as openalex


def test_openalex_as_list_handles_missing_and_wrong_shapes():
    assert openalex.as_list(["item"]) == ["item"]
    assert openalex.as_list(None) == []
    assert openalex.as_list({"not": "a list"}) == []


def test_openalex_unique_join_deduplicates_non_empty_values_in_order():
    assert (
        openalex.unique_join(["Colombo", " ", None, "Kandy", "Colombo"])
        == "Colombo; Kandy"
    )


def test_openalex_country_codes_from_authorship_uses_countries_and_institutions():
    authorship = {
        "countries": ["lk", "US"],
        "institutions": [
            {"display_name": "University of Colombo", "country_code": "lk"},
            {"display_name": "Example University", "country_code": "gb"},
            "not-a-dict",
        ],
    }

    assert openalex.country_codes_from_authorship(authorship) == {"LK", "US", "GB"}


def test_openalex_helpers_ignore_malformed_authorships():
    work = {
        "authorships": [
            "not-a-dict",
            {
                "raw_author_name": "Fallback Author",
                "raw_affiliation_strings": [
                    "Department of Medicine, University of Colombo, Sri Lanka",
                ],
                "countries": ["LK"],
                "institutions": [
                    {"display_name": "University of Colombo", "country_code": "LK"}
                ],
            },
            {
                "author": {"display_name": "Foreign Author"},
                "raw_affiliation_string": "School of Public Health, Example University, USA",
                "countries": ["US"],
                "institutions": [
                    {"display_name": "Example University", "country_code": "US"}
                ],
            },
        ]
    }

    assert openalex.author_names(work) == "Fallback Author; Foreign Author"
    assert openalex.author_names(work, sri_lankan_only=True) == "Fallback Author"
    assert openalex.institution_names(work) == "University of Colombo; Example University"
    assert openalex.institution_names(work, sri_lankan_only=True) == "University of Colombo"
    assert (
        openalex.raw_affiliation_strings(work)
        == "Department of Medicine, University of Colombo, Sri Lanka; "
        "School of Public Health, Example University, USA"
    )
    assert (
        openalex.raw_affiliation_strings(work, sri_lankan_only=True)
        == "Department of Medicine, University of Colombo, Sri Lanka"
    )


def test_openalex_work_to_row_falls_back_to_first_topic_when_primary_topic_missing():
    row = openalex.work_to_row(
        {
            "id": "https://openalex.org/W1",
            "display_name": "Fallback title",
            "topics": [
                {
                    "display_name": "Public health",
                    "field": {"display_name": "Medicine"},
                    "subfield": {"display_name": "Epidemiology"},
                    "domain": {"display_name": "Health Sciences"},
                }
            ],
            "referenced_works": ["https://openalex.org/W2"],
        }
    )

    assert row["title"] == "Fallback title"
    assert row["primary_topic"] == "Public health"
    assert row["primary_field"] == "Medicine"
    assert row["referenced_works_count"] == 1


def test_openalex_iter_sri_lankan_works_honors_max_records(monkeypatch):
    work_one = {"id": "https://openalex.org/W1", "authorships": [{"countries": ["LK"]}]}
    work_two = {"id": "https://openalex.org/W2", "authorships": [{"countries": ["LK"]}]}

    def fake_pages(**_kwargs):
        yield openalex.OpenAlexWorkPage(
            cursor="*",
            next_cursor=None,
            filters=[openalex.LK_AUTHORSHIP_FILTER],
            works=[work_one, work_two],
        )

    collector = openalex.OpenAlexCollector()
    monkeypatch.setattr(collector, "iter_sri_lankan_work_pages", fake_pages)

    assert list(collector.iter_sri_lankan_works(max_records=1)) == [work_one]


def test_crossref_fetch_works_sends_expected_query_params():
    calls = []

    class FakeResponse:
        ok = True
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"items": []}}

    class FakeSession:
        def get(self, url, *, params, timeout):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeResponse()

    collector = crossref.CrossrefCollector(email="tester@example.com")
    collector.session = FakeSession()

    assert collector.fetch_works(
        affiliation_query="Sri Lanka",
        filters=["from-pub-date:2020-01-01"],
        rows=25,
        cursor="abc",
    ) == {"message": {"items": []}}

    assert calls == [
        {
            "url": "https://api.crossref.org/works",
            "params": {
                "query.affiliation": "Sri Lanka",
                "rows": 25,
                "cursor": "abc",
                "filter": "from-pub-date:2020-01-01",
            },
            "timeout": (10, 60),
        }
    ]


def test_crossref_iter_works_stops_at_max_records_across_pages(monkeypatch):
    pages = [
        {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/one",
                        "type": "journal-article",
                        "issued": {"date-parts": [[2024]]},
                    },
                    {
                        "DOI": "10.1000/two",
                        "type": "journal-article",
                        "issued": {"date-parts": [[2024]]},
                    },
                ],
                "next-cursor": "next",
            }
        },
        {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/three",
                        "type": "journal-article",
                        "issued": {"date-parts": [[2024]]},
                    },
                ],
                "next-cursor": None,
            }
        },
    ]

    collector = crossref.CrossrefCollector()
    monkeypatch.setattr(collector, "fetch_works", lambda **_kwargs: pages.pop(0))

    works = list(collector.iter_works(affiliation_query="lanka", max_records=2))

    assert [work["DOI"] for work in works] == ["10.1000/one", "10.1000/two"]
    assert len(pages) == 1


def test_crossref_fetch_work_by_doi_url_encodes_doi_and_returns_message():
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"DOI": "10.1234/example"}}

    class FakeSession:
        def get(self, url, *, timeout):
            calls.append({"url": url, "timeout": timeout})
            return FakeResponse()

    collector = crossref.CrossrefCollector()
    collector.session = FakeSession()

    assert collector.fetch_work_by_doi("10.1234/example") == {
        "DOI": "10.1234/example"
    }
    assert calls == [
        {
            "url": "https://api.crossref.org/works/10.1234%2Fexample",
            "timeout": (10, 60),
        }
    ]


def test_crossref_fetch_work_by_doi_returns_none_for_404():
    class FakeResponse:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 responses should return before raising")

    class FakeSession:
        def get(self, url, *, timeout):
            return FakeResponse()

    collector = crossref.CrossrefCollector()
    collector.session = FakeSession()

    assert collector.fetch_work_by_doi("10.404/missing") is None


def test_crossref_fetch_work_by_doi_raises_request_errors():
    class FakeSession:
        def get(self, url, *, timeout):
            raise requests.RequestException("network unavailable")

    collector = crossref.CrossrefCollector()
    collector.session = FakeSession()

    with pytest.raises(requests.RequestException, match="network unavailable"):
        collector.fetch_work_by_doi("10.500/error")
