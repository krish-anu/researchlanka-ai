"""Tests for OpenAlex Sri Lanka collection using sample publication records."""

import argparse

from scripts import kaggle_collect_openalex_sri_lanka as openalex


def sample_work(country_code: str = "LK") -> dict:
    """Create a minimal OpenAlex-like work record for collector tests."""
    return {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1234/example",
        "title": "Sample Sri Lankan Research Publication",
        "publication_year": 2024,
        "publication_date": "2024-01-15",
        "type": "article",
        "cited_by_count": 7,
        "authorships": [
            {
                "author": {"display_name": "A. Researcher"},
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
            "source": {
                "display_name": "Example Journal",
                "host_organization_name": "Example Publisher",
            },
        },
        "open_access": {"is_oa": True},
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


def test_work_to_row_flattens_expected_openalex_fields():
    """Sample OpenAlex records should produce the expected flat CSV fields."""
    row = openalex.work_to_row(sample_work("LK"))

    assert row["openalex_id"] == "https://openalex.org/W123"
    assert row["doi"] == "https://doi.org/10.1234/example"
    assert row["title"] == "Sample Sri Lankan Research Publication"
    assert row["publication_year"] == 2024
    assert row["author_count"] == 2
    assert row["authors"] == "A. Researcher; B. Collaborator"
    assert row["sri_lankan_authors"] == "A. Researcher"
    assert row["institutions"] == "University of Colombo; Example University"
    assert row["sri_lankan_institutions"] == "University of Colombo"
    assert row["countries"] == "LK; US"
    assert row["source_name"] == "Example Journal"
    assert row["publisher"] == "Example Publisher"
    assert row["is_oa"] is True
    assert row["landing_page_url"] == "https://example.org/paper"
    assert row["pdf_url"] == "https://example.org/paper.pdf"


def test_build_filters_adds_publication_year_range():
    """Year arguments should be converted into an OpenAlex publication-year filter."""
    args = argparse.Namespace(
        filter=[openalex.LK_AUTHORSHIP_FILTER],
        from_year=2020,
        to_year=2024,
    )

    assert openalex.build_filters(args) == [
        openalex.LK_AUTHORSHIP_FILTER,
        "publication_year:2020-2024",
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

    monkeypatch.setattr(openalex, "fetch_works", fake_fetch_works)

    args = argparse.Namespace(
        filter=[openalex.LK_AUTHORSHIP_FILTER],
        from_year=None,
        to_year=None,
        per_page=25,
        max_records=None,
        email="tester@example.com",
        api_key=None,
    )

    works = list(openalex.iter_sri_lankan_works(args))

    assert works == [lk_work]
    assert calls == [
        {
            "filters": [openalex.LK_AUTHORSHIP_FILTER],
            "cursor": "*",
            "per_page": 25,
            "email": "tester@example.com",
            "api_key": None,
        }
    ]
