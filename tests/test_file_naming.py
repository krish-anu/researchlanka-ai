"""Tests for project file-naming conventions."""

from pathlib import Path

import pytest

from src.pipeline import collect_crossref
from src.quality import compare_dois
from src.pipeline import kaggle_collect_openalex_sri_lanka
from src.utils.file_naming import dataset_filename, is_dataset_filename, slug_segment


def test_slug_segment_converts_names_to_lower_snake_case():
    assert slug_segment("Sri Lanka") == "sri_lanka"
    assert slug_segment("OpenAlex-only") == "openalex_only"


def test_slug_segment_rejects_empty_segments():
    with pytest.raises(ValueError):
        slug_segment("!!!")


def test_dataset_filename_uses_source_scope_entity_variant_order():
    assert (
        dataset_filename(
            "Crossref",
            "Sri Lanka",
            "Works",
            ".jsonl",
            variant="DOI enriched",
        )
        == "crossref_sri_lanka_works_doi_enriched.jsonl"
    )


def test_dataset_filename_rejects_unsupported_extensions():
    with pytest.raises(ValueError):
        dataset_filename("openalex", "sri_lanka", "works", "xlsx")


def test_is_dataset_filename_accepts_lower_snake_case_supported_outputs():
    assert is_dataset_filename("openalex_sri_lanka_works.csv")
    assert is_dataset_filename("openalex_sri_lanka_works.parquet")
    assert is_dataset_filename("doi_comparison_common_dois.txt")


def test_is_dataset_filename_rejects_mixed_case_and_hyphenated_outputs():
    assert not is_dataset_filename("OpenAlex_Sri_Lanka_Works.csv")
    assert not is_dataset_filename("openalex-sri-lanka-works.csv")
    assert not is_dataset_filename("works.csv")


def test_script_defaults_follow_dataset_naming_convention():
    default_paths = [
        kaggle_collect_openalex_sri_lanka.DEFAULT_JSONL_OUTPUT,
        kaggle_collect_openalex_sri_lanka.DEFAULT_CSV_OUTPUT,
        kaggle_collect_openalex_sri_lanka.DEFAULT_PARQUET_OUTPUT,
        collect_crossref.DEFAULT_OUTPUT_PATH,
        collect_crossref.DEFAULT_ENRICHED_OUTPUT_PATH,
        compare_dois.OPENALEX_PATH,
        compare_dois.CROSSREF_PATH,
    ]

    assert all(is_dataset_filename(path) for path in default_paths)


def test_legacy_openalex_raw_path_is_not_reintroduced():
    project_root = Path(__file__).resolve().parents[1]
    legacy_path = "data/raw/open-alex/open-alex.csv"

    searched_files = [
        *project_root.joinpath("scripts").glob("*.py"),
        *project_root.joinpath("src").rglob("*.py"),
    ]

    assert all(legacy_path not in path.read_text() for path in searched_files)
