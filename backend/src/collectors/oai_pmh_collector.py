"""Generic OAI-PMH harvester for the Sri Lankan repository targets.

Works against any standards-compliant OAI-PMH endpoint (DSpace, OJS, ...).
Handles resumption-token pagination and parses Dublin Core (oai_dc) records
into plain dicts. Metadata-schema unification into the project's common
publication schema happens downstream, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator
from xml.etree import ElementTree

import requests

from src.collectors.http import create_retry_session

OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
OAI_DC_NS = "{http://www.openarchives.org/OAI/2.0/oai_dc/}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"

# All fifteen unqualified Dublin Core elements.
DC_FIELDS = [
    "title",
    "creator",
    "subject",
    "description",
    "publisher",
    "contributor",
    "date",
    "type",
    "format",
    "identifier",
    "source",
    "language",
    "relation",
    "coverage",
    "rights",
]


class OaiPmhError(RuntimeError):
    """Raised when an OAI-PMH endpoint returns an <error> response.

    Carries the OAI error ``code`` (e.g. "noRecordsMatch") so callers can
    tell a benign "nothing in this range" apart from a real fault.
    """

    def __init__(self, code: str, message: str | None) -> None:
        self.code = code
        super().__init__(f"OAI-PMH error [{code}]: {message}")


@dataclass
class OaiPmhCollector:
    """Harvest records from a single OAI-PMH endpoint."""

    base_url: str
    metadata_prefix: str = "oai_dc"
    timeout: int = 30
    session: requests.Session | None = None
    # Some institutions (e.g. SLIIT) have a live endpoint behind a broken/
    # misconfigured TLS certificate -- see repositories.json ssl_verify_failed.
    # Only set this False for hosts already confirmed reachable-but-bad-cert
    # by scripts/validate_repositories.py; never as a blanket default.
    verify_ssl: bool = True

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_retry_session()

    def _request(self, params: dict[str, str]) -> ElementTree.Element:
        response = self.session.get(
            self.base_url, params=params, timeout=self.timeout, verify=self.verify_ssl
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)

        error = root.find(f"{OAI_NS}error")
        if error is not None:
            raise OaiPmhError(error.get("code", "unknown"), error.text)

        return root

    def _parse_dc_record(self, record_el: ElementTree.Element) -> dict[str, Any]:
        header = record_el.find(f"{OAI_NS}header")
        status = header.get("status") if header is not None else None
        identifier_el = header.find(f"{OAI_NS}identifier") if header is not None else None
        datestamp_el = header.find(f"{OAI_NS}datestamp") if header is not None else None
        set_specs = (
            [el.text for el in header.findall(f"{OAI_NS}setSpec") if el.text]
            if header is not None
            else []
        )

        record: dict[str, Any] = {
            "oai_identifier": identifier_el.text if identifier_el is not None else None,
            "datestamp": datestamp_el.text if datestamp_el is not None else None,
            "set_specs": set_specs,
            "deleted": status == "deleted",
        }

        if record["deleted"]:
            return record

        metadata_el = record_el.find(f"{OAI_NS}metadata")
        if metadata_el is None:
            return record

        dc_el = metadata_el.find(f"{OAI_DC_NS}dc")
        if dc_el is None:
            return record

        for field in DC_FIELDS:
            values = [el.text for el in dc_el.findall(f"{DC_NS}{field}") if el.text]
            if values:
                record[field] = values

        return record

    def _fetch_page(
        self,
        *,
        resumption_token: str | None,
        set_spec: str | None,
        from_date: str | None,
        until_date: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if resumption_token:
            params = {"verb": "ListRecords", "resumptionToken": resumption_token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": self.metadata_prefix}
            if set_spec:
                params["set"] = set_spec
            if from_date:
                params["from"] = from_date
            if until_date:
                params["until"] = until_date

        root = self._request(params)

        list_records = root.find(f"{OAI_NS}ListRecords")
        if list_records is None:
            return [], None

        records = [
            self._parse_dc_record(record_el)
            for record_el in list_records.findall(f"{OAI_NS}record")
        ]

        token_el = list_records.find(f"{OAI_NS}resumptionToken")
        next_token = None
        if token_el is not None and token_el.text:
            next_token = token_el.text

        return records, next_token

    def _fetch_sets_page(self, *, resumption_token: str | None) -> tuple[list[str], str | None]:
        if resumption_token:
            params = {"verb": "ListSets", "resumptionToken": resumption_token}
        else:
            params = {"verb": "ListSets"}

        root = self._request(params)

        list_sets = root.find(f"{OAI_NS}ListSets")
        if list_sets is None:
            return [], None

        set_specs = [
            spec_el.text
            for set_el in list_sets.findall(f"{OAI_NS}set")
            for spec_el in [set_el.find(f"{OAI_NS}setSpec")]
            if spec_el is not None and spec_el.text
        ]

        token_el = list_sets.find(f"{OAI_NS}resumptionToken")
        next_token = None
        if token_el is not None and token_el.text:
            next_token = token_el.text

        return set_specs, next_token

    def iter_set_specs(self) -> Iterator[str]:
        """Yield every OAI-PMH setSpec, following ListSets resumption tokens."""

        resumption_token: str | None = None
        first_page = True
        seen_tokens: set[str] = set()

        while first_page or resumption_token:
            first_page = False
            set_specs, resumption_token = self._fetch_sets_page(
                resumption_token=resumption_token
            )

            yield from set_specs

            if resumption_token is not None:
                if resumption_token in seen_tokens:
                    raise RuntimeError(
                        f"OAI-PMH ListSets resumption token repeated: {resumption_token}"
                    )
                seen_tokens.add(resumption_token)

    def iter_records(
        self,
        *,
        set_spec: str | None = None,
        from_date: str | None = None,
        until_date: str | None = None,
        max_records: int | None = None,
        include_deleted: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Yield every record from this endpoint, following resumption tokens."""

        resumption_token: str | None = None
        records_seen = 0
        first_page = True
        seen_tokens: set[str] = set()

        while first_page or resumption_token:
            first_page = False
            records, resumption_token = self._fetch_page(
                resumption_token=resumption_token,
                set_spec=set_spec,
                from_date=from_date,
                until_date=until_date,
            )

            for record in records:
                if not include_deleted and record.get("deleted"):
                    continue
                if max_records is not None and records_seen >= max_records:
                    return
                records_seen += 1
                yield record

            if resumption_token is not None:
                if resumption_token in seen_tokens:
                    raise RuntimeError(
                        f"OAI-PMH resumption token repeated: {resumption_token}"
                    )
                seen_tokens.add(resumption_token)
