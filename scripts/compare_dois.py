from pathlib import Path
import logging
import pandas as pd
import re
import sys

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.file_naming import dataset_filename

OPENALEX_PATH = PROJECT_ROOT / "data" / "raw" / "openalex" / dataset_filename(
    "openalex",
    "sri_lanka",
    "works",
    "csv",
)
CROSSREF_PATH = PROJECT_ROOT / "data" / "processed" / "crossref" / dataset_filename(
    "crossref",
    "sri_lanka",
    "works",
    "csv",
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "doi_comparison"


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


def load_dois(path: Path, column: str) -> pd.DataFrame:
    """
    Load and normalize DOIs from CSV.

    Args:
        path: Path to CSV file.
        column: Column name containing DOI values.

    Returns:
        DataFrame with normalized DOIs.

    Raises:
        FileNotFoundError: If CSV file doesn't exist.
        ValueError: If column doesn't exist in CSV.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)

    if column not in df.columns:
        available = ", ".join(df.columns)
        raise ValueError(
            f"Column '{column}' not found in {path}. Available: {available}"
        )

    df["doi_clean"] = df[column].apply(normalize_doi)
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
        oa = load_dois(OPENALEX_PATH, "doi")
        cr = load_dois(CROSSREF_PATH, "DOI")
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Error loading data: {e}")
        raise

    oa_dois = set(oa["doi_clean"])
    cr_dois = set(cr["doi_clean"])

    common = oa_dois & cr_dois
    openalex_only = oa_dois - cr_dois
    crossref_only = cr_dois - oa_dois

    print(f"OpenAlex DOI: {len(oa_dois)}")
    print(f"Crossref DOI: {len(cr_dois)}")
    print(f"Common: {len(common)}")
    print(f"OpenAlex only: {len(openalex_only)}")
    print(f"Crossref only: {len(crossref_only)}")

    pd.Series(sorted(openalex_only)).to_csv(
        OUTPUT_DIR
        / dataset_filename("doi_comparison", "openalex_only", "dois", "txt"),
        index=False,
        header=False,
    )
    pd.Series(sorted(crossref_only)).to_csv(
        OUTPUT_DIR
        / dataset_filename("doi_comparison", "crossref_only", "dois", "txt"),
        index=False,
        header=False,
)

    pd.Series(sorted(common)).to_csv(
        OUTPUT_DIR / dataset_filename("doi_comparison", "common", "dois", "txt"),
        index=False,
        header=False,
    )
    logger.info(f"Saved comparison results to {OUTPUT_DIR}")


if __name__ == "__main__":
    import logging

    main()


# python scripts/collect_crossref.py enrich-dois \
# --doi-file data/processed/doi_comparison/doi_comparison_openalex_only_dois.txt \
# --email your_email@example.com
