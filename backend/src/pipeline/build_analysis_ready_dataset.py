"""Build an analysis-ready final dataset and preprocessing issue files."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.build_final_common_dataset import build_publication_key
from src.utils.doi import normalize_doi


DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = date.today().year
DEFAULT_YEAR_SUFFIX = f"{DEFAULT_START_YEAR}_{DEFAULT_END_YEAR}"
DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / f"common_publications_final_{DEFAULT_YEAR_SUFFIX}_multivalue_normalized.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / f"common_publications_final_{DEFAULT_YEAR_SUFFIX}_analysis_ready.csv"
)
DEFAULT_ISSUE_DIR = (
    PROJECT_ROOT / "data" / "processed" / "common" / f"preprocessing_issues_{DEFAULT_YEAR_SUFFIX}"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / f"common_publications_final_{DEFAULT_YEAR_SUFFIX}_analysis_ready_summary.csv"
)

TEXT_COLUMNS = ["title", "abstract", "keywords"]
IDENTIFIER_COLUMNS = [
    "doi",
    "openalex_id",
    "url",
    "pdf_url",
    "author_orcids",
    "issn",
    "issn_l",
    "funder_doi",
    "funder_identifier",
]
NUMERIC_COLUMNS = [
    "author_count",
    "reference_count",
    "reference_count_difference_oa_minus_crossref",
]
DROP_FROM_ANALYSIS_READY = [
    "citation_count",
    "citation_count_difference_oa_minus_crossref",
    "citation_count_divergence_flag",
    "is_referenced_by_count",
    "publication_year",
    "raw_identifiers",
]
NATURALLY_SPARSE_COLUMNS = [
    "abstract",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "license",
    "license_url",
    "pdf_url",
    "author_orcids",
    "article_number",
]
BOOLEAN_COLUMNS = [
    "is_oa",
    "citation_count_divergence_flag",
    "reference_count_divergence_flag",
]
ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dX]$", re.IGNORECASE)
ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-[\dX]{3}[\dX]", re.IGNORECASE)
ROR_RE = re.compile(r"https?://ror\.org/[0-9a-z]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,;:)]}"
TRAILING_SAFE_URL_PUNCTUATION = ".,;:"


def clean_text(value: Any) -> str | None:   
    if pd.isna(value):
        return None

    text = " ".join(str(value).split()).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a", "[]", "{}"}:
        return None
    return text


def normalize_search_text(value: Any) -> Any:
    text = clean_text(value)
    return text.casefold() if text is not None else pd.NA


def split_semicolon_values(value: Any) -> list[str]:
    text = clean_text(value)
    if text is None:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def unique_join(values: list[str]) -> Any:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = clean_text(value)
        if text is None:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return "; ".join(output) if output else pd.NA


def normalize_keywords_for_search(value: Any) -> Any:
    return unique_join([item.casefold() for item in split_semicolon_values(value)])


def normalize_url(value: Any, *, force_https_hosts: set[str] | None = None) -> Any:
    text = clean_text(value)
    if text is None:
        return pd.NA

    text = text.rstrip(TRAILING_SAFE_URL_PUNCTUATION)
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        return text

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if force_https_hosts and netloc in force_https_hosts:
        scheme = "https"

    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def normalize_openalex_id(value: Any) -> Any:
    text = clean_text(value)
    if text is None:
        return pd.NA

    text = normalize_url(text)
    if pd.isna(text):
        return pd.NA

    match = re.search(r"/([WAIVSFC]\d+)$", str(text), flags=re.IGNORECASE)
    if match:
        return f"https://openalex.org/{match.group(1).upper()}"
    return text


def normalize_orcid_item(value: str) -> str | None:
    match = ORCID_RE.search(value)
    if not match:
        return None
    return f"https://orcid.org/{match.group(0).upper()}"


def normalize_orcids(value: Any) -> Any:
    return unique_join([orcid for item in split_semicolon_values(value) if (orcid := normalize_orcid_item(item))])


def normalize_issn_item(value: str) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.upper().replace(" ", "")
    if re.fullmatch(r"\d{7}[\dX]", text):
        text = f"{text[:4]}-{text[4:]}"
    return text if ISSN_RE.fullmatch(text) else None


def normalize_issns(value: Any) -> Any:
    return unique_join([issn for item in split_semicolon_values(value) if (issn := normalize_issn_item(item))])


def normalize_doi_cell(value: Any) -> Any:
    return unique_join([doi for item in split_semicolon_values(value) if (doi := normalize_doi(item))])


def normalize_identifier_cell(column: str, value: Any) -> Any:
    if column in {"doi", "funder_doi"}:
        return normalize_doi_cell(value)
    if column == "openalex_id":
        return normalize_openalex_id(value)
    if column in {"url", "pdf_url"}:
        return normalize_url(value)
    if column == "author_orcids":
        return normalize_orcids(value)
    if column in {"issn", "issn_l"}:
        return normalize_issns(value)
    if column == "funder_identifier":
        identifiers: list[str] = []
        for item in split_semicolon_values(value):
            doi = normalize_doi(item)
            if doi:
                identifiers.append(doi)
                continue
            ror_match = ROR_RE.search(item)
            if ror_match:
                identifiers.append(str(normalize_url(ror_match.group(0), force_https_hosts={"ror.org"})))
                continue
            normalized = normalize_url(item)
            if not pd.isna(normalized):
                identifiers.append(str(normalized))
        return unique_join(identifiers)
    raise ValueError(f"Unsupported identifier column: {column}")


def normalize_bool(value: Any) -> Any:
    text = clean_text(value)
    if text is None:
        return pd.NA

    lowered = text.casefold()
    if lowered in {"true", "t", "yes", "y", "1"}:
        return True
    if lowered in {"false", "f", "no", "n", "0"}:
        return False
    return pd.NA


def normalize_license(value: Any) -> Any:
    text = clean_text(value)
    if text is None:
        return pd.NA
    return text.casefold().replace("_", "-").replace(" ", "-")


def normalize_oa_status(value: Any) -> str:
    text = clean_text(value)
    return text.casefold().replace(" ", "-") if text is not None else "unknown"


def looks_all_caps_name(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def titlecase_author_name(value: str) -> str:
    return " ".join(part.capitalize() if len(part) > 1 else part for part in value.split())


def normalize_author_name(value: str) -> str | None:
    text = clean_text(value)
    if text is None:
        return None

    if "," in text and text.count(",") == 1:
        family, given = [part.strip() for part in text.split(",", maxsplit=1)]
        if family and given:
            text = f"{given} {family}"

    if looks_all_caps_name(text):
        text = titlecase_author_name(text)

    return clean_text(text)


def normalize_authors_for_analysis(value: Any) -> Any:
    return unique_join([name for item in split_semicolon_values(value) if (name := normalize_author_name(item))])


def issue_record(
    *,
    category: str,
    row_number: int | None,
    row: pd.Series | None,
    column: str,
    issue: str,
    original_value: Any = pd.NA,
    cleaned_value: Any = pd.NA,
) -> dict[str, Any]:
    publication_key = build_publication_key(row, row_number) if row is not None and row_number is not None else pd.NA
    return {
        "category": category,
        "publication_key": publication_key,
        "publication_row_number": row_number,
        "column": column,
        "issue": issue,
        "original_value": original_value,
        "cleaned_value": cleaned_value,
    }


def add_search_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    if "title" in cleaned.columns:
        cleaned["title_search_text"] = cleaned["title"].map(normalize_search_text)
    if "abstract" in cleaned.columns:
        cleaned["abstract_search_text"] = cleaned["abstract"].map(normalize_search_text)
        cleaned["abstract_missing_flag"] = cleaned["abstract_search_text"].isna()
    if "keywords" in cleaned.columns:
        cleaned["keywords_search_text"] = cleaned["keywords"].map(normalize_keywords_for_search)
    return cleaned


def normalize_identifiers(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for column in IDENTIFIER_COLUMNS:
        if column in cleaned.columns:
            cleaned[column] = cleaned[column].map(lambda value, col=column: normalize_identifier_cell(col, value))
    return cleaned


def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for column in NUMERIC_COLUMNS:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce").astype("Int64")
    return cleaned


def add_missing_flags(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for column in NATURALLY_SPARSE_COLUMNS:
        if column in cleaned.columns:
            cleaned[f"{column}_missing_flag"] = cleaned[column].map(clean_text).isna()
    return cleaned


def normalize_author_fields(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    if "authors" in cleaned.columns:
        cleaned["authors_clean"] = cleaned["authors"].map(normalize_authors_for_analysis)
    if "author_orcids" in cleaned.columns:
        cleaned["author_disambiguation_available_flag"] = ~cleaned["author_orcids"].map(clean_text).isna()
    return cleaned


def normalize_oa_license_fields(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    if "oa_status" in cleaned.columns:
        cleaned["oa_status"] = cleaned["oa_status"].map(normalize_oa_status)
    if "is_oa" in cleaned.columns:
        cleaned["is_oa"] = cleaned["is_oa"].map(normalize_bool).astype("object")
    for column in ["reference_count_divergence_flag"]:
        if column in cleaned.columns:
            cleaned[column] = cleaned[column].map(normalize_bool).astype("object")
    if "license" in cleaned.columns:
        cleaned["license"] = cleaned["license"].map(normalize_license)
    if "license_url" in cleaned.columns:
        cleaned["license_url"] = cleaned["license_url"].map(
            lambda value: normalize_url(value, force_https_hosts={"creativecommons.org", "doi.wiley.com"})
        )
    return cleaned


def build_issue_logs(original: pd.DataFrame, cleaned: pd.DataFrame) -> dict[str, pd.DataFrame]:
    issues: dict[str, list[dict[str, Any]]] = {
        "text_issues": [],
        "identifier_issues": [],
        "numeric_issues": [],
        "missingness_issues": [],
        "author_issues": [],
        "oa_license_issues": [],
    }

    row_lookup = [
        pd.Series(dict(zip(original.columns, row, strict=True)))
        for row in original.itertuples(index=False)
    ]

    for row_number, row in enumerate(row_lookup, start=1):
        cleaned_row = cleaned.iloc[row_number - 1]

        for column in TEXT_COLUMNS:
            if column not in original.columns:
                continue
            target_column = f"{column}_search_text"
            original_value = row.get(column, pd.NA)
            cleaned_value = cleaned_row.get(target_column, pd.NA)
            if clean_text(original_value) is None:
                issues["text_issues"].append(
                    issue_record(
                        category="text",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="missing_text",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )
            elif str(original_value) != str(cleaned_value):
                issues["text_issues"].append(
                    issue_record(
                        category="text",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="search_text_normalized",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )

        for column in IDENTIFIER_COLUMNS:
            if column not in original.columns:
                continue
            original_value = row.get(column, pd.NA)
            cleaned_value = cleaned_row.get(column, pd.NA)
            if clean_text(original_value) is not None and clean_text(cleaned_value) is None:
                issues["identifier_issues"].append(
                    issue_record(
                        category="identifier",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="invalid_identifier_removed",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )
            elif clean_text(original_value) != clean_text(cleaned_value):
                issues["identifier_issues"].append(
                    issue_record(
                        category="identifier",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="identifier_normalized",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )

        for column in NUMERIC_COLUMNS:
            if column not in original.columns:
                continue
            original_value = row.get(column, pd.NA)
            cleaned_value = cleaned_row.get(column, pd.NA)
            if clean_text(original_value) is not None and pd.isna(cleaned_value):
                issues["numeric_issues"].append(
                    issue_record(
                        category="numeric",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="non_numeric_value",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )

        if "authors" in original.columns and clean_text(row.get("authors")) != clean_text(cleaned_row.get("authors_clean")):
            issues["author_issues"].append(
                issue_record(
                    category="author",
                    row_number=row_number,
                    row=row,
                    column="authors",
                    issue="author_name_cleaned",
                    original_value=row.get("authors", pd.NA),
                    cleaned_value=cleaned_row.get("authors_clean", pd.NA),
                )
            )

        if "author_orcids" in original.columns and clean_text(row.get("authors")) is not None and clean_text(row.get("author_orcids")) is None:
            issues["author_issues"].append(
                issue_record(
                    category="author",
                    row_number=row_number,
                    row=row,
                    column="author_orcids",
                    issue="author_disambiguation_missing_orcid",
                    original_value=row.get("author_orcids", pd.NA),
                    cleaned_value=cleaned_row.get("author_disambiguation_available_flag", pd.NA),
                )
            )

        for column in ["oa_status", "is_oa", "license", "license_url"]:
            if column not in original.columns:
                continue
            original_value = row.get(column, pd.NA)
            cleaned_value = cleaned_row.get(column, pd.NA)
            if clean_text(original_value) is None:
                issues["oa_license_issues"].append(
                    issue_record(
                        category="oa_license",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="missing_oa_license_value",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )
            elif clean_text(original_value) != clean_text(cleaned_value):
                issues["oa_license_issues"].append(
                    issue_record(
                        category="oa_license",
                        row_number=row_number,
                        row=row,
                        column=column,
                        issue="oa_license_value_normalized",
                        original_value=original_value,
                        cleaned_value=cleaned_value,
                    )
                )

    for column in NATURALLY_SPARSE_COLUMNS:
        if column not in original.columns:
            continue
        missing = int(original[column].map(clean_text).isna().sum())
        issues["missingness_issues"].append(
            issue_record(
                category="missingness",
                row_number=None,
                row=None,
                column=column,
                issue="naturally_sparse_column_missing_count",
                original_value=missing,
                cleaned_value=f"{column}_missing_flag",
            )
        )

    return {name: pd.DataFrame(rows) for name, rows in issues.items()}


def build_analysis_ready_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = add_search_text_columns(df)
    cleaned = normalize_identifiers(cleaned)
    cleaned = convert_numeric_columns(cleaned)
    cleaned = add_missing_flags(cleaned)
    cleaned = normalize_author_fields(cleaned)
    cleaned = normalize_oa_license_fields(cleaned)
    columns_to_drop = [column for column in DROP_FROM_ANALYSIS_READY if column in cleaned.columns]
    if columns_to_drop:
        cleaned = cleaned.drop(columns=columns_to_drop)
    return cleaned


def write_issue_files(issue_dir: Path, issue_logs: dict[str, pd.DataFrame]) -> int:
    issue_dir.mkdir(parents=True, exist_ok=True)
    all_issues = []
    total_rows = 0

    for name, issue_df in issue_logs.items():
        output_path = issue_dir / f"{name}.csv"
        issue_df.to_csv(output_path, index=False)
        total_rows += len(issue_df)
        all_issues.append(issue_df)

    combined = pd.concat(all_issues, ignore_index=True) if all_issues else pd.DataFrame()
    combined.to_csv(issue_dir / "all_preprocessing_issues.csv", index=False)
    return total_rows


def build_analysis_ready_dataset(
    input_csv: Path,
    output_csv: Path,
    issue_dir: Path,
    summary_csv: Path,
) -> tuple[pd.DataFrame, int]:
    df = pd.read_csv(input_csv, dtype="object", low_memory=False)
    cleaned = build_analysis_ready_dataframe(df)
    issue_logs = build_issue_logs(df, cleaned)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(output_csv, index=False)
    issue_rows = write_issue_files(issue_dir, issue_logs)

    summary_rows = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "issue_dir", "value": str(issue_dir)},
        {"metric": "input_rows", "value": len(df)},
        {"metric": "input_columns", "value": len(df.columns)},
        {"metric": "output_rows", "value": len(cleaned)},
        {"metric": "output_columns", "value": len(cleaned.columns)},
        {"metric": "issue_rows", "value": issue_rows},
        {"metric": "text_helper_columns", "value": "title_search_text; abstract_search_text; keywords_search_text"},
        {"metric": "missing_flag_columns", "value": "; ".join(f"{column}_missing_flag" for column in NATURALLY_SPARSE_COLUMNS)},
        {"metric": "author_helper_columns", "value": "authors_clean; author_disambiguation_available_flag"},
    ]
    pd.DataFrame(summary_rows).to_csv(summary_csv, index=False)

    issue_summary = pd.DataFrame(
        [{"issue_file": name, "rows": len(issue_df)} for name, issue_df in issue_logs.items()]
    )
    issue_summary.to_csv(issue_dir / "issue_file_summary.csv", index=False)

    return cleaned, issue_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an analysis-ready dataset and separate preprocessing issue files."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--issue-dir", type=Path, default=DEFAULT_ISSUE_DIR)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cleaned, issue_rows = build_analysis_ready_dataset(
        args.input_csv,
        args.output_csv,
        args.issue_dir,
        args.summary_csv,
    )

    print("Done.")
    print(f"  Rows: {len(cleaned):,}")
    print(f"  Columns: {len(cleaned.columns):,}")
    print(f"  Issue rows: {issue_rows:,}")
    print(f"  Analysis-ready dataset: {args.output_csv}")
    print(f"  Issue files: {args.issue_dir}")
    print(f"  Summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
