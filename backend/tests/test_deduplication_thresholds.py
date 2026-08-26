from research_analytics.config import config_from_dict
from research_analytics.deduplication import find_duplicate_candidates


def test_fuzzy_title_threshold_creates_manual_review_candidates_only():
    config = config_from_dict(
        {
            "deduplication": {
                "fuzzy_title_match": {"enabled": True, "threshold": 85},
                "author_match": {"minimum_matching_authors": 1},
                "year_difference": {"maximum": 1},
            }
        }
    )
    records = [
        {
            "title": "Machine learning for tea leaf disease detection",
            "publication_year": "2024",
            "authors": "A. Author",
            "doi": "",
        },
        {
            "title": "Machine learning models for tea leaf disease detection",
            "publication_year": "2025",
            "authors": "A Author",
            "doi": "",
        },
    ]

    candidates = find_duplicate_candidates(records, config.deduplication)

    fuzzy = [candidate for candidate in candidates if candidate.match_type == "fuzzy_title"]
    assert len(fuzzy) == 1
    assert fuzzy[0].merge_decision == "manual_review"
    assert fuzzy[0].confidence == "review"
    assert fuzzy[0].score >= 85
    assert fuzzy[0].threshold == 85


def test_fuzzy_title_threshold_requires_author_when_configured():
    config = config_from_dict(
        {
            "deduplication": {
                "fuzzy_title_match": {"enabled": True, "threshold": 85},
                "author_match": {"minimum_matching_authors": 1},
                "year_difference": {"maximum": 1},
            }
        }
    )
    records = [
        {
            "title": "Machine learning for tea leaf disease detection",
            "publication_year": "2024",
            "authors": "A. Author",
            "doi": "",
        },
        {
            "title": "Machine learning for tea-leaf disease detection",
            "publication_year": "2024",
            "authors": "B. Author",
            "doi": "",
        },
    ]

    candidates = find_duplicate_candidates(records, config.deduplication)

    assert not [candidate for candidate in candidates if candidate.match_type == "fuzzy_title"]
