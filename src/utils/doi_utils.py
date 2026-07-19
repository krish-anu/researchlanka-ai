from __future__ import annotations

import re
import pandas as pd


def normalize_doi(doi):

    if doi is None or pd.isna(doi):
        return None

    doi = str(doi).strip().lower()

    doi = re.sub(
        r"^(https?://)?(dx\.)?doi\.org/",
        "",
        doi,
        flags=re.I,
    )

    doi = re.sub(
        r"^doi:\s*",
        "",
        doi,
        flags=re.I,
    )

    doi = doi.replace(" ", "")

    doi = doi.rstrip(".,;:)]}")

    return doi.strip()


def extract_unique_dois(
    df: pd.DataFrame,
    column: str = "doi",
) -> list[str]:

    return df[column].apply(normalize_doi).dropna().unique().tolist()
