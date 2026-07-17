from pathlib import Path
import logging
import pandas as pd
import re

logger = logging.getLogger(__name__)

OPENALEX_PATH = "data/raw/open-alex/open-alex.csv"
CROSSREF_PATH = "data/processed/crossref/lk_works.csv"

OUTPUT_DIR = Path("data/processed/doi_comparison")


def normalize_doi(doi):
    """
    Normalize DOI strings for matching.
    """

    if doi is None or pd.isna(doi):
        return None

    doi = str(doi).strip().lower()

    # Remove DOI URLs
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

    # Remove spaces
    doi = doi.replace(" ", "")

    # Remove citation punctuation
    doi = doi.rstrip(".,;:)]}")

    return doi.strip()

START_YEAR = 2016

def load_dois(
    path: Path,
    doi_column: str,
    year_column: str | None = None,
    start_year: int | None = None,
):

    df = pd.read_csv(path)

    if year_column and start_year:
        df = df[df[year_column] >= start_year]

    df["doi_clean"] = df[doi_column].apply(normalize_doi)

    df = df.dropna(subset=["doi_clean"])

    return df


def main() -> None:
    """Compare DOIs between OpenAlex and Crossref datasets."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        oa = load_dois(
            OPENALEX_PATH, "doi", year_column="publication_year", start_year=2016
        )
        cr = load_dois(CROSSREF_PATH, "DOI")
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Error loading data: {e}")
        raise

    oa_dois = set(
        oa["doi_clean"]
    )


    cr_dois = set(
        cr["doi_clean"]
    )


    missing_in_crossref = (
        oa_dois - cr_dois
    )

    
    pd.Series(sorted(missing_in_crossref)).to_csv(
        OUTPUT_DIR / "openalex_2016_plus_missing_crossref.txt",
        index=False,
        header=False,
    )
    logger.info(f"Saved comparison results to {OUTPUT_DIR}")


if __name__ == "__main__":
    import logging

    main()


# python scripts/collect_crossref.py enrich-dois \
# --doi-file data/processed/doi_comparison/openalex_only_dois.txt \
# --email your_email@example.com
