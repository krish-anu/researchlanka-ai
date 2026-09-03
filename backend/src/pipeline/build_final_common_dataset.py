"""Build a clean final publication dataset from the merged common CSV.

This script applies the decisions documented in
docs/07_last_26_columns_final_dataset_decisions.md:

* keep best-available reference counts in the main dataset
* drop citation_count from the main dataset
* move source-specific count comparison fields to an audit sidecar
* normalize funder identifiers
* deduplicate selected semicolon-separated fields
* move Crossref reference-list payloads to a sidecar table
* drop sparse event fields and raw audit JSON from the main dataset

It also applies the decisions documented in
docs/08_columns_26_50_final_dataset_decisions.md:

* drop container_title and source_name, which duplicate journal exactly
* drop page, which is derivable from first_page and last_page
* drop rights, which holds a single constant value
* drop editors and publisher_location, which are too sparse to analyze

It also applies the decisions documented in
docs/09_columns_1_25_final_dataset_decisions.md:

* drop landing_page_url, publication_type, and author_names, which duplicate
  url, type, and authors exactly
* drop created_date and published_date from the main dataset because they add
  no coverage beyond publication_date
* drop subtitle, original_title, and subtype, which are too sparse to analyze
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.kaggle_merge_common_dataset import (
    OWNERSHIP_POLICY_VERSION,
    is_blank,
    normalize_doi,
)


DEFAULT_INPUT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_deduplicated.csv"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_REFERENCES_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "publication_references.csv"
DEFAULT_COUNT_AUDIT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "publication_count_audit.csv"
DEFAULT_SUMMARY_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_summary.csv"
DEFAULT_REVIEW_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_ownership_review.csv"
DEFAULT_EXCLUDED_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_ownership_excluded.csv"
DEFAULT_VERIFIED_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_verified_sri_lanka_owned.csv"

FINAL_MAIN_COLUMNS = [
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "openalex_id",
    "doi",
    "url",
    "pdf_url",
    "title",
    "abstract",
    "keywords",
    "publication_year",
    "publication_date",
    "type",
    "authors",
    "author_ids",
    "author_count",
    "author_affiliations",
    "author_orcids",
    "author_disambiguation_level",
    "sri_lankan_authors",
    "contributors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "ownership_decision",
    "ownership_class",
    "ownership_confidence",
    "ownership_reason",
    "ownership_evidence",
    "lead_country",
    "corresponding_author_countries",
    "has_sri_lankan_participant",
    "has_foreign_participant",
    "needs_manual_review",
    "ownership_policy_version",
    "publisher",
    "journal",
    "source_type",
    "issn",
    "issn_l",
    "volume",
    "issue",
    "first_page",
    "last_page",
    "article_number",
    "language",
    "license",
    "license_url",
    "oa_status",
    "is_oa",
    "reference_count",
    "concepts",
    "topics",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "source_set_specs",
    "raw_identifiers",
    "citation_count_difference_oa_minus_crossref",
    "citation_count_divergence_flag",
    "reference_count_difference_oa_minus_crossref",
    "reference_count_divergence_flag",
]

# Columns 51-76, per docs/07_last_26_columns_final_dataset_decisions.md.
DROP_FROM_MAIN = [
    "is_referenced_by_count",
    "referenced_works_count",
    "references_json",
    "event_name",
    "event_acronym",
    "event_location",
    "event_start_date",
    "event_end_date",
    "event_sponsor",
    "raw_source_json",
    # Columns 26-50, per docs/08_columns_26_50_final_dataset_decisions.md.
    "container_title",
    "source_name",
    "page",
    "rights",
    "editors",
    "publisher_location",
    # Columns 1-25, per docs/09_columns_1_25_final_dataset_decisions.md.
    "landing_page_url",
    "subtitle",
    "original_title",
    "created_date",
    "published_date",
    "subtype",
    "publication_type",
    "author_names",
]

MULTI_VALUE_COLUMNS = [
    "concepts",
    "topics",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "source_set_specs",
    "raw_identifiers",
]

TRAILING_URL_PUNCTUATION = ".,;:)]}"
ROR_RE = re.compile(r"https?://ror\.org/[0-9a-z]+", re.IGNORECASE)


def clean_text(value: Any) -> str | None:
    if is_blank(value):
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def split_semicolon_values(value: Any) -> list[str]:
    text = clean_text(value)
    if text is None:
        return []

    return [part.strip() for part in text.split(";") if part.strip()]


def unique_join(values: list[str]) -> str | pd.NA:
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


def normalize_url_like(value: str) -> str:
    return value.strip().rstrip(TRAILING_URL_PUNCTUATION)


def normalize_multi_value_item(value: str, *, doi_only: bool = False) -> str | None:
    doi = normalize_doi(value)
    if not is_blank(doi):
        return str(doi)

    if doi_only:
        return None

    ror_match = ROR_RE.search(value)
    if ror_match:
        return normalize_url_like(ror_match.group(0)).lower()

    return normalize_url_like(value)


def normalize_multi_value_cell(value: Any, *, doi_only: bool = False) -> Any:
    normalized = [
        item
        for part in split_semicolon_values(value)
        if (item := normalize_multi_value_item(part, doi_only=doi_only)) is not None
    ]
    return unique_join(normalized)


def parse_structured_value(value: str) -> Any:
    text = value.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except (json.JSONDecodeError, ValueError, SyntaxError):
            continue
    return text


def extract_identifier_values(value: Any) -> list[str]:
    if is_blank(value):
        return []

    if isinstance(value, dict):
        identifier = value.get("id")
        if not is_blank(identifier):
            return [str(identifier)]

        values: list[str] = []
        for item in value.values():
            values.extend(extract_identifier_values(item))
        return values

    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(extract_identifier_values(item))
        return values

    text = clean_text(value)
    return [text] if text is not None else []


def normalize_funder_identifier(value: Any) -> Any:
    identifiers: list[str] = []

    for part in split_semicolon_values(value):
        parsed = parse_structured_value(part)
        for identifier in extract_identifier_values(parsed):
            normalized = normalize_multi_value_item(identifier)
            if normalized is not None:
                identifiers.append(normalized)

    return unique_join(identifiers)


def coalesce_numeric_columns(df: pd.DataFrame, target: str, candidates: list[str]) -> None:
    result = pd.Series(pd.NA, index=df.index, dtype="object")

    for column in candidates:
        if column not in df.columns:
            continue
        values = pd.to_numeric(df[column], errors="coerce").astype("Int64")
        mask = result.map(is_blank) & values.notna()
        result.loc[mask] = values.loc[mask].astype("object")

    df[target] = result


def numeric_difference(left: Any, right: Any) -> Any:
    left_number = pd.to_numeric(pd.Series([left]), errors="coerce").iloc[0]
    right_number = pd.to_numeric(pd.Series([right]), errors="coerce").iloc[0]

    if pd.isna(left_number) or pd.isna(right_number):
        return pd.NA

    return int(left_number) - int(right_number)


def add_difference_columns(
    df: pd.DataFrame,
    *,
    target_difference: str,
    target_flag: str,
    left: str,
    right: str,
    flag_threshold: int = 1,
) -> None:
    if left not in df.columns or right not in df.columns:
        df[target_difference] = pd.NA
        df[target_flag] = pd.NA
        return

    df[target_difference] = [
        numeric_difference(left_value, right_value)
        for left_value, right_value in zip(df[left], df[right], strict=True)
    ]
    df[target_flag] = pd.Series(
        [
            abs(value) >= flag_threshold if not is_blank(value) else pd.NA
            for value in df[target_difference]
        ],
        index=df.index,
        dtype="object",
    )


def has_sources(value: Any, required_sources: set[str]) -> bool:
    if is_blank(value):
        return False

    sources = {part.strip().casefold() for part in str(value).split(";")}
    return required_sources.issubset(sources)


def blank_differences_without_sources(
    df: pd.DataFrame,
    *,
    difference_column: str,
    flag_column: str,
    required_sources: set[str],
) -> None:
    if "source_dataset" not in df.columns:
        return

    mask = ~df["source_dataset"].map(lambda value: has_sources(value, required_sources))
    if not mask.any():
        return

    df[flag_column] = df[flag_column].astype("object")
    df.loc[mask, [difference_column, flag_column]] = pd.NA


def add_count_comparison_columns(df: pd.DataFrame) -> None:
    coalesce_numeric_columns(df, "citation_count", ["cited_by_count"])
    for column in ["is_referenced_by_count", "reference_count", "referenced_works_count"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")

    add_difference_columns(
        df,
        target_difference="citation_count_difference_oa_minus_crossref",
        target_flag="citation_count_divergence_flag",
        left="citation_count",
        right="is_referenced_by_count",
        flag_threshold=10,
    )
    blank_differences_without_sources(
        df,
        difference_column="citation_count_difference_oa_minus_crossref",
        flag_column="citation_count_divergence_flag",
        required_sources={"openalex", "crossref"},
    )
    add_difference_columns(
        df,
        target_difference="reference_count_difference_oa_minus_crossref",
        target_flag="reference_count_divergence_flag",
        left="referenced_works_count",
        right="reference_count",
    )
    blank_differences_without_sources(
        df,
        difference_column="reference_count_difference_oa_minus_crossref",
        flag_column="reference_count_divergence_flag",
        required_sources={"openalex", "crossref"},
    )


def split_reference_payload(value: Any) -> list[str]:
    text = clean_text(value)
    if text is None:
        return []

    chunks: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "[{":
            depth += 1
            continue
        if char in "]}":
            depth = max(0, depth - 1)
            continue
        if char == ";" and depth == 0:
            chunk = text[start:index].strip()
            if chunk:
                chunks.append(chunk)
            start = index + 1

    final_chunk = text[start:].strip()
    if final_chunk:
        chunks.append(final_chunk)

    return chunks


def reference_field(reference: Any, *names: str) -> Any:
    if not isinstance(reference, dict):
        return pd.NA

    for name in names:
        value = reference.get(name)
        if not is_blank(value):
            return value
    return pd.NA


def build_publication_key(row: pd.Series, row_number: int) -> str:
    doi = normalize_doi(row.get("doi"))
    if not is_blank(doi):
        return f"doi:{doi}"

    source_dataset = clean_text(row.get("source_dataset"))
    source_record_id = clean_text(row.get("source_record_id"))
    if source_dataset and source_record_id:
        return f"source:{source_dataset}:{source_record_id}"

    return f"row:{row_number}"


def build_reference_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    if "references_json" not in df.columns:
        return []

    rows: list[dict[str, Any]] = []
    needed_columns = ["source_dataset", "source_record_id", "doi", "title", "references_json"]

    for row_number, row in enumerate(
        df.loc[:, needed_columns].to_dict("records"),
        start=1,
    ):
        publication_key = build_publication_key(row, row_number)
        references = split_reference_payload(row["references_json"])

        for reference_index, raw_reference in enumerate(references, start=1):
            parsed = parse_structured_value(raw_reference)
            rows.append(
                {
                    "publication_key": publication_key,
                    "publication_row_number": row_number,
                    "source_dataset": row["source_dataset"],
                    "source_record_id": row["source_record_id"],
                    "doi": row["doi"],
                    "reference_index": reference_index,
                    "reference_doi": normalize_doi(reference_field(parsed, "DOI", "doi")),
                    "reference_title": reference_field(
                        parsed,
                        "article-title",
                        "volume-title",
                        "title",
                        "unstructured",
                    ),
                    "reference_author": reference_field(parsed, "author"),
                    "reference_year": reference_field(parsed, "year"),
                    "raw_reference_json": raw_reference,
                }
            )

    return rows


def write_reference_sidecar(df: pd.DataFrame, output_path: Path) -> int:
    rows = build_reference_rows(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "publication_key",
        "publication_row_number",
        "source_dataset",
        "source_record_id",
        "doi",
        "reference_index",
        "reference_doi",
        "reference_title",
        "reference_author",
        "reference_year",
        "raw_reference_json",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def build_count_audit_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    audit = df.copy()
    add_count_comparison_columns(audit)

    count_columns = [
        "citation_count",
        "is_referenced_by_count",
        "reference_count",
        "referenced_works_count",
        "citation_count_difference_oa_minus_crossref",
        "citation_count_divergence_flag",
        "reference_count_difference_oa_minus_crossref",
        "reference_count_divergence_flag",
    ]

    rows: list[dict[str, Any]] = []
    needed_columns = ["source_dataset", "source_record_id", "doi", "title"]

    for row_number, row in enumerate(audit.to_dict("records"), start=1):
        if all(is_blank(row.get(column)) for column in count_columns):
            continue

        publication_key = build_publication_key(row, row_number)
        audit_row = {
            "publication_key": publication_key,
            "publication_row_number": row_number,
        }
        for column in needed_columns + count_columns:
            audit_row[column] = row.get(column, pd.NA)
        rows.append(audit_row)

    return rows


def write_count_audit_sidecar(df: pd.DataFrame, output_path: Path) -> int:
    rows = build_count_audit_rows(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "publication_key",
        "publication_row_number",
        "source_dataset",
        "source_record_id",
        "doi",
        "title",
        "citation_count",
        "is_referenced_by_count",
        "reference_count",
        "referenced_works_count",
        "citation_count_difference_oa_minus_crossref",
        "citation_count_divergence_flag",
        "reference_count_difference_oa_minus_crossref",
        "reference_count_divergence_flag",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def clean_final_dataset(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()

    add_count_comparison_columns(cleaned)

    if "funder_id" in cleaned.columns:
        cleaned["funder_identifier"] = cleaned["funder_id"].map(normalize_funder_identifier)
    else:
        cleaned["funder_identifier"] = pd.NA

    if "funder_doi" in cleaned.columns:
        cleaned["funder_doi"] = cleaned["funder_doi"].map(
            lambda value: normalize_multi_value_cell(value, doi_only=True)
        )

    for column in MULTI_VALUE_COLUMNS:
        if column in cleaned.columns and column != "funder_doi":
            cleaned[column] = cleaned[column].map(normalize_multi_value_cell)

    columns_to_drop = [column for column in DROP_FROM_MAIN if column in cleaned.columns]
    cleaned = cleaned.drop(columns=columns_to_drop)

    for column in ["cited_by_count", "citation_count"]:
        if column in cleaned.columns:
            cleaned = cleaned.drop(columns=[column])
    if "funder_id" in cleaned.columns:
        cleaned = cleaned.drop(columns=["funder_id"])

    if "funder_identifier" in cleaned.columns and "funder_award" in cleaned.columns:
        columns = list(cleaned.columns)
        columns.remove("funder_identifier")
        award_index = columns.index("funder_award")
        columns.insert(award_index, "funder_identifier")
        cleaned = cleaned.loc[:, columns]

    return cleaned


def bool_is_true(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


def contains_lk_country(value: Any) -> bool:
    if is_blank(value):
        return False
    countries = {
        part.strip().upper()
        for part in re.split(r"[;,|]", str(value))
        if part.strip()
    }
    return "LK" in countries


def valid_policy_version(value: Any) -> bool:
    return clean_text(value) == OWNERSHIP_POLICY_VERSION


def verified_ownership_mask(df: pd.DataFrame) -> pd.Series:
    required = {
        "ownership_decision",
        "ownership_confidence",
        "needs_manual_review",
        "lead_country",
        "ownership_reason",
        "ownership_evidence",
        "ownership_policy_version",
    }
    missing = required - set(df.columns)
    if missing:
        return pd.Series(False, index=df.index)
    return (
        df["ownership_decision"].map(lambda value: str(value).strip().upper() == "INCLUDE")
        & df["ownership_confidence"].map(lambda value: str(value).strip().upper() in {"HIGH", "MEDIUM"})
        & ~df["needs_manual_review"].map(bool_is_true)
        & df["lead_country"].map(contains_lk_country)
        & ~df["ownership_reason"].map(is_blank)
        & ~df["ownership_evidence"].map(is_blank)
        & df["ownership_policy_version"].map(valid_policy_version)
    )


def repository_review_mask(df: pd.DataFrame) -> pd.Series:
    """Return repository-provenance rows that are reviewable but not verified owned."""
    if "source_dataset" not in df.columns:
        return pd.Series(False, index=df.index)

    source_has_repository = df["source_dataset"].map(
        lambda value: "repositories_combined" in {part.strip() for part in str(value).split(";")}
    )
    decision = df.get("ownership_decision", pd.Series(pd.NA, index=df.index)).map(
        lambda value: str(value).strip().upper()
    )
    ownership_class = df.get("ownership_class", pd.Series(pd.NA, index=df.index)).map(
        lambda value: str(value).strip().upper()
    )
    return source_has_repository & (decision == "REVIEW") & (
        ownership_class == "REPOSITORY_ONLY_EVIDENCE"
    )


def final_inclusion_mask(
    df: pd.DataFrame,
    *,
    include_repository_review_records: bool = False,
) -> pd.Series:
    """Return rows to write to the main final dataset."""
    mask = verified_ownership_mask(df)
    if include_repository_review_records:
        mask = mask | repository_review_mask(df)
    return mask


def ownership_review_mask(cleaned: pd.DataFrame, verified_mask: pd.Series) -> pd.Series:
    decision = cleaned.get("ownership_decision", pd.Series(pd.NA, index=cleaned.index)).map(
        lambda value: str(value).strip().upper()
    )
    excluded_mask = decision == "EXCLUDE"
    explicit_review_mask = decision == "REVIEW"
    invalid_metadata_mask = ~verified_mask & ~excluded_mask
    return explicit_review_mask | invalid_metadata_mask


def write_ownership_sidecars(
    cleaned: pd.DataFrame,
    *,
    review_csv: Path,
    excluded_csv: Path,
    verified_csv: Path,
) -> tuple[int, int, int]:
    review_csv.parent.mkdir(parents=True, exist_ok=True)
    excluded_mask = cleaned.get("ownership_decision", pd.Series(pd.NA, index=cleaned.index)).map(
        lambda value: str(value).strip().upper() == "EXCLUDE"
    )
    verified_mask = verified_ownership_mask(cleaned)
    review_mask = ownership_review_mask(cleaned, verified_mask)

    cleaned.loc[review_mask].to_csv(review_csv, index=False)
    cleaned.loc[excluded_mask].to_csv(excluded_csv, index=False)
    cleaned.loc[verified_mask].to_csv(verified_csv, index=False)
    return int(review_mask.sum()), int(excluded_mask.sum()), int(verified_mask.sum())


def write_summary(
    output_path: Path,
    *,
    input_csv: Path,
    output_csv: Path,
    references_csv: Path,
    count_audit_csv: Path,
    input_rows: int,
    input_columns: int,
    output_rows: int,
    output_columns: int,
    reference_rows: int,
    count_audit_rows: int,
    review_rows: int,
    excluded_rows: int,
    verified_rows: int,
    repository_review_rows_in_final: int = 0,
) -> None:
    rows = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "references_csv", "value": str(references_csv)},
        {"metric": "count_audit_csv", "value": str(count_audit_csv)},
        {"metric": "input_rows", "value": input_rows},
        {"metric": "input_columns", "value": input_columns},
        {"metric": "output_rows", "value": output_rows},
        {"metric": "output_columns", "value": output_columns},
        {"metric": "reference_sidecar_rows", "value": reference_rows},
        {"metric": "count_audit_sidecar_rows", "value": count_audit_rows},
        {"metric": "ownership_review_rows", "value": review_rows},
        {"metric": "ownership_excluded_rows", "value": excluded_rows},
        {"metric": "verified_sri_lanka_owned_rows", "value": verified_rows},
        {"metric": "repository_review_rows_in_final", "value": repository_review_rows_in_final},
        {"metric": "dropped_main_columns", "value": "; ".join(DROP_FROM_MAIN)},
        {"metric": "renamed_columns", "value": "cited_by_count -> citation_count; funder_id -> funder_identifier"},
    ]
    pd.DataFrame(rows).to_csv(output_path, index=False)


def build_final_common_dataset(
    input_csv: Path,
    output_csv: Path,
    references_csv: Path,
    count_audit_csv: Path,
    summary_csv: Path,
    review_csv: Path = DEFAULT_REVIEW_CSV,
    excluded_csv: Path = DEFAULT_EXCLUDED_CSV,
    verified_csv: Path = DEFAULT_VERIFIED_CSV,
    include_repository_review_records: bool = False,
) -> tuple[pd.DataFrame, int, int]:
    df = pd.read_csv(input_csv, dtype="object", low_memory=False)
    reference_rows = write_reference_sidecar(df, references_csv)
    count_audit_rows = write_count_audit_sidecar(df, count_audit_csv)
    cleaned = clean_final_dataset(df)
    review_rows, excluded_rows, verified_rows = write_ownership_sidecars(
        cleaned,
        review_csv=review_csv,
        excluded_csv=excluded_csv,
        verified_csv=verified_csv,
    )
    repository_rows_in_final = 0
    if include_repository_review_records:
        repository_rows_in_final = int(
            (repository_review_mask(cleaned) & ~verified_ownership_mask(cleaned)).sum()
        )
    final = cleaned.loc[
        final_inclusion_mask(
            cleaned,
            include_repository_review_records=include_repository_review_records,
        )
    ].copy()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(output_csv, index=False)
    write_summary(
        summary_csv,
        input_csv=input_csv,
        output_csv=output_csv,
        references_csv=references_csv,
        count_audit_csv=count_audit_csv,
        input_rows=len(df),
        input_columns=len(df.columns),
        output_rows=len(final),
        output_columns=len(final.columns),
        reference_rows=reference_rows,
        count_audit_rows=count_audit_rows,
        review_rows=review_rows,
        excluded_rows=excluded_rows,
        verified_rows=verified_rows,
        repository_review_rows_in_final=repository_rows_in_final,
    )

    return final, reference_rows, count_audit_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a clean final common publications dataset and reference sidecar."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--references-csv", type=Path, default=DEFAULT_REFERENCES_CSV)
    parser.add_argument("--count-audit-csv", type=Path, default=DEFAULT_COUNT_AUDIT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--excluded-csv", type=Path, default=DEFAULT_EXCLUDED_CSV)
    parser.add_argument("--verified-csv", type=Path, default=DEFAULT_VERIFIED_CSV)
    parser.add_argument(
        "--include-repository-review-records",
        action="store_true",
        help=(
            "Include repository-provenance REVIEW rows in the main final CSV. "
            "The verified owned sidecar remains strict INCLUDE-only."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cleaned, reference_rows, count_audit_rows = build_final_common_dataset(
        args.input_csv,
        args.output_csv,
        args.references_csv,
        args.count_audit_csv,
        args.summary_csv,
        args.review_csv,
        args.excluded_csv,
        args.verified_csv,
        include_repository_review_records=args.include_repository_review_records,
    )

    print("Done.")
    print(f"  Final rows: {len(cleaned):,}")
    print(f"  Final columns: {len(cleaned.columns):,}")
    print(f"  Final dataset: {args.output_csv}")
    print(f"  Reference sidecar rows: {reference_rows:,} -> {args.references_csv}")
    print(f"  Count audit sidecar rows: {count_audit_rows:,} -> {args.count_audit_csv}")
    print(f"  Summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
