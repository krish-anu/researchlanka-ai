from src.collectors.crossref_collector import (
    CrossrefCollector,
    CrossrefPrefixCollector,
    CrossrefRepeatedCursorError,
    create_session,
    is_crossref_work_in_publication_year_range,
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
                    "author": [
                        {
                            "given": "A.",
                            "family": "Author",
                            "affiliation": [{"name": "University of Colombo"}],
                        }
                    ],
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


def test_iter_works_can_require_first_author_lk(monkeypatch):
    fake_response = {
        "message": {
            "items": [
                {
                    "DOI": "10.1234/lk-first",
                    "type": "journal-article",
                    "title": ["LK first"],
                    "issued": {"date-parts": [[2024]]},
                    "author": [
                        {
                            "given": "A.",
                            "family": "Author",
                            "affiliation": [{"name": "University of Colombo"}],
                        }
                    ],
                },
                {
                    "DOI": "10.1234/lk-later",
                    "type": "journal-article",
                    "title": ["LK later"],
                    "issued": {"date-parts": [[2024]]},
                    "author": [
                        {
                            "given": "Foreign",
                            "family": "Lead",
                            "affiliation": [{"name": "Example University, Australia"}],
                        },
                        {
                            "given": "Sri Lankan",
                            "family": "Collaborator",
                            "affiliation": [{"name": "University of Colombo"}],
                        },
                    ],
                },
            ],
            "next-cursor": None,
        }
    }

    collector = CrossrefCollector()
    monkeypatch.setattr(collector, "fetch_works", lambda **kwargs: fake_response)

    works = list(
        collector.iter_works(
            affiliation_query="lanka",
            require_first_author_lk=True,
        )
    )

    assert [work["DOI"] for work in works] == ["10.1234/lk-first"]
    assert works[0]["keep_in_strict_sri_lanka_dataset"] is True


def test_crossref_publication_year_range_requires_2016_or_later():
    old_work = {"issued": {"date-parts": [[2015]]}}
    start_work = {"issued": {"date-parts": [[2016]]}}
    current_work = {"published": {"date-parts": [[2024, 4, 5]]}}
    missing_year_work = {"DOI": "10.4038/no-year"}

    assert is_crossref_work_in_publication_year_range(old_work) is False
    assert is_crossref_work_in_publication_year_range(start_work) is True
    assert is_crossref_work_in_publication_year_range(current_work) is True
    assert is_crossref_work_in_publication_year_range(missing_year_work) is False


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
                "items": [
                    {"DOI": "10.4038/one", "issued": {"date-parts": [[2024]]}},
                    {"DOI": "10.4038/two", "issued": {"date-parts": [[2024]]}},
                ],
                "next-cursor": "next",
            }
        },
        {
            "message": {
                "items": [
                    {"DOI": "10.4038/three", "issued": {"date-parts": [[2024]]}},
                ],
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


def test_prefix_iter_works_stops_on_repeated_cursor():
    page = {
        "message": {
            "items": [{"DOI": "10.4038/one", "issued": {"date-parts": [[2024]]}}],
            "next-cursor": "*",
        }
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return page

    class FakeSession:
        def get(self, url, *, params, timeout):
            return FakeResponse()

    collector = CrossrefPrefixCollector(prefix="10.4038", delay=0)
    collector.session = FakeSession()

    assert list(collector.iter_works()) == [
        {"DOI": "10.4038/one", "issued": {"date-parts": [[2024]]}}
    ]


def test_prefix_iter_works_can_raise_on_repeated_cursor():
    page = {
        "message": {
            "items": [{"DOI": "10.4038/one", "issued": {"date-parts": [[2024]]}}],
            "next-cursor": "*",
        }
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return page

    class FakeSession:
        def get(self, url, *, params, timeout):
            return FakeResponse()

    collector = CrossrefPrefixCollector(prefix="10.4038", delay=0)
    collector.session = FakeSession()
    works = collector.iter_works(repeated_cursor_policy="raise")

    assert next(works) == {
        "DOI": "10.4038/one",
        "issued": {"date-parts": [[2024]]},
    }
    try:
        next(works)
    except CrossrefRepeatedCursorError:
        pass
    else:
        raise AssertionError("Expected CrossrefRepeatedCursorError")


def test_prefix_iter_works_by_publication_date_splits_repeated_cursor():
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
            calls.append(params)
            filters = params["filter"]
            if filters == "from-pub-date:2020-01-01,until-pub-date:2020-12-31":
                return FakeResponse(
                    {
                        "message": {
                            "items": [
                                {"DOI": "10.4038/one", "issued": {"date-parts": [[2020]]}},
                            ],
                            "next-cursor": "*",
                        }
                    }
                )
            if filters == "from-pub-date:2020-01-01,until-pub-date:2020-07-01":
                return FakeResponse(
                    {
                        "message": {
                            "items": [
                                {"DOI": "10.4038/one", "issued": {"date-parts": [[2020]]}},
                            ],
                            "next-cursor": None,
                        }
                    }
                )
            if filters == "from-pub-date:2020-07-02,until-pub-date:2020-12-31":
                return FakeResponse(
                    {
                        "message": {
                            "items": [
                                {"DOI": "10.4038/two", "issued": {"date-parts": [[2020]]}},
                            ],
                            "next-cursor": None,
                        }
                    }
                )
            raise AssertionError(f"Unexpected filters: {filters}")

    collector = CrossrefPrefixCollector(prefix="10.4038", rows=500, delay=0)
    collector.session = FakeSession()

    works = list(collector.iter_works_by_publication_date(start_year=2020, end_year=2020))

    assert [work["DOI"] for work in works] == ["10.4038/one", "10.4038/two"]
    assert [call["cursor"] for call in calls] == ["*", "*", "*"]
