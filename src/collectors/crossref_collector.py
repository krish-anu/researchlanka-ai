from __future__ import annotations

from dataclasses import dataclass,field
from typing import Any,Iterator 

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from preprocessing.crossref_normalizer import reduce_work

CROSSREF_BASE_URL = "https://api.crossref.org"
USER_AGENT = ("SriLankaCollector/1.0")

KEEP_TYPES = {
    "journal-article",
    "proceedings-article",
    "posted-content",
}

# shift to util?
def create_session(
    user_agent: str,
) -> requests.Session:

    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    session = requests.Session()

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount("https://", adapter)

    session.headers.update({"User-Agent": user_agent})

    return session

@dataclass
class CrossrefCollector:
    """
        Fetch Sri Lankan publication records from Crossref.
    """
    email: str | None = None
    timeout:int =60
    base_url:str = CROSSREF_BASE_URL
    user_agent:str=USER_AGENT
    session:requests.Session=field(init=False)

    keep_types:set[str]|None=None

    def __post_init__(self):
        user_agent = self.user_agent

        if self.email:
            user_agent = (
                f"{self.user_agent} "
                f"(mailto:{self.email})"
            )

        self.session = create_session(user_agent)
        if self.keep_types is None:
            self.keep_types=KEEP_TYPES

    def fetch_works(
        self,
        *,
        affiliation_query:str,
        filters:list[str] | None=None,
        rows:int=100,
        cursor:str="*",
    )->dict[str,Any]:

        params={
            "query.affiliation":affiliation_query,
            "rows":rows,
            "cursor":cursor,
            "cursor-max":10000,
        }

        if filters:
            params["filter"]=",".join(filters)

        response=self.session.get(
            f"{self.base_url}/works",
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()

    def iter_works(
        self,
        *,
        affiliation_query:str,
        filters:list[str]|None=None,
        rows:int=100,
        max_records:int|None=None,
    )->Iterator[dict[str,Any]]:
       
        cursor="*"

        records_seen=0

        while cursor:
            response=self.fetch_works(
                affiliation_query=affiliation_query,
                filters=filters,
                rows=rows,
                cursor=cursor,
            )

            message=response.get("message",{})
            items=message.get("items",[])

            if not items:
                break
            
            for work in items:
                if(self.keep_types and work.get("type") not in self.keep_types):
                    continue
                if(max_records is not None and records_seen>=max_records):
                    return
                records_seen+=1

                yield reduce_work(work)

            cursor=message.get("next-cursor")
            
            if not cursor:
                break

