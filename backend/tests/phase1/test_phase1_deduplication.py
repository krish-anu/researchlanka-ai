"""Phase 1 — deduplication edge cases."""

from __future__ import annotations

import pytest

from research_analytics.config import config_from_dict
from research_analytics.deduplication import find_duplicate_candidates


pytestmark = [pytest.mark.phase1, pytest.mark.deduplication]


def _config(**overrides):
    payload = {
        "deduplication": {
            "enabled": True,
            "doi_match": {"enabled": True, "automatic_merge": True},
            "title_year_match": {"enabled": True},
            "fuzzy_title_match": {"enabled": True, "threshold": 85},
            "author_match": {"minimum_matching_authors": 1},
            "year_difference": {"maximum": 1},
        }
    }
    payload["deduplication"].update(overrides)
    return config_from_dict(payload)


@pytest.mark.edge_case
def test_doi_duplicates_auto_merge_even_with_different_titles():
    records = [
        {"title": "Paper A", "doi": "https://doi.org/10.1000/SAME", "publication_year": 2020},
        {"title": "Paper B totally different", "doi": "10.1000/same", "publication_year": 2021},
    ]
    candidates = find_duplicate_candidates(records, _config().deduplication)
    doi_matches = [c for c in candidates if c.match_type == "doi"]
    assert len(doi_matches) == 1
    assert doi_matches[0].merge_decision == "auto_merge"
    assert doi_matches[0].confidence == "automatic"


@pytest.mark.edge_case
def test_blank_doi_does_not_match():
    records = [
        {"title": "Unique one", "doi": "", "publication_year": 2020, "authors": "A"},
        {"title": "Unique two", "doi": None, "publication_year": 2020, "authors": "B"},
    ]
    candidates = find_duplicate_candidates(records, _config().deduplication)
    assert not [c for c in candidates if c.match_type == "doi"]


@pytest.mark.edge_case
def test_title_year_exact_match_with_compatible_authors():
    records = [
        {
            "title": "Tea Leaf Disease Detection",
            "publication_year": "2024",
            "authors": "Perera, K.",
            "doi": "",
        },
        {
            "title": "tea leaf disease detection",
            "publication_year": 2024,
            "authors": "Perera, K.",
            "doi": "",
        },
    ]
    candidates = find_duplicate_candidates(records, _config().deduplication)
    assert any(c.match_type in {"title_year", "exact_title_year"} or "title" in c.match_type for c in candidates)


@pytest.mark.edge_case
def test_fuzzy_title_year_gap_beyond_threshold_is_rejected():
    config = _config()
    records = [
        {
            "title": "Machine learning for tea leaf disease detection",
            "publication_year": "2010",
            "authors": "A. Author",
            "doi": "",
        },
        {
            "title": "Machine learning for tea leaf disease detection",
            "publication_year": "2024",
            "authors": "A. Author",
            "doi": "",
        },
    ]
    candidates = find_duplicate_candidates(records, config.deduplication)
    fuzzy = [c for c in candidates if c.match_type == "fuzzy_title"]
    assert fuzzy == []


@pytest.mark.edge_case
def test_deduplication_disabled_returns_empty():
    config = config_from_dict({"deduplication": {"enabled": False}})
    records = [
        {"title": "Same", "doi": "10.1000/x", "publication_year": 2020},
        {"title": "Same", "doi": "10.1000/x", "publication_year": 2020},
    ]
    assert find_duplicate_candidates(records, config.deduplication) == []
