"""Tests for memory-conscious framework exports."""

import json
from pathlib import Path

from research_analytics.exporters import _write_json


def test_write_json_streams_to_open_file(tmp_path, monkeypatch) -> None:
    output = tmp_path / "records.json"
    records = [{"id": index, "abstract": "A" * 10_000} for index in range(20)]

    def fail_write_text(*_args, **_kwargs):
        raise AssertionError("large JSON exports must not use Path.write_text")

    monkeypatch.setattr(Path, "write_text", fail_write_text)
    _write_json(output, records)

    with output.open(encoding="utf-8") as handle:
        assert json.load(handle) == records
