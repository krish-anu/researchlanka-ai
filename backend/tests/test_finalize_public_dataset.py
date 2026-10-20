from scripts.quality.finalize_public_dataset import (
    PUBLIC_RELEASE_FIELDS,
    augment_duplicate_candidates,
    canonical_rank,
    public_release_row,
    unsupported_sri_lanka_alias,
)


def test_unsupported_sri_lanka_alias_requires_unambiguous_evidence():
    assert unsupported_sri_lanka_alias(
        {
            "openalex_id": "https://openalex.org/W1",
            "sri_lankan_institutions": "National Research Council",
        }
    )
    assert not unsupported_sri_lanka_alias(
        {
            "openalex_id": "https://openalex.org/W2",
            "sri_lankan_institutions": (
                "National Research Council; Uva Wellassa University"
            ),
        }
    )


def test_canonical_rank_prefers_formal_publication_over_preprint():
    published = {
        "doi": "10.1000/published",
        "title": "A study",
        "type": "article",
        "source_type": "journal",
        "publication_date": "2025-01-01",
        "openalex_id": "https://openalex.org/W2",
    }
    preprint = {
        **published,
        "doi": "10.21203/rs.3.rs-1/v1",
        "type": "preprint",
        "source_type": "repository",
        "publication_date": "2026-01-01",
        "openalex_id": "https://openalex.org/W1",
    }

    assert canonical_rank(published) > canonical_rank(preprint)


def test_public_release_row_preserves_abstract_text():
    source = {
        "abstract": "Copyrighted abstract",
        "abstract_search_text": "copyrighted abstract",
        "title": "Title remains",
        "ai_classification_confidence": "0.99",
    }

    public = public_release_row(source)

    assert public["abstract"] == "Copyrighted abstract"
    assert public["title"] == "Title remains"
    assert list(public) == PUBLIC_RELEASE_FIELDS
    assert "abstract_search_text" not in public
    assert "ai_classification_confidence" not in public
    assert source["abstract"] == "Copyrighted abstract"


def test_normalized_duplicate_extends_existing_title_group():
    rows = [
        {
            "openalex_id": "W1",
            "title": "Adapter Based Fine-Tuning",
            "doi": "10.21203/preprint",
            "publication_date": "2024-01-01",
            "authors": "A. Author",
            "source_dataset": "openalex",
        },
        {
            "openalex_id": "W2",
            "title": "Adapter-based fine-tuning",
            "doi": "10.1000/article",
            "publication_date": "2025-01-01",
            "authors": "A. Author",
            "source_dataset": "openalex",
        },
    ]
    supplied = [
        {
            "title_group": "1",
            "original_csv_row": "2",
            **rows[0],
            "resolution_note": "",
        }
    ]

    augmented = augment_duplicate_candidates(rows, supplied)

    assert len(augmented) == 2
    assert {row["title_group"] for row in augmented} == {"1"}
    assert {row["openalex_id"] for row in augmented} == {"W1", "W2"}
