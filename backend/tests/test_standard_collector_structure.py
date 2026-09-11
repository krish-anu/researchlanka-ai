import pytest

from src.collectors.dspace_rest_collector import DspaceRestCollector
from src.collectors.html_meta_collector import HtmlMetaCollector
from src.collectors.http import create_retry_session
from src.collectors.oai_pmh_collector import OaiPmhCollector
from src.collectors.schema_mapping import (
    has_dspace_rest_doi,
    has_html_meta_doi,
    has_oai_dc_doi,
)
from src.collectors.sitemap_collector import SitemapCollector


def test_create_retry_session_sets_user_agent_and_retry_policy():
    session = create_retry_session(user_agent="TestCollector/1.0")

    assert session.headers["User-Agent"] == "TestCollector/1.0"
    assert session.adapters["https://"].max_retries.total == 5
    assert session.adapters["http://"].max_retries.total == 5


def test_dspace_rest_iter_items_pages_and_parses_metadata():
    calls = []
    pages = [
        {
            "_embedded": {
                "searchResult": {
                    "_embedded": {
                        "objects": [
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "item-1",
                                        "name": "One",
                                        "handle": "123456789/1",
                                        "lastModified": "2026-01-01T00:00:00Z",
                                        "withdrawn": False,
                                        "metadata": {
                                            "dc.title": [{"value": "Publication One"}],
                                            "dc.empty": [{"value": ""}],
                                        },
                                    }
                                }
                            }
                        ]
                    },
                    "page": {"totalPages": 2, "totalElements": 2},
                }
            }
        },
        {
            "_embedded": {
                "searchResult": {
                    "_embedded": {
                        "objects": [
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "item-2",
                                        "name": "Two",
                                        "metadata": {},
                                    }
                                }
                            }
                        ]
                    },
                    "page": {"totalPages": 2, "totalElements": 2},
                }
            }
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def get(self, url, *, params, timeout, verify):
            calls.append(
                {"url": url, "params": params, "timeout": timeout, "verify": verify}
            )
            return FakeResponse(pages.pop(0))

    collector = DspaceRestCollector(
        api_base_url="https://repo.example.edu/server/api/",
        page_size=1,
        delay=0,
        session=FakeSession(),
    )

    items = list(collector.iter_items(max_records=2, start_year=None, end_year=None))

    assert [item["uuid"] for item in items] == ["item-1", "item-2"]
    assert items[0]["metadata"] == {"dc.title": ["Publication One"]}
    assert calls[0]["url"] == (
        "https://repo.example.edu/server/api/discover/search/objects"
    )
    assert calls[0]["params"] == {"dsoType": "item", "page": 0, "size": 1}


def test_dspace_rest_iter_items_filters_by_publication_year():
    pages = [
        {
            "_embedded": {
                "searchResult": {
                    "_embedded": {
                        "objects": [
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "old",
                                        "name": "Too old",
                                        "metadata": {
                                            "dc.date.issued": [{"value": "2015"}],
                                        },
                                    }
                                }
                            },
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "start",
                                        "name": "Start year",
                                        "metadata": {
                                            "dc.date.issued": [{"value": "2016-01-01"}],
                                        },
                                    }
                                }
                            },
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "current",
                                        "name": "Current",
                                        "metadata": {
                                            "dc.date.issued": [{"value": "2024"}],
                                        },
                                    }
                                }
                            },
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "missing",
                                        "name": "Missing year",
                                        "metadata": {},
                                    }
                                }
                            },
                        ]
                    },
                    "page": {"totalPages": 1, "totalElements": 4},
                }
            }
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def get(self, url, *, params, timeout, verify):
            return FakeResponse(pages.pop(0))

    collector = DspaceRestCollector(
        api_base_url="https://repo.example.edu/server/api/",
        delay=0,
        session=FakeSession(),
    )

    items = list(collector.iter_items(max_records=1, start_year=2016, end_year=2026))

    assert [item["uuid"] for item in items] == ["start"]


def test_html_meta_collector_discovers_and_fetches_items():
    html_pages = {
        "https://repo.example.edu/ujrr/browse": (
            '<a href="/ujrr/handle/123456789/1">One</a>'
        ),
        "https://repo.example.edu/ujrr/handle/123456789/1": (
            '<meta name="DC.title" content="Encoded &amp; Title">'
            "<meta content='Reversed Attribute Title' name='DC.alternative'>"
            "<META CONTENT='Uppercase Attribute Author' NAME='citation_author'>"
            "<meta data-extra='x' content='2026-07-21' name='DCTERMS.dateAccepted'>"
            '<meta name="citation_author" content="A. Author">'
        ),
    }
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, text):
            self.text = text

    class FakeSession:
        def get(self, url, **kwargs):
            calls.append({"url": url, "kwargs": kwargs})
            return FakeResponse(html_pages.get(url, ""))

    collector = HtmlMetaCollector(
        base_url="https://repo.example.edu/ujrr/",
        delay=0,
        session=FakeSession(),
    )

    items = list(collector.iter_items(max_records=1, start_year=None, end_year=None))

    assert items == [
        {
            "handle_path": "/handle/123456789/1",
            "url": "https://repo.example.edu/ujrr/handle/123456789/1",
            "meta": {
                "DC.title": ["Encoded & Title"],
                "DC.alternative": ["Reversed Attribute Title"],
                "citation_author": ["Uppercase Attribute Author", "A. Author"],
                "DCTERMS.dateAccepted": ["2026-07-21"],
            },
        }
    ]
    assert calls[0]["url"] == "https://repo.example.edu/ujrr/browse"


def test_html_meta_collector_filters_by_publication_year():
    html_pages = {
        "https://repo.example.edu/ujrr/browse": (
            '<a href="/ujrr/handle/123456789/1">One</a>'
            '<a href="/ujrr/handle/123456789/2">Two</a>'
            '<a href="/ujrr/handle/123456789/3">Three</a>'
        ),
        "https://repo.example.edu/ujrr/handle/123456789/1": (
            '<meta name="DC.title" content="Too old">'
            '<meta name="DCTERMS.issued" content="2015">'
        ),
        "https://repo.example.edu/ujrr/handle/123456789/2": (
            '<meta name="DC.title" content="Start year">'
            '<meta name="citation_date" content="2016-02-10">'
        ),
        "https://repo.example.edu/ujrr/handle/123456789/3": (
            '<meta name="DC.title" content="Current">'
            '<meta name="DCTERMS.issued" content="2024">'
        ),
    }

    class FakeResponse:
        status_code = 200

        def __init__(self, text):
            self.text = text

    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResponse(html_pages.get(url, ""))

    collector = HtmlMetaCollector(
        base_url="https://repo.example.edu/ujrr/",
        delay=0,
        session=FakeSession(),
    )

    items = list(collector.iter_items(max_records=1, start_year=2016, end_year=2026))

    assert [item["handle_path"] for item in items] == ["/handle/123456789/2"]


def test_oai_pmh_collector_follows_resumption_tokens_and_skips_deleted():
    responses = [
        """<?xml version="1.0" encoding="UTF-8"?>
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <ListRecords>
            <record>
              <header>
                <identifier>oai:repo:1</identifier>
                <datestamp>2026-01-01</datestamp>
              </header>
              <metadata>
                <oai_dc:dc
                  xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                  xmlns:dc="http://purl.org/dc/elements/1.1/">
                  <dc:title>First record</dc:title>
                  <dc:creator>A. Author</dc:creator>
                </oai_dc:dc>
              </metadata>
            </record>
            <resumptionToken>token-2</resumptionToken>
          </ListRecords>
        </OAI-PMH>""",
        """<?xml version="1.0" encoding="UTF-8"?>
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <ListRecords>
            <record>
              <header status="deleted">
                <identifier>oai:repo:deleted</identifier>
                <datestamp>2026-01-02</datestamp>
              </header>
            </record>
            <record>
              <header>
                <identifier>oai:repo:2</identifier>
                <datestamp>2026-01-03</datestamp>
              </header>
              <metadata>
                <oai_dc:dc
                  xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                  xmlns:dc="http://purl.org/dc/elements/1.1/">
                  <dc:title>Second record</dc:title>
                </oai_dc:dc>
              </metadata>
            </record>
          </ListRecords>
        </OAI-PMH>""",
    ]
    calls = []

    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, *, params, timeout, verify):
            calls.append(params)
            return FakeResponse(responses.pop(0))

    collector = OaiPmhCollector(
        base_url="https://repo.example.edu/oai",
        session=FakeSession(),
    )

    records = list(collector.iter_records())

    assert [record["oai_identifier"] for record in records] == [
        "oai:repo:1",
        "oai:repo:2",
    ]
    assert records[0]["title"] == ["First record"]
    assert calls == [
        {"verb": "ListRecords", "metadataPrefix": "oai_dc"},
        {"verb": "ListRecords", "resumptionToken": "token-2"},
    ]


def test_oai_pmh_collector_rejects_repeated_resumption_token():
    response = """<?xml version="1.0" encoding="UTF-8"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <ListRecords>
        <record>
          <header>
            <identifier>oai:repo:1</identifier>
            <datestamp>2026-01-01</datestamp>
          </header>
        </record>
        <resumptionToken>stuck-token</resumptionToken>
      </ListRecords>
    </OAI-PMH>"""

    class FakeResponse:
        text = response

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, *, params, timeout, verify):
            return FakeResponse()

    collector = OaiPmhCollector(
        base_url="https://repo.example.edu/oai",
        session=FakeSession(),
    )

    with pytest.raises(RuntimeError, match="resumption token repeated"):
        list(collector.iter_records())


def test_raw_repository_doi_helpers_require_valid_doi_values():
    assert has_oai_dc_doi(
        {"identifier": ["https://repo.example.edu/1", "doi:10.1000/example"]}
    )
    assert not has_oai_dc_doi({"identifier": ["https://repo.example.edu/1"]})

    assert has_dspace_rest_doi(
        {
            "metadata": {
                "dc.identifier.doi": ["https://doi.org/10.1000/rest"],
            }
        }
    )
    assert not has_dspace_rest_doi(
        {
            "metadata": {
                "dc.identifier.uri": ["https://repo.example.edu/items/1"],
            }
        }
    )

    assert has_html_meta_doi(
        {
            "meta": {
                "DC.identifier": ["DOI: 10.1000/html"],
            }
        }
    )
    assert not has_html_meta_doi(
        {
            "meta": {
                "DC.identifier": ["not-a-doi"],
            }
        }
    )


def test_sitemap_collector_follows_indexes_and_filters_item_urls():
    sitemap_index = b"""<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://repo.example.edu/sitemap_1.xml</loc></sitemap>
    </sitemapindex>"""
    sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://repo.example.edu/handle/123456789/1</loc></url>
      <url><loc>https://repo.example.edu/community-list</loc></url>
      <url><loc>https://repo.example.edu/items/2</loc></url>
    </urlset>"""

    class FakeResponse:
        status_code = 200

        def __init__(self, content):
            self.content = content

    class FakeSession:
        def get(self, url, *, timeout):
            if url == "https://repo.example.edu/sitemap_index.xml":
                return FakeResponse(sitemap_index)
            if url == "https://repo.example.edu/sitemap_1.xml":
                return FakeResponse(sitemap)
            return FakeResponse(b"")

    collector = SitemapCollector(
        repository_url="https://repo.example.edu/repository",
        session=FakeSession(),
    )

    assert collector.iter_item_urls() == [
        "https://repo.example.edu/handle/123456789/1",
        "https://repo.example.edu/items/2",
    ]
