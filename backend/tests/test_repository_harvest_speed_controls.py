from types import SimpleNamespace

from src.pipeline import harvest_all


def test_parse_id_filter_normalizes_comma_separated_ids():
    assert harvest_all.parse_id_filter(" UOM, cmb ,,sliit ") == {
        "uom",
        "cmb",
        "sliit",
    }


def test_filter_targets_applies_include_and_exclude_sets():
    targets = [
        SimpleNamespace(id="uom"),
        SimpleNamespace(id="cmb"),
        SimpleNamespace(id="seu"),
        SimpleNamespace(id="sliit"),
    ]

    selected = harvest_all.filter_targets(
        targets,
        include_ids={"uom", "cmb", "seu"},
        exclude_ids={"seu"},
    )

    assert [target.id for target in selected] == ["uom", "cmb"]


def test_skip_existing_outcome_reuses_non_empty_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(harvest_all, "DEFAULT_RAW_DIR", tmp_path)
    target = SimpleNamespace(id="uom", name="University of Moratuwa")
    output_path = tmp_path / "uom" / "oai_dc.jsonl"
    output_path.parent.mkdir(parents=True)
    output_path.write_text('{"id": 1}\n\n{"id": 2}\n', encoding="utf-8")

    outcome = harvest_all.skip_existing_outcome(target)

    assert outcome is not None
    assert outcome.status == "skipped_existing"
    assert outcome.record_count == 2
    assert outcome.output_path == str(output_path)


def test_skip_existing_outcome_ignores_missing_or_empty_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(harvest_all, "DEFAULT_RAW_DIR", tmp_path)
    missing_target = SimpleNamespace(id="missing", name="Missing")
    empty_target = SimpleNamespace(id="empty", name="Empty")
    empty_path = tmp_path / "empty" / "oai_dc.jsonl"
    empty_path.parent.mkdir(parents=True)
    empty_path.write_text("\n", encoding="utf-8")

    assert harvest_all.skip_existing_outcome(missing_target) is None
    assert harvest_all.skip_existing_outcome(empty_target) is None
