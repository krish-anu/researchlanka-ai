"""
DOI based Crossref enrichment.
"""

from pathlib import Path
import json

import pandas as pd

from src.collectors.crossref_collector import CrossrefCollector
from src.preprocessing.crossref_normalizer import normalize_crossref
from src.utils.doi_utils import extract_unique_dois


OPENALEX_PATH = Path("data/raw/open-alex/open-alex.csv")

OUTPUT_PATH = Path("data/processed/crossref/crossref_enriched.jsonl")


def main():

    df = pd.read_csv(OPENALEX_PATH)


    dois = extract_unique_dois(df)

    collector = CrossrefCollector()

    for doi in dois:
        work = collector.fetch_work_by_doi(doi)

    

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as out:
        for doi in dois:
            work = collector.fetch_work_by_doi(doi)

            if not work:
                continue

            normalized = normalize_crossref(work)

            out.write(
                json.dumps(
                    normalized,
                    ensure_ascii=False,
                )
                + "\n"
            )


if __name__ == "__main__":
    main()
