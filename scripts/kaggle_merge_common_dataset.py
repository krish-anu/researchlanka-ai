"""Merge Sri Lanka publication CSVs into one Kaggle-ready common dataset.

Expected input files:
    crossref_clean_2016_2026_enriched.csv
    openalex_sri_lanka_works.csv
    repositories_combined.csv
    sljol.csv

Kaggle usage:
    1. Upload the four CSV files as one Kaggle dataset.
    2. Add this script to the notebook or upload it with the dataset.
    3. Run:
       !python kaggle_merge_common_dataset.py

Local usage from the project root:
    python scripts/kaggle_merge_common_dataset.py

Outputs are written to /kaggle/working by default:
    common_publications_all_records.csv
    common_publications_deduplicated.csv
    common_publications_merge_log.csv
    common_publications_run_log.txt
    common_publications_schema.csv
    common_publications_summary.csv

For local runs, the default input directory is data/raw/Datasets and the
default output directory is data/processed/common.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[1] if SCRIPT_PATH.parent.name == "scripts" else Path.cwd()
LOCAL_INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "Datasets"
LOCAL_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "common"

EXPECTED_FILES = {
    "crossref": "crossref_clean_2016_2026_enriched.csv",
    "openalex": "openalex_sri_lanka_works.csv",
    "repositories_combined": "repositories_combined.csv",
    "sljol": "sljol.csv",
}

COMMON_COLUMNS = [
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "openalex_id",
    "doi",
    "url",
    "landing_page_url",
    "pdf_url",
    "title",
    "subtitle",
    "original_title",
    "abstract",
    "keywords",
    "publication_year",
    "publication_date",
    "created_date",
    "published_date",
    "type",
    "subtype",
    "publication_type",
    "authors",
    "author_count",
    "author_names",
    "author_affiliations",
    "author_orcids",
    "sri_lankan_authors",
    "contributors",
    "editors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "publisher",
    "publisher_location",
    "journal",
    "container_title",
    "source_name",
    "source_type",
    "issn",
    "issn_l",
    "volume",
    "issue",
    "page",
    "first_page",
    "last_page",
    "article_number",
    "language",
    "rights",
    "license",
    "license_url",
    "oa_status",
    "is_oa",
    "cited_by_count",
    "is_referenced_by_count",
    "reference_count",
    "referenced_works_count",
    "references_json",
    "concepts",
    "topics",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "funder_name",
    "funder_doi",
    "funder_id",
    "funder_award",
    "event_name",
    "event_acronym",
    "event_location",
    "event_start_date",
    "event_end_date",
    "event_sponsor",
    "source_set_specs",
    "raw_identifiers",
    "raw_source_json",
]

COLUMN_DESCRIPTIONS = {
    "source_dataset": "Input source: crossref, openalex, repositories_combined, or sljol.",
    "source_institution_id": "Repository or source institution identifier when available.",
    "source_record_id": "Original source record identifier.",
    "source_datestamp": "Original source harvest/datestamp value.",
    "openalex_id": "OpenAlex work ID.",
    "doi": "Normalized DOI without https://doi.org/ prefix.",
    "url": "Best available publication URL.",
    "landing_page_url": "Landing page URL from OpenAlex or the source.",
    "pdf_url": "PDF URL when available.",
    "title": "Publication title.",
    "subtitle": "Publication subtitle.",
    "original_title": "Original title when supplied by the source.",
    "abstract": "Publication abstract or summary.",
    "keywords": "Subjects or keywords.",
    "publication_year": "Publication year.",
    "publication_date": "Best available publication date.",
    "created_date": "Record creation date, mainly from Crossref.",
    "published_date": "Published date, mainly from Crossref.",
    "type": "Source publication type.",
    "subtype": "More specific source subtype.",
    "publication_type": "Publication type/category from repositories or source.",
    "authors": "Author list as supplied or normalized by the source.",
    "author_count": "Number of authors when available.",
    "author_names": "Author names normalized into a shared text field.",
    "author_affiliations": "Author affiliation text when available.",
    "author_orcids": "Author ORCID identifiers.",
    "sri_lankan_authors": "Sri Lankan authors detected by OpenAlex.",
    "contributors": "Contributor names from repositories.",
    "editors": "Editor names from Crossref.",
    "institutions": "Institution names, mainly from OpenAlex.",
    "sri_lankan_institutions": "Sri Lankan institution names detected by OpenAlex.",
    "countries": "Country codes detected by OpenAlex.",
    "publisher": "Publishing organization.",
    "publisher_location": "Publisher location.",
    "journal": "Journal name.",
    "container_title": "Journal, conference, book, or container title.",
    "source_name": "OpenAlex source name or journal/source title.",
    "source_type": "Source/venue type.",
    "issn": "ISSN values.",
    "issn_l": "Linking ISSN.",
    "volume": "Journal volume.",
    "issue": "Journal issue.",
    "page": "Page range or page number.",
    "first_page": "First page.",
    "last_page": "Last page.",
    "article_number": "Article number.",
    "language": "Publication language.",
    "rights": "Rights statement.",
    "license": "License label.",
    "license_url": "License URL.",
    "oa_status": "Open access status.",
    "is_oa": "Whether the work is open access.",
    "cited_by_count": "Citation count, preferring source-specific citation fields.",
    "is_referenced_by_count": "Crossref citation count.",
    "reference_count": "Number of references cited by the publication.",
    "referenced_works_count": "OpenAlex referenced works count.",
    "references_json": "Structured reference list from Crossref.",
    "concepts": "OpenAlex concepts.",
    "topics": "OpenAlex topics.",
    "primary_topic": "OpenAlex primary topic.",
    "primary_field": "OpenAlex primary field.",
    "primary_subfield": "OpenAlex primary subfield.",
    "primary_domain": "OpenAlex primary domain.",
    "funder_name": "Funding organization.",
    "funder_doi": "Funder DOI.",
    "funder_id": "Funder identifier.",
    "funder_award": "Grant or award number.",
    "event_name": "Conference/event name.",
    "event_acronym": "Conference/event acronym.",
    "event_location": "Conference/event location.",
    "event_start_date": "Conference/event start date.",
    "event_end_date": "Conference/event end date.",
    "event_sponsor": "Conference/event sponsor.",
    "source_set_specs": "Repository OAI set specs.",
    "raw_identifiers": "Original identifier values.",
    "raw_source_json": "Optional JSON copy of the original source row.",
}

MULTI_VALUE_COLUMNS = {
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "authors",
    "author_names",
    "author_affiliations",
    "author_orcids",
    "sri_lankan_authors",
    "contributors",
    "editors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "issn",
    "keywords",
    "concepts",
    "topics",
    "funder_name",
    "funder_doi",
    "funder_id",
    "funder_award",
    "event_sponsor",
    "source_set_specs",
    "raw_identifiers",
}

SOURCE_PRIORITY = {
    "openalex": 0,
    "crossref": 1,
    "sljol": 2,
    "repositories_combined": 3,
}

BLANK_STRINGS = {"", "nan", "none", "null", "na", "n/a", "[]", "{}"}
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>;]+", re.IGNORECASE)
YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")
JATS_TAG_RE = re.compile(r"</?jats:[^>]+>|</?[a-z]+:?[^>]*>")


def is_blank(value: Any) -> bool:
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):
        return value.strip().casefold() in BLANK_STRINGS

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0

    return False


def clean_text(value: Any) -> Any:
    if is_blank(value):
        return pd.NA

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else pd.NA


def parse_literal(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text or text[0] not in "[{":
        return value

    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except (json.JSONDecodeError, ValueError, SyntaxError):
            continue

    return value


def flatten_values(value: Any) -> list[Any]:
    parsed = parse_literal(value)

    if is_blank(parsed):
        return []

    if isinstance(parsed, dict):
        return [json.dumps(parsed, ensure_ascii=False, sort_keys=True)]

    if isinstance(parsed, (list, tuple, set)):
        values: list[Any] = []
        for item in parsed:
            values.extend(flatten_values(item))
        return values

    return [parsed]


def first_text(value: Any) -> Any:
    values = flatten_values(value)
    if not values:
        return pd.NA
    return clean_text(values[0])


def unique_text(value: Any, separator: str = "; ") -> Any:
    seen: set[str] = set()
    output: list[str] = []

    for item in flatten_values(value):
        text = clean_text(item)
        if is_blank(text):
            continue
        text = str(text)
        if text not in seen:
            seen.add(text)
            output.append(text)

    return separator.join(output) if output else pd.NA


def split_multi_value(value: Any) -> list[str]:
    text = unique_text(value)
    if is_blank(text):
        return []

    values: list[str] = []
    for chunk in str(text).split(";"):
        cleaned = clean_text(chunk)
        if not is_blank(cleaned):
            values.append(str(cleaned))
    return values


def normalize_doi(value: Any) -> Any:
    if is_blank(value):
        return pd.NA

    text = str(value).strip().casefold()
    match = DOI_RE.search(text)
    if match:
        text = match.group(0)

    text = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(" ", "")
    text = text.rstrip(".,;:)]}")

    if not re.match(r"^10\.\d{4,9}/", text, flags=re.IGNORECASE):
        return pd.NA

    return text or pd.NA


def normalize_bool(value: Any) -> Any:
    if is_blank(value):
        return pd.NA

    if isinstance(value, bool):
        return value

    text = str(value).strip().casefold()
    if text in {"true", "t", "1", "yes", "y"}:
        return True
    if text in {"false", "f", "0", "no", "n"}:
        return False

    return pd.NA


def normalize_int(value: Any) -> Any:
    if is_blank(value):
        return pd.NA

    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        return pd.NA

    if math.isnan(number):
        return pd.NA

    return int(number)


def format_date_parts(parts: list[int]) -> Any:
    if not parts:
        return pd.NA

    year = parts[0]
    if len(parts) == 1:
        return f"{year:04d}"

    month = parts[1]
    if not 1 <= month <= 12:
        return f"{year:04d}"

    if len(parts) == 2:
        return f"{year:04d}-{month:02d}"

    day = parts[2]
    if not 1 <= day <= 31:
        return f"{year:04d}-{month:02d}"

    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_date_parts(value: Any) -> Any:
    parsed = parse_literal(value)

    if isinstance(parsed, dict) and "date-parts" in parsed:
        parsed = parsed["date-parts"]

    if not isinstance(parsed, list):
        return normalize_date(value)

    parts = parsed[0] if parsed and isinstance(parsed[0], list) else parsed
    normalized_parts: list[int] = []

    for part in parts[:3]:
        if is_blank(part):
            break
        try:
            normalized_parts.append(int(float(str(part).strip())))
        except ValueError:
            break

    return format_date_parts(normalized_parts)


def normalize_date(value: Any) -> Any:
    text = clean_text(value)
    if is_blank(text):
        return pd.NA

    text = str(text)
    if text[0] in "[{":
        return normalize_date_parts(text)

    if re.fullmatch(r"\d{4}", text):
        return text

    year_month = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if year_month:
        return f"{int(year_month.group(1)):04d}-{int(year_month.group(2)):02d}"

    year_month_day = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if year_month_day:
        return (
            f"{int(year_month_day.group(1)):04d}-"
            f"{int(year_month_day.group(2)):02d}-"
            f"{int(year_month_day.group(3)):02d}"
        )

    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return pd.NA

    return parsed.date().isoformat()


def normalize_year(value: Any) -> Any:
    if is_blank(value):
        return pd.NA

    if isinstance(value, int):
        return value

    if isinstance(value, float) and not math.isnan(value):
        return int(value)

    text = str(value).strip()
    if text and text[0] in "[{":
        date_value = normalize_date_parts(text)
        if is_blank(date_value):
            return pd.NA
        text = str(date_value)

    match = YEAR_RE.search(text)
    return int(match.group(1)) if match else pd.NA


def strip_jats(value: Any) -> Any:
    text = first_text(value)
    if is_blank(text):
        return pd.NA

    stripped = JATS_TAG_RE.sub(" ", str(text))
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped or pd.NA


def normalize_title_key(value: Any) -> Any:
    text = first_text(value)
    if is_blank(text):
        return pd.NA

    return NON_WORD_RE.sub(" ", str(text).casefold()).strip()


def normalize_author_key(value: Any) -> str:
    names = split_multi_value(value)
    if not names:
        return ""

    first_author = names[0].casefold()
    return NON_WORD_RE.sub(" ", first_author).strip()


def coalesce_columns(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    result = pd.Series(pd.NA, index=df.index, dtype="object")

    for column in candidates:
        if column not in df.columns:
            continue

        values = df.loc[:, column]
        if isinstance(values, pd.DataFrame):
            values = values.iloc[:, 0]

        mask = result.map(is_blank) & values.map(lambda value: not is_blank(value))
        result.loc[mask] = values.loc[mask]

    return result


def assign_column(
    output: pd.DataFrame,
    target: str,
    source: pd.DataFrame,
    candidates: list[str],
    transform: Callable[[Any], Any] = clean_text,
) -> None:
    output[target] = coalesce_columns(source, candidates).map(transform)


def empty_common_frame(index: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(
        {column: pd.Series(pd.NA, index=index, dtype="object") for column in COMMON_COLUMNS}
    )


def crossref_person_name(row: pd.Series, prefix: str) -> Any:
    full_name = first_text(row.get(f"{prefix}_name"))
    if not is_blank(full_name):
        return full_name

    given = first_text(row.get(f"{prefix}_given"))
    family = first_text(row.get(f"{prefix}_family"))
    parts = [str(part) for part in (given, family) if not is_blank(part)]
    return " ".join(parts) if parts else pd.NA


def raw_row_json(row: pd.Series) -> str:
    values = {
        column: (None if is_blank(value) else value)
        for column, value in row.to_dict().items()
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def add_raw_json(output: pd.DataFrame, source: pd.DataFrame, include_raw_json: bool) -> None:
    if include_raw_json:
        output["raw_source_json"] = source.apply(raw_row_json, axis=1)


def normalize_openalex(
    df: pd.DataFrame,
    *,
    include_raw_json: bool,
) -> pd.DataFrame:
    output = empty_common_frame(df.index)
    output["source_dataset"] = "openalex"

    assign_column(output, "openalex_id", df, ["openalex_id"])
    assign_column(output, "source_record_id", df, ["openalex_id"])
    assign_column(output, "doi", df, ["doi"], normalize_doi)
    assign_column(output, "url", df, ["landing_page_url"])
    assign_column(output, "landing_page_url", df, ["landing_page_url"])
    assign_column(output, "pdf_url", df, ["pdf_url"])
    assign_column(output, "title", df, ["title"], first_text)
    assign_column(output, "publication_year", df, ["publication_year"], normalize_year)
    assign_column(output, "publication_date", df, ["publication_date"], normalize_date)
    assign_column(output, "type", df, ["type"])
    assign_column(output, "publication_type", df, ["type"])
    assign_column(output, "cited_by_count", df, ["cited_by_count"], normalize_int)
    assign_column(output, "is_referenced_by_count", df, ["cited_by_count"], normalize_int)
    assign_column(output, "author_count", df, ["author_count"], normalize_int)
    assign_column(output, "authors", df, ["authors"], unique_text)
    assign_column(output, "author_names", df, ["authors"], unique_text)
    assign_column(output, "author_affiliations", df, ["institutions"], unique_text)
    assign_column(output, "sri_lankan_authors", df, ["sri_lankan_authors"], unique_text)
    assign_column(output, "institutions", df, ["institutions"], unique_text)
    assign_column(output, "sri_lankan_institutions", df, ["sri_lankan_institutions"], unique_text)
    assign_column(output, "countries", df, ["countries"], unique_text)
    assign_column(output, "source_name", df, ["source_name"])
    assign_column(output, "publisher", df, ["publisher"])
    assign_column(output, "is_oa", df, ["is_oa"], normalize_bool)
    assign_column(output, "referenced_works_count", df, ["referenced_works_count"], normalize_int)
    assign_column(output, "reference_count", df, ["referenced_works_count"], normalize_int)
    assign_column(output, "concepts", df, ["concepts"], unique_text)
    assign_column(output, "topics", df, ["topics"], unique_text)
    assign_column(output, "primary_topic", df, ["primary_topic"])
    assign_column(output, "primary_field", df, ["primary_field"])
    assign_column(output, "primary_subfield", df, ["primary_subfield"])
    assign_column(output, "primary_domain", df, ["primary_domain"])
    assign_column(output, "language", df, ["language"])
    assign_column(output, "oa_status", df, ["oa_status"])
    assign_column(output, "license", df, ["license"])
    assign_column(output, "source_type", df, ["source_type"])
    assign_column(output, "issn", df, ["issn", "issn_l"], unique_text)
    assign_column(output, "issn_l", df, ["issn_l"])
    assign_column(output, "volume", df, ["volume"])
    assign_column(output, "issue", df, ["issue"])
    assign_column(output, "first_page", df, ["first_page"])
    assign_column(output, "last_page", df, ["last_page"])
    add_raw_json(output, df, include_raw_json)

    return finalize_common_frame(output)


def normalize_crossref(
    df: pd.DataFrame,
    *,
    include_raw_json: bool,
) -> pd.DataFrame:
    output = empty_common_frame(df.index)
    output["source_dataset"] = "crossref"

    assign_column(output, "source_record_id", df, ["DOI", "doi"], normalize_doi)
    assign_column(output, "doi", df, ["DOI", "doi"], normalize_doi)
    assign_column(output, "url", df, ["URL", "url"])
    assign_column(output, "landing_page_url", df, ["URL", "url"])
    assign_column(output, "title", df, ["title"], first_text)
    assign_column(output, "subtitle", df, ["subtitle"], first_text)
    assign_column(output, "original_title", df, ["original-title", "original_title"], first_text)
    assign_column(output, "abstract", df, ["abstract"], strip_jats)
    assign_column(output, "publication_year", df, ["publication_year"], normalize_year)
    assign_column(output, "publication_date", df, ["issued.date-parts", "issued_date"], normalize_date_parts)
    assign_column(output, "created_date", df, ["created.date-parts", "created_date"], normalize_date_parts)
    assign_column(output, "published_date", df, ["published.date-parts", "published_date"], normalize_date_parts)
    assign_column(output, "type", df, ["type"])
    assign_column(output, "subtype", df, ["subtype"])
    assign_column(output, "publication_type", df, ["type"])
    assign_column(output, "authors", df, ["author_name"], unique_text)
    assign_column(output, "author_names", df, ["author_name"], unique_text)
    output["author_names"] = output["author_names"].where(
        output["author_names"].map(lambda value: not is_blank(value)),
        df.apply(lambda row: crossref_person_name(row, "author"), axis=1),
    )
    output["authors"] = output["authors"].where(
        output["authors"].map(lambda value: not is_blank(value)),
        output["author_names"],
    )
    assign_column(output, "author_affiliations", df, ["author_affiliation"], unique_text)
    assign_column(output, "author_orcids", df, ["author_ORCID", "author_orcid"], unique_text)
    output["editors"] = df.apply(lambda row: crossref_person_name(row, "editor"), axis=1)
    assign_column(output, "publisher", df, ["publisher"])
    assign_column(output, "publisher_location", df, ["publisher-location", "publisher_location"])
    assign_column(output, "journal", df, ["container-title", "container_title"], first_text)
    assign_column(output, "container_title", df, ["container-title", "container_title"], first_text)
    assign_column(output, "source_name", df, ["container-title", "container_title"], first_text)
    assign_column(output, "issn", df, ["ISSN", "issn"], unique_text)
    assign_column(output, "issn_l", df, ["ISSN", "issn"], first_text)
    assign_column(output, "volume", df, ["volume"])
    assign_column(output, "issue", df, ["issue"])
    assign_column(output, "page", df, ["page"])
    assign_column(output, "article_number", df, ["article-number", "article_number"])
    assign_column(output, "language", df, ["language"])
    assign_column(output, "license_url", df, ["license_URL", "license_url"])
    assign_column(output, "cited_by_count", df, ["is-referenced-by-count"], normalize_int)
    assign_column(output, "is_referenced_by_count", df, ["is-referenced-by-count"], normalize_int)
    assign_column(output, "reference_count", df, ["reference-count"], normalize_int)
    assign_column(output, "references_json", df, ["references_json"], unique_text)
    assign_column(output, "funder_name", df, ["funder_name"], unique_text)
    assign_column(output, "funder_doi", df, ["funder_DOI", "funder_doi"], unique_text)
    assign_column(output, "funder_id", df, ["funder_id"], unique_text)
    assign_column(output, "funder_award", df, ["funder_award"], unique_text)
    assign_column(output, "event_name", df, ["event.name", "event_name"])
    assign_column(output, "event_acronym", df, ["event.acronym", "event_acronym"])
    assign_column(output, "event_location", df, ["event.location", "event_location"])
    assign_column(
        output,
        "event_start_date",
        df,
        ["event.start.date-parts", "event_start_date"],
        normalize_date_parts,
    )
    assign_column(
        output,
        "event_end_date",
        df,
        ["event.end.date-parts", "event_end_date"],
        normalize_date_parts,
    )
    assign_column(output, "event_sponsor", df, ["event.sponsor", "event_sponsor"], unique_text)
    add_raw_json(output, df, include_raw_json)

    return finalize_common_frame(output)


def normalize_repository_like(
    df: pd.DataFrame,
    *,
    source_dataset: str,
    include_raw_json: bool,
) -> pd.DataFrame:
    output = empty_common_frame(df.index)
    output["source_dataset"] = source_dataset

    assign_column(output, "source_institution_id", df, ["source_institution_id"])
    assign_column(output, "source_record_id", df, ["source_record_id"])
    assign_column(output, "source_datestamp", df, ["source_datestamp"])
    doi_candidates = ["doi", "DOI", "raw_identifiers"]
    if source_dataset == "sljol":
        doi_candidates.append("source_record_id")
    assign_column(output, "doi", df, doi_candidates, normalize_doi)
    assign_column(output, "url", df, ["url", "URL"])
    assign_column(output, "landing_page_url", df, ["url", "URL"])
    assign_column(output, "title", df, ["title"], first_text)
    assign_column(output, "abstract", df, ["abstract"], strip_jats)
    assign_column(output, "keywords", df, ["keywords"], unique_text)
    assign_column(output, "publication_date", df, ["publication_date"], normalize_date)
    assign_column(output, "publication_year", df, ["publication_year", "publication_date"], normalize_year)
    assign_column(output, "type", df, ["publication_type", "type"])
    assign_column(output, "publication_type", df, ["publication_type", "type"])
    assign_column(output, "authors", df, ["authors"], unique_text)
    assign_column(output, "author_names", df, ["authors"], unique_text)
    assign_column(output, "contributors", df, ["contributors"], unique_text)
    assign_column(output, "publisher", df, ["publisher"])
    assign_column(output, "journal", df, ["journal"])
    assign_column(output, "container_title", df, ["journal"])
    assign_column(output, "source_name", df, ["journal"])
    output["source_type"] = "repository" if source_dataset == "repositories_combined" else "journal"
    assign_column(output, "language", df, ["language"])
    assign_column(output, "rights", df, ["rights"])
    assign_column(output, "source_set_specs", df, ["source_set_specs"], unique_text)
    assign_column(output, "raw_identifiers", df, ["raw_identifiers"], unique_text)
    add_raw_json(output, df, include_raw_json)

    return finalize_common_frame(output)


def finalize_common_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["doi"] = df["doi"].map(normalize_doi)

    fill_from(df, "url", ["landing_page_url"])
    fill_from(df, "landing_page_url", ["url"])
    fill_from(df, "journal", ["container_title", "source_name"])
    fill_from(df, "container_title", ["journal", "source_name"])
    fill_from(df, "source_name", ["journal", "container_title"])
    fill_from(df, "cited_by_count", ["is_referenced_by_count"])
    fill_from(df, "reference_count", ["referenced_works_count"])

    missing_year = df["publication_year"].map(is_blank)
    if missing_year.any():
        df.loc[missing_year, "publication_year"] = df.loc[missing_year, "publication_date"].map(
            normalize_year
        )

    return df[COMMON_COLUMNS]


def fill_from(df: pd.DataFrame, target: str, candidates: list[str]) -> None:
    for candidate in candidates:
        mask = df[target].map(is_blank) & df[candidate].map(lambda value: not is_blank(value))
        if mask.any():
            df.loc[mask, target] = df.loc[mask, candidate]


def normalize_source_frame(
    source_dataset: str,
    path: Path,
    *,
    include_raw_json: bool,
    sample_rows: int | None = None,
) -> pd.DataFrame:
    df = pd.read_csv(path, dtype="object", low_memory=False, nrows=sample_rows)
    df.columns = [str(column).strip() for column in df.columns]

    if source_dataset == "openalex":
        return normalize_openalex(df, include_raw_json=include_raw_json)
    if source_dataset == "crossref":
        return normalize_crossref(df, include_raw_json=include_raw_json)
    if source_dataset in {"repositories_combined", "sljol"}:
        return normalize_repository_like(
            df,
            source_dataset=source_dataset,
            include_raw_json=include_raw_json,
        )

    raise ValueError(f"Unsupported source dataset: {source_dataset}")


def record_merge_info(row: pd.Series, row_number: int) -> tuple[str, str, str]:
    doi = normalize_doi(row.get("doi"))
    if not is_blank(doi):
        return (
            f"doi:{doi}",
            "doi",
            "Same normalized DOI. DOI URLs, DOI: prefixes, case, spaces, and trailing punctuation were cleaned.",
        )

    title_key = normalize_title_key(row.get("title"))
    year = normalize_year(row.get("publication_year"))
    author_value = row.get("author_names")
    if is_blank(author_value):
        author_value = row.get("authors")
    author_key = normalize_author_key(author_value)

    if not is_blank(title_key) and not is_blank(year):
        if author_key:
            return (
                f"title_year_author:{title_key}|{year}|{author_key}",
                "title_year_first_author",
                "Missing DOI; matched by normalized title, publication year, and first author.",
            )
        return (
            f"title_year:{title_key}|{year}",
            "title_year",
            "Missing DOI and first author; matched by normalized title and publication year.",
        )

    source = row.get("source_dataset")
    source_record_id = row.get("source_record_id")
    if not is_blank(source) and not is_blank(source_record_id):
        return (
            f"source_record:{source}|{source_record_id}",
            "source_record_id",
            "No DOI/title-year key; kept by source dataset and original source record ID.",
        )

    return (
        f"row:{row_number}",
        "row_number",
        "No DOI, title/year key, or source record ID; kept by input row number.",
    )


def record_merge_key(row: pd.Series, row_number: int) -> str:
    return record_merge_info(row, row_number)[0]


def completeness_score(row: pd.Series) -> int:
    ignored = {"source_dataset", "source_record_id", "source_datestamp", "raw_source_json"}
    return sum(not is_blank(row[column]) for column in COMMON_COLUMNS if column not in ignored)


def merge_group(group: pd.DataFrame) -> dict[str, Any]:
    ordered = group.copy()
    ordered["_source_priority"] = ordered["source_dataset"].map(SOURCE_PRIORITY).fillna(99)
    ordered["_completeness"] = ordered.apply(completeness_score, axis=1)
    ordered = ordered.sort_values(
        ["_completeness", "_source_priority"],
        ascending=[False, True],
        kind="stable",
    )

    merged: dict[str, Any] = {}

    for column in COMMON_COLUMNS:
        if column in MULTI_VALUE_COLUMNS:
            seen: set[str] = set()
            values: list[str] = []
            for value in ordered[column]:
                for item in split_multi_value(value):
                    if item not in seen:
                        seen.add(item)
                        values.append(item)
            merged[column] = "; ".join(values) if values else pd.NA
            continue

        for value in ordered[column]:
            if not is_blank(value):
                merged[column] = value
                break
        else:
            merged[column] = pd.NA

    return merged


def unique_series_text(values: pd.Series) -> Any:
    return unique_text(values.dropna().tolist())


def first_nonblank(*values: Any) -> Any:
    for value in values:
        if not is_blank(value):
            return value
    return pd.NA


def merge_log_row(
    merged_row_number: int,
    merge_key: str,
    group: pd.DataFrame,
    merged: dict[str, Any],
) -> dict[str, Any]:
    group_size = len(group)
    merge_method = first_text(group["_merge_method"].iloc[0])
    merge_reason = first_text(group["_merge_reason"].iloc[0])
    source_datasets = unique_series_text(group["source_dataset"])

    return {
        "merged_row_number": merged_row_number,
        "action": "merged" if group_size > 1 else "kept_single_record",
        "was_merged": group_size > 1,
        "merge_method": merge_method,
        "merge_key": merge_key,
        "merge_reason": merge_reason,
        "input_record_count": group_size,
        "source_datasets": source_datasets,
        "source_record_ids": unique_series_text(group["source_record_id"]),
        "openalex_ids": unique_series_text(group["openalex_id"]),
        "normalized_dois": unique_series_text(group["doi"]),
        "final_doi": merged.get("doi"),
        "final_title": merged.get("title"),
        "final_publication_year": merged.get("publication_year"),
        "final_authors": first_nonblank(merged.get("author_names"), merged.get("authors")),
        "final_journal": first_nonblank(merged.get("journal"), merged.get("container_title")),
        "non_empty_final_fields": completeness_score(pd.Series(merged)),
        "input_row_numbers": "; ".join(str(index + 1) for index in group.index),
    }


def deduplicate_publications(
    all_records: pd.DataFrame,
    *,
    return_log: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    working = all_records.copy()
    merge_infos = [
        record_merge_info(row, row_number)
        for row_number, (_, row) in enumerate(working.iterrows(), start=1)
    ]
    working["_merge_key"] = [merge_info[0] for merge_info in merge_infos]
    working["_merge_method"] = [merge_info[1] for merge_info in merge_infos]
    working["_merge_reason"] = [merge_info[2] for merge_info in merge_infos]

    merged_rows: list[dict[str, Any]] = []
    merge_log_rows: list[dict[str, Any]] = []

    for merged_row_number, (merge_key, group) in enumerate(
        working.groupby("_merge_key", sort=False, dropna=False),
        start=1,
    ):
        merged = merge_group(group)
        merged_rows.append(merged)
        merge_log_rows.append(
            merge_log_row(
                merged_row_number,
                str(merge_key),
                group,
                merged,
            )
        )

    deduplicated = pd.DataFrame(merged_rows, columns=COMMON_COLUMNS)
    merge_log = pd.DataFrame(merge_log_rows)

    if return_log:
        return deduplicated, merge_log

    return deduplicated


def find_input_file(input_root: Path, filename: str) -> Path:
    direct_input = input_root / filename
    if direct_input.exists():
        return direct_input

    if input_root.exists():
        input_candidates = sorted(
            input_root.rglob(filename),
            key=lambda path: (len(path.parts), str(path)),
        )
        if input_candidates:
            return input_candidates[0]

    candidates: list[Path] = []
    if input_root != Path.cwd() and Path.cwd().exists():
        candidates.extend(Path.cwd().rglob(filename))

    if not candidates:
        raise FileNotFoundError(
            f"Could not find {filename}. In Kaggle, check /kaggle/input/*/{filename}."
        )

    return sorted(candidates, key=lambda path: (len(path.parts), str(path)))[0]


def write_schema(output_dir: Path) -> Path:
    schema = pd.DataFrame(
        [
            {
                "column": column,
                "description": COLUMN_DESCRIPTIONS.get(column, ""),
            }
            for column in COMMON_COLUMNS
        ]
    )
    output_path = output_dir / "common_publications_schema.csv"
    schema.to_csv(output_path, index=False)
    return output_path


def write_summary(
    output_dir: Path,
    *,
    input_paths: dict[str, Path],
    source_frames: dict[str, pd.DataFrame],
    all_records: pd.DataFrame,
    deduplicated: pd.DataFrame,
) -> Path:
    rows: list[dict[str, Any]] = []

    for source_dataset, frame in source_frames.items():
        rows.append(
            {
                "metric": f"{source_dataset}_rows",
                "value": len(frame),
                "file": str(input_paths[source_dataset]),
            }
        )
        rows.append(
            {
                "metric": f"{source_dataset}_rows_with_doi",
                "value": int(frame["doi"].map(lambda value: not is_blank(value)).sum()),
                "file": str(input_paths[source_dataset]),
            }
        )

    rows.extend(
        [
            {
                "metric": "all_records_rows",
                "value": len(all_records),
                "file": "common_publications_all_records.csv",
            },
            {
                "metric": "deduplicated_rows",
                "value": len(deduplicated),
                "file": "common_publications_deduplicated.csv",
            },
            {
                "metric": "common_schema_columns",
                "value": len(COMMON_COLUMNS),
                "file": "common_publications_schema.csv",
            },
        ]
    )

    output_path = output_dir / "common_publications_summary.csv"
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def write_run_log(
    output_dir: Path,
    *,
    input_paths: dict[str, Path],
    source_frames: dict[str, pd.DataFrame],
    all_records: pd.DataFrame,
    deduplicated: pd.DataFrame,
    merge_log: pd.DataFrame,
    args: argparse.Namespace,
    output_paths: dict[str, Path],
) -> Path:
    lines = [
        "ResearchLanka common dataset merge log",
        f"Created at: {datetime.now().isoformat(timespec='seconds')}",
        f"Input directory: {args.input_dir}",
        f"Output directory: {args.output_dir}",
        f"Sample rows per source: {args.sample_rows or 'all'}",
        f"Included raw_source_json: {bool(args.include_raw_json)}",
        "",
        "Input files:",
    ]

    for source_dataset, path in input_paths.items():
        frame = source_frames[source_dataset]
        rows_with_doi = int(frame["doi"].map(lambda value: not is_blank(value)).sum())
        lines.append(f"- {source_dataset}: {path}")
        lines.append(f"  rows normalized: {len(frame):,}")
        lines.append(f"  rows with normalized DOI: {rows_with_doi:,}")

    lines.extend(
        [
            "",
            "Merge results:",
            f"- all normalized records: {len(all_records):,}",
            f"- deduplicated publications: {len(deduplicated):,}",
            f"- records removed by deduplication: {len(all_records) - len(deduplicated):,}",
            "",
            "Merge method counts:",
        ]
    )

    method_counts = merge_log["merge_method"].value_counts(dropna=False)
    for method, count in method_counts.items():
        lines.append(f"- {method}: {int(count):,} final rows")

    merged_method_counts = merge_log.loc[merge_log["was_merged"], "merge_method"].value_counts(
        dropna=False
    )
    lines.append("")
    lines.append("Merged-row method counts:")
    if merged_method_counts.empty:
        lines.append("- none: 0")
    else:
        for method, count in merged_method_counts.items():
            lines.append(f"- {method}: {int(count):,} merged rows")

    lines.extend(["", "Outputs:"])
    for name, path in output_paths.items():
        lines.append(f"- {name}: {path}")

    output_path = output_dir / "common_publications_run_log.txt"
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    if Path("/kaggle/input").exists():
        default_input_dir = Path("/kaggle/input")
    elif LOCAL_INPUT_DIR.exists():
        default_input_dir = LOCAL_INPUT_DIR
    else:
        default_input_dir = Path.cwd()

    if Path("/kaggle/working").exists():
        default_output_dir = Path("/kaggle/working")
    elif PROJECT_ROOT.exists():
        default_output_dir = LOCAL_OUTPUT_DIR
    else:
        default_output_dir = Path.cwd()

    parser = argparse.ArgumentParser(
        description="Normalize and merge Crossref, OpenAlex, repository, and SLJOL CSVs."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_input_dir,
        help="Input directory to search recursively for the four CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Output directory for merged CSV files.",
    )
    parser.add_argument(
        "--include-raw-json",
        action="store_true",
        help="Store the original source row JSON in raw_source_json. This increases output size.",
    )
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=None,
        help="Read only the first N rows from each input file for a quick local test.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = {
        source_dataset: find_input_file(args.input_dir, filename)
        for source_dataset, filename in EXPECTED_FILES.items()
    }

    print("Found input files:")
    for source_dataset, path in input_paths.items():
        print(f"  {source_dataset}: {path}")

    if args.sample_rows:
        print(f"\nSample mode: reading first {args.sample_rows:,} rows from each file.")

    source_frames: dict[str, pd.DataFrame] = {}
    print("\nNormalizing input files...", flush=True)
    for source_dataset, path in input_paths.items():
        print(f"  Normalizing {source_dataset}...", flush=True)
        source_frames[source_dataset] = normalize_source_frame(
            source_dataset,
            path,
            include_raw_json=args.include_raw_json,
            sample_rows=args.sample_rows,
        )
        print(f"  {source_dataset}: {len(source_frames[source_dataset]):,} rows", flush=True)

    all_records = pd.concat(source_frames.values(), ignore_index=True)

    all_records_path = args.output_dir / "common_publications_all_records.csv"
    deduplicated_path = args.output_dir / "common_publications_deduplicated.csv"
    merge_log_path = args.output_dir / "common_publications_merge_log.csv"

    print(f"\nWriting normalized records -> {all_records_path}", flush=True)
    all_records.to_csv(all_records_path, index=False)

    print("Deduplicating and building merge log...", flush=True)
    deduplicated, merge_log = deduplicate_publications(all_records, return_log=True)

    print(f"Writing deduplicated records -> {deduplicated_path}", flush=True)
    deduplicated.to_csv(deduplicated_path, index=False)
    print(f"Writing merge log -> {merge_log_path}", flush=True)
    merge_log.to_csv(merge_log_path, index=False)
    schema_path = write_schema(args.output_dir)
    summary_path = write_summary(
        args.output_dir,
        input_paths=input_paths,
        source_frames=source_frames,
        all_records=all_records,
        deduplicated=deduplicated,
    )
    output_paths = {
        "all_records": all_records_path,
        "deduplicated": deduplicated_path,
        "merge_log": merge_log_path,
        "schema": schema_path,
        "summary": summary_path,
    }
    run_log_path = write_run_log(
        args.output_dir,
        input_paths=input_paths,
        source_frames=source_frames,
        all_records=all_records,
        deduplicated=deduplicated,
        merge_log=merge_log,
        args=args,
        output_paths=output_paths,
    )

    print("\nDone.")
    print(f"  All normalized records: {len(all_records):,} -> {all_records_path}")
    print(f"  Deduplicated publications: {len(deduplicated):,} -> {deduplicated_path}")
    print(f"  Merge log: {merge_log_path}")
    print(f"  Run log: {run_log_path}")
    print(f"  Schema columns: {len(COMMON_COLUMNS):,} -> {schema_path}")
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
