import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.openalex_collector import work_has_author_from_country
from scripts.convert_openalex_jsonl_to_csv import (
    has_sri_lankan_affiliation,
    sri_lankan_author_names,
)


def test_work_matches_when_one_author_has_lk_country_code() -> None:
    work = {
        "authorships": [
            {
                "author": {"display_name": "Foreign Author"},
                "countries": ["US"],
                "institutions": [{"country_code": "US"}],
            },
            {
                "author": {"display_name": "Sri Lankan Author"},
                "countries": ["LK"],
                "institutions": [],
            },
        ]
    }

    assert work_has_author_from_country(work)
    assert has_sri_lankan_affiliation(work)
    assert sri_lankan_author_names(work) == "Sri Lankan Author"


def test_work_matches_when_one_author_has_lk_institution_only() -> None:
    work = {
        "authorships": [
            {
                "author": {"display_name": "Collaborator"},
                "countries": ["GB"],
                "institutions": [{"country_code": "GB"}],
            },
            {
                "author": {"display_name": "Local Institution Author"},
                "countries": [],
                "institutions": [{"country_code": "lk"}],
            },
        ]
    }

    assert work_has_author_from_country(work)
    assert has_sri_lankan_affiliation(work)
    assert sri_lankan_author_names(work) == "Local Institution Author"


def test_work_without_lk_affiliation_is_excluded() -> None:
    work = {
        "authorships": [
            {
                "author": {"display_name": "Foreign Author"},
                "countries": ["US"],
                "institutions": [{"country_code": "US"}],
            }
        ]
    }

    assert not work_has_author_from_country(work)
    assert not has_sri_lankan_affiliation(work)
    assert sri_lankan_author_names(work) == ""
