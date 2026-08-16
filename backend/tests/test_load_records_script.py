import json

from research_analytics.cli import load_database_records
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


def test_load_record_file_batches_records_and_ensures_schema_once(
    tmp_path, monkeypatch
):
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
    assert all("database_url" not in kwargs for _, kwargs in calls)
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


def test_iter_csv_records_handles_large_fields(tmp_path):
    path = tmp_path / "large_field.csv"
    large_value = "A" * 200_000
    path.write_text(
        f"source_dataset,source_record_id,title\n" f"sample,pub-1,{large_value}\n",
        encoding="utf-8",
    )

    assert list(iter_record_file(path))[0]["title"] == large_value


def test_load_database_records_populates_full_normalized_database(
    tmp_path, monkeypatch
):
    dataset_path = tmp_path / "final_dataset.csv"
    dataset_path.write_text(
        "source_dataset,source_record_id,title,authors,keywords,countries,institutions\n"
        "sample,pub-1,First paper,A. Author; B. Author,AI; ML,US; LK,University of Colombo\n"
        "sample,pub-2,Second paper,C. Author,ML,US,University of Peradeniya\n",
        encoding="utf-8",
    )

    captured = {}

    def fake_load_full_database_dataset(path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"final_publications": 2, "source_records": 2, "authors": 3}

    monkeypatch.setattr(
        "src.database.load_records.load_record_file",
        lambda *args, **kwargs: 2,
    )
    monkeypatch.setattr(
        "src.database.load_records.load_full_database_dataset",
        fake_load_full_database_dataset,
    )

    loaded = load_database_records(
        config={"dummy": True},
        dataset_path=dataset_path,
        batch_size=7,
        full_database=True,
    )

    assert loaded == {"final_publications": 2, "source_records": 2, "authors": 3}
    assert captured["path"] == dataset_path
    assert captured["kwargs"]["batch_size"] == 7


def test_build_final_publication_row_rejects_year_only_dates():
    row = {
        "title": "Sample paper",
        "publication_year": 2016,
        "publication_date": "2016",
        "source_dataset": "sample",
        "source_record_id": "pub-1",
    }

    normalized = __import__(
        "src.database.loader", fromlist=["build_final_publication_row"]
    ).build_final_publication_row(row, 1)

    assert normalized["publication_year"] == 2016
    assert normalized["publication_date"] is None


def test_upsert_publication_coerces_year_only_dates_to_none():
    class Cursor:
        def __init__(self):
            self.args = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, args):
            self.args = args

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self):
            return self.cursor_obj

    connection = Connection()
    from src.database.load_records import _upsert_publication

    _upsert_publication(
        connection,
        "source:sample:pub-1",
        {
            "title": "Sample paper",
            "publication_year": 2016,
            "publication_date": "2016",
            "source_dataset": "sample",
            "source_record_id": "pub-1",
        },
    )

    assert connection.cursor_obj.args[6] is None


def test_resolve_source_institution_id_rejects_empty_parentheses_and_empty_collections():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, args):
            return None

        def fetchone(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

    from src.database.load_records import _resolve_source_institution_id

    assert _resolve_source_institution_id(Connection(), ()) is None
    assert _resolve_source_institution_id(Connection(), "()") is None
    assert _resolve_source_institution_id(Connection(), []) is None


def test_upsert_publication_location_uses_not_exists_instead_of_conflict_target():
    seen = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, args):
            seen["query"] = query
            seen["args"] = args

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self):
            return self.cursor_obj

    from src.database.load_records import _upsert_publication_location

    _upsert_publication_location(
        Connection(),
        "pub-123",
        {"url": "https://example.org", "pdf_url": "https://example.org/p.pdf"},
    )

    assert "WHERE NOT EXISTS" in seen["query"]
    assert seen["args"][-1] == "pub-123"
