"""Tests for keeping repository aggregation separate from standalone sources."""

from src.processing.convert_repositories_jsonl_to_csv import iter_input_files
from src.processing.map_to_common_schema import discover_raw_institution_ids


def test_map_all_discovery_excludes_sljol_standalone_source(tmp_path):
    raw_dir = tmp_path / "raw"
    (raw_dir / "uom").mkdir(parents=True)
    (raw_dir / "sljol").mkdir()
    (raw_dir / "uom" / "oai_dc.jsonl").write_text('{"title": ["Repo item"]}\n', encoding="utf-8")
    (raw_dir / "sljol" / "crossref_works.jsonl").write_text('{"title": ["SLJOL item"]}\n', encoding="utf-8")

    assert discover_raw_institution_ids(raw_dir) == ["uom"]


def test_repository_csv_default_inputs_exclude_stale_sljol_jsonl(tmp_path):
    processed_dir = tmp_path / "repositories"
    processed_dir.mkdir()
    uom_path = processed_dir / "uom.jsonl"
    sljol_path = processed_dir / "sljol.jsonl"
    uom_path.write_text('{"source_institution_id": "uom"}\n', encoding="utf-8")
    sljol_path.write_text('{"source_institution_id": "sljol"}\n', encoding="utf-8")

    assert list(iter_input_files(None, default_input_dir=processed_dir)) == [uom_path]
    assert list(iter_input_files(sljol_path)) == [sljol_path]
