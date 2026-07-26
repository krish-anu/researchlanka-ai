"""PubMed (NCBI E-utilities) collector for affiliation-scoped searches.

Second recovery route for institutions whose repository is unreachable.
PubMed's ``[Affiliation]`` field search is exact enough to need no local
re-filtering (unlike Crossref's fuzzy affiliation query), and the records
carry abstracts and MeSH terms, which repository Dublin Core rarely does.

Only medical/life-science output is indexed here, so this complements
rather than replaces the Crossref route.

NCBI asks for <=3 requests/second without an API key; the default delay
keeps well inside that.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def create_session() -> requests.Session:
    """Session that retries E-utilities' frequent transient failures.

    NCBI returns sporadic 502/429 under load even well inside the rate
    limit, and a multi-batch efetch run is long enough to meet one.
    """

    retry_strategy = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    text = "".join(element.itertext()).strip()
    return text or None


@dataclass
class PubmedCollector:
    """Search PubMed by query and fetch full records in batches."""

    email: str | None = None
    api_key: str | None = None
    tool: str = "researchlanka"
    timeout: int = 60
    batch_size: int = 200
    delay: float = 0.4
    base_url: str = EUTILS_BASE_URL
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_session()

    def _params(self, **extra: Any) -> dict[str, Any]:
        params: dict[str, Any] = {"tool": self.tool, **extra}
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def search_ids(self, query: str, *, max_records: int | None = None) -> list[str]:
        """Return every PMID matching the query, paging through esearch."""

        ids: list[str] = []
        retstart = 0
        total: int | None = None

        while True:
            response = self.session.get(
                f"{self.base_url}/esearch.fcgi",
                params=self._params(
                    db="pubmed",
                    term=query,
                    retmode="json",
                    retmax=self.batch_size,
                    retstart=retstart,
                ),
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json().get("esearchresult", {})
            if total is None:
                total = int(result.get("count", 0))
            batch = result.get("idlist") or []
            if not batch:
                break
            ids.extend(batch)
            if max_records is not None and len(ids) >= max_records:
                return ids[:max_records]
            retstart += len(batch)
            if retstart >= total:
                break
            time.sleep(self.delay)

        return ids

    @staticmethod
    def _parse_article(article: ET.Element) -> dict[str, Any]:
        """Flatten one PubmedArticle element into a plain dict."""

        citation = article.find("MedlineCitation")
        if citation is None:
            return {}
        article_node = citation.find("Article")
        if article_node is None:
            article_node = ET.Element("Article")

        authors = []
        affiliations = []
        for author in article_node.findall("./AuthorList/Author"):
            last = _text(author.find("LastName"))
            fore = _text(author.find("ForeName"))
            collective = _text(author.find("CollectiveName"))
            name = collective or " ".join(p for p in (fore, last) if p)
            if name:
                authors.append(name)
            for affiliation in author.findall("./AffiliationInfo/Affiliation"):
                if (value := _text(affiliation)):
                    affiliations.append(value)

        abstract = " ".join(
            part for node in article_node.findall("./Abstract/AbstractText")
            if (part := _text(node))
        )

        pub_date = article_node.find("./Journal/JournalIssue/PubDate")
        year = _text(pub_date.find("Year")) if pub_date is not None else None
        if year is None and pub_date is not None:
            medline_date = _text(pub_date.find("MedlineDate"))
            year = medline_date.split(" ")[0] if medline_date else None

        identifiers = {
            (node.get("IdType") or "").lower(): _text(node)
            for node in article.findall("./PubmedData/ArticleIdList/ArticleId")
        }

        return {
            "pmid": _text(citation.find("PMID")),
            "doi": identifiers.get("doi"),
            "pmc": identifiers.get("pmc"),
            "title": _text(article_node.find("ArticleTitle")),
            "abstract": abstract or None,
            "authors": authors,
            "affiliations": affiliations,
            "journal": _text(article_node.find("./Journal/Title")),
            "issn": _text(article_node.find("./Journal/ISSN")),
            "volume": _text(article_node.find("./Journal/JournalIssue/Volume")),
            "issue": _text(article_node.find("./Journal/JournalIssue/Issue")),
            "pages": _text(article_node.find("./Pagination/MedlinePgn")),
            "publication_year": year,
            "publication_types": [
                value
                for node in article_node.findall("./PublicationTypeList/PublicationType")
                if (value := _text(node))
            ],
            "keywords": [
                value
                for node in citation.findall("./KeywordList/Keyword")
                if (value := _text(node))
            ],
            "mesh_terms": [
                value
                for node in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName")
                if (value := _text(node))
            ],
            "language": _text(article_node.find("Language")),
            "grants": [
                value
                for node in article_node.findall("./GrantList/Grant/Agency")
                if (value := _text(node))
            ],
        }

    def iter_records(self, pmids: list[str]) -> Iterator[dict[str, Any]]:
        """Fetch full records for the given PMIDs, batch by batch."""

        for start in range(0, len(pmids), self.batch_size):
            batch = pmids[start : start + self.batch_size]
            response = self.session.get(
                f"{self.base_url}/efetch.fcgi",
                params=self._params(db="pubmed", id=",".join(batch), retmode="xml"),
                timeout=self.timeout,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for article in root.findall(".//PubmedArticle"):
                record = self._parse_article(article)
                if record:
                    yield record
            time.sleep(self.delay)
