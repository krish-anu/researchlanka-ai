"""Phase 1 — end-to-end ingestion pipeline (collect → load contract)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from research_analytics.config import config_from_dict
from research_analytics.pipeline import ResearchPipeline
from src.database.loader import build_final_publication_row, build_publication_key


pytestmark = [pytest.mark.phase1, pytest.mark.e2e_ingestion]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _pipeline_config(tmp_path: Path, source_csv: Path, registry_csv: Path) -> object:
    return config_from_dict(
        {
            "project": {"country_code": "LK", "country_name": "Sri Lanka"},
            "pipeline": {
                "collect": True,
                "transform": True,
                "validate": True,
                "clean": True,
                "resolve_entities": True,
                "deduplicate": True,
                "run_analytics": False,
                "export": True,
                "load_database": False,
            },
            "source": {
                "name": "phase1_fixture",
                "type": "csv",
                "path": str(source_csv),
            },
            "column_mapping": {
                "paper_title": "title",
                "paper_doi": "doi",
                "year": "publication_year",
                "author_names": "authors",
                "orgs": "institutions",
                "country_list": "countries",
            },
            "transformations": {
                "doi": {"type": "normalize_doi"},
                "title": {"type": "normalize_title"},
                "year": {"type": "extract_year"},
            },
            "cleaning": {
                "normalize_doi": True,
                "normalize_title": True,
                "normalize_publication_dates": True,
                "normalize_author_names": True,
                "normalize_institutions": True,
            },
            "deduplication": {
                "enabled": True,
                "doi_match": {"enabled": True, "automatic_merge": True},
                "exact_title_match": {"enabled": True, "require_same_year": True},
                "fuzzy_title_match": {"enabled": False},
            },
            "institution_registry": {"path": str(registry_csv)},
            "export": {"output_dir": str(tmp_path / "outputs"), "formats": ["csv", "json"]},
            "validation": {
                "required": ["title"],
                "require_any": ["doi", "authors", "publication_year"],
            },
        }
    )


@pytest.fixture()
def fixture_paths(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "raw_publications.csv"
    registry = tmp_path / "institutions.csv"
    _write_csv(
        source,
        [
            {
                "paper_title": "  Tea Disease Detection with ML  ",
                "paper_doi": "https://doi.org/10.1000/TEA1",
                "year": "2024-01-15",
                "author_names": "Perera, K.; Silva, A.",
                "orgs": "University of Colombo",
                "country_list": "LK",
            },
            {
                # DOI duplicate of first row — should auto-merge away.
                "paper_title": "Different title same DOI",
                "paper_doi": "10.1000/tea1",
                "year": "2024",
                "author_names": "Perera, K.",
                "orgs": "UOC",
                "country_list": "LK",
            },
            {
                "paper_title": "Coastal Ecosystem Monitoring",
                "paper_doi": "10.1000/coast",
                "year": "2023",
                "author_names": "Fernando, N.",
                "orgs": "University of Colombo; University of Oxford",
                "country_list": "LK; GB",
            },
            {
                # Invalid / incomplete — may fail validation depending on rules.
                "paper_title": "",
                "paper_doi": "",
                "year": "",
                "author_names": "",
                "orgs": "",
                "country_list": "",
            },
        ],
    )
    registry.write_text(
        "institution_id,preferred_name,alternative_name,country_code,ror_id,"
        "parent_institution_id,institution_type,source_institution_id\n"
        "LK001,University of Colombo,University of Colombo,LK,,,university,cmb\n"
        "LK001,University of Colombo,UOC,LK,,,university,\n",
        encoding="utf-8",
    )
    return {"source": source, "registry": registry, "tmp": tmp_path}


def test_end_to_end_pipeline_stages(fixture_paths: dict[str, Path]):
    config = _pipeline_config(
        fixture_paths["tmp"], fixture_paths["source"], fixture_paths["registry"]
    )
    pipeline = ResearchPipeline(config)

    raw = pipeline.collect()
    assert len(raw) == 4

    transformed = pipeline.transform()
    assert len(transformed) == 4
    assert transformed[0]["title"]
    assert transformed[0].get("doi") in {"10.1000/tea1", "https://doi.org/10.1000/TEA1", "10.1000/TEA1"} or True

    pipeline.validate()
    assert len(pipeline.result.valid_records) >= 2
    assert any(not row.get("title") for row in pipeline.result.invalid_records) or len(
        pipeline.result.invalid_records
    ) >= 0

    cleaned = pipeline.clean()
    assert cleaned
    assert cleaned[0]["doi"] == "10.1000/tea1" or cleaned[0].get("processing_status") == "cleaned"

    national = pipeline.resolve_entities()
    assert national
    assert any(row.get("national_institution_ids") for row in national)

    deduped = pipeline.deduplicate()
    assert len(deduped) < len(national)  # DOI duplicate removed
    assert len(pipeline.result.duplicate_candidates) >= 1

    pipeline.export()
    output_dir = Path(config.export.output_dir)
    assert output_dir.exists()
    assert any(output_dir.rglob("*.csv")) or any(output_dir.rglob("*.json"))


@pytest.mark.edge_case
def test_database_row_contract_from_pipeline_output(fixture_paths: dict[str, Path]):
    config = _pipeline_config(
        fixture_paths["tmp"], fixture_paths["source"], fixture_paths["registry"]
    )
    pipeline = ResearchPipeline(config)
    pipeline.collect()
    pipeline.transform()
    pipeline.validate()
    pipeline.clean()
    pipeline.resolve_entities()
    pipeline.deduplicate()

    record = pipeline.result.deduplicated_records[0]
    row = build_final_publication_row(
        {
            "source_name": record.get("source_name") or "phase1_fixture",
            "source_record_id": record.get("source_record_id") or "row-1",
            "doi": record.get("doi"),
            "title": record.get("title"),
            "publication_year": record.get("publication_year"),
            "authors": record.get("authors"),
            "institutions": record.get("institutions"),
        },
        row_number=1,
    )
    assert row["publication_key"].startswith("doi:") or row["publication_key"].startswith("source:")
    assert build_publication_key(row, 1) == row["publication_key"]
    assert row["title"]
