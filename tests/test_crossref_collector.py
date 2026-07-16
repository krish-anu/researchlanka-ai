from src.collectors.crossref_collector import create_session,CrossrefCollector

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


