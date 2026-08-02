import json

from src.database.load_records import (
    detect_format,
    iter_record_file,
    load_record_file,
)


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_detect_format_from_supported_suffixes(tmp_path):
    assert detect_format(tmp_path / "records.csv") == "csv"
    assert detect_format(tmp_path / "records.json") == "json"
    assert detect_format(tmp_path / "records.jsonl") == "jsonl"
    assert detect_format(tmp_path / "records.ndjson") == "jsonl"


def test_iter_record_file_reads_csv(tmp_path):
    path = tmp_path / "records.csv"
    path.write_text(
        "source_dataset,source_record_id,title,publication_year\n"
        "sample,pub-1,First paper,2024\n"
        "sample,pub-2,Second paper,2025\n",
        encoding="utf-8",
    )

    assert list(iter_record_file(path)) == [
        {
            "source_dataset": "sample",
            "source_record_id": "pub-1",
            "title": "First paper",
            "publication_year": "2024",
        },
        {
            "source_dataset": "sample",
            "source_record_id": "pub-2",
            "title": "Second paper",
            "publication_year": "2025",
        },
    ]


def test_iter_record_file_reads_json_records_list(tmp_path):
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {"source_record_id": "pub-1", "title": "First paper"},
                    {"source_record_id": "pub-2", "title": "Second paper"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert list(iter_record_file(path)) == [
        {"source_record_id": "pub-1", "title": "First paper"},
        {"source_record_id": "pub-2", "title": "Second paper"},
    ]


def test_iter_record_file_reads_jsonl_and_skips_blank_lines(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        '{"source_record_id":"pub-1","title":"First paper"}\n\n'
        '{"source_record_id":"pub-2","title":"Second paper"}\n',
        encoding="utf-8",
    )

    assert list(iter_record_file(path)) == [
        {"source_record_id": "pub-1", "title": "First paper"},
        {"source_record_id": "pub-2", "title": "Second paper"},
    ]


def test_load_record_file_batches_records_and_ensures_schema_once(tmp_path, monkeypatch):
    path = tmp_path / "records.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"source_record_id": f"pub-{index}", "title": f"Paper {index}"})
            for index in range(5)
        ),
        encoding="utf-8",
    )
    calls = []
    connection = FakeConnection()

    def fake_load_final_publications(records, **kwargs):
        calls.append((records, kwargs))
        return len(records)

    monkeypatch.setattr(
        "src.database.load_records.get_connection",
        lambda database_url=None: connection,
    )
    monkeypatch.setattr(
        "src.database.load_records.load_final_publications",
        fake_load_final_publications,
    )

    loaded = load_record_file(
        path,
        database_url="postgresql://example.test/db",
        batch_size=2,
    )

    assert loaded == 5
    assert [len(records) for records, _ in calls] == [2, 2, 1]
    assert [kwargs["ensure_schema"] for _, kwargs in calls] == [True, False, False]
    assert all(kwargs["connection"] is connection for _, kwargs in calls)
    assert all(
        "database_url" not in kwargs
        for _, kwargs in calls
    )
    assert connection.commits == 3
    assert connection.rollbacks == 0
    assert connection.closed is True


def test_load_record_file_limit_applies_before_batching(tmp_path, monkeypatch):
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps([{"title": "One"}, {"title": "Two"}, {"title": "Three"}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "src.database.load_records.get_connection",
        lambda database_url=None: FakeConnection(),
    )
    monkeypatch.setattr(
        "src.database.load_records.load_final_publications",
        lambda records, **kwargs: len(records),
    )

    assert load_record_file(path, batch_size=2, limit=1) == 1
