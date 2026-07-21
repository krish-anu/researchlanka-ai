from src.collectors.crossref_collector import (
    CrossrefCollector,
    CrossrefPrefixCollector,
    create_session,
)

def test_create_session():
    session=create_session("TestAgent/1.0")

    assert session.headers["User-Agent"]=="TestAgent/1.0"


def test_iter_works(monkeypatch):
    fake_response = {
        "message": {
            "items": [
                {
                    "DOI": "10.1234/test",
                    "type": "journal-article",
                    "title": ["Test Paper"],
                    "issued": {"date-parts": [[2024]]},
                },
                {"DOI": "10.9999/book", "type": "book"},
            ],
            "next-cursor": None,
        }
    }

    collector=CrossrefCollector()

    monkeypatch.setattr(
        collector,
        "fetch_works",
        lambda **kwargs:fake_response
    )

    works=list(collector.iter_works(affiliation_query="lanka"))

    assert len(works)==1
    assert works[0]["DOI"]=="10.1234/test"


def test_prefix_total_works_sends_prefix_query():
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"total-results": 26200}}

    class FakeSession:
        def get(self, url, *, params, timeout):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeResponse()

    collector = CrossrefPrefixCollector(prefix="10.4038", email="tester@example.com")
    collector.session = FakeSession()

    assert collector.total_works() == 26200
    assert calls == [
        {
            "url": "https://api.crossref.org/prefixes/10.4038/works",
            "params": {"rows": 0, "mailto": "tester@example.com"},
            "timeout": 60,
        }
    ]


def test_prefix_iter_works_honors_max_records_across_pages():
    pages = [
        {
            "message": {
                "items": [{"DOI": "10.4038/one"}, {"DOI": "10.4038/two"}],
                "next-cursor": "next",
            }
        },
        {
            "message": {
                "items": [{"DOI": "10.4038/three"}],
                "next-cursor": None,
            }
        },
    ]
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def get(self, url, *, params, timeout):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeResponse(pages.pop(0))

    collector = CrossrefPrefixCollector(prefix="10.4038", rows=2, delay=0)
    collector.session = FakeSession()

    works = list(collector.iter_works(max_records=2))

    assert [work["DOI"] for work in works] == ["10.4038/one", "10.4038/two"]
    assert len(pages) == 1
    assert calls == [
        {
            "url": "https://api.crossref.org/prefixes/10.4038/works",
            "params": {"rows": 2, "cursor": "*"},
            "timeout": 60,
        }
    ]

