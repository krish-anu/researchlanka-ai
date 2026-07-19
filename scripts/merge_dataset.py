from pathlib import Path

import pandas as pd

OPENALEX_PATH = Path("data/raw/open-alex/open-alex.csv")

CROSSREF_PATH = Path("data/processed/crossref/crossref_enriched.csv")

OUTPUT_PATH = Path("data/final/research_lanka_dataset.csv")

from src.preprocessing.merger import merge_datasets


def main():

    oa = pd.read_csv(OPENALEX_PATH)

    cr = pd.read_csv(CROSSREF_PATH)

    merged = merge_datasets(
        oa,
        cr,
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    merged.to_csv(
        OUTPUT_PATH,
        index=False,
    )


if __name__ == "__main__":
    main()
