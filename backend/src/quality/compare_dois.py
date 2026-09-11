"""Compare DOI coverage and validity between the OpenAlex and Crossref pulls.

Reads the two raw collections, normalizes every DOI to the same form, and
reports how many are present, valid, shared, and unique to each source. Used
to sanity-check a collection run before the merge stage, where a DOI gap
silently becomes a deduplication miss.

Run from the backend folder::

    python -m src.quality.compare_dois
"""

from pathlib import Path
import logging
import pandas as pd
import sys

logger = logging.getLogger(__name__)

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.file_naming import dataset_filename
from src.utils.doi import is_valid_doi, normalize_doi

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
    df = df[df["doi_clean"].apply(is_valid_doi)]

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


# python scripts/collection/collect_crossref.py enrich-dois \
# --doi-file data/processed/doi_comparison/doi_comparison_openalex_only_dois.txt \
# --email your_email@example.com
