"""Merge Sri Lanka publication CSVs into one Kaggle-ready common dataset.

Expected input files:
    crossref_clean_2016_<current_year>_enriched.csv or crossref_sri_lanka_works.csv
    openalex_sri_lanka_works.csv
    repositories_combined.csv
    sljol.csv

Kaggle usage:
    1. Upload the four CSV files as one Kaggle dataset.
    2. Add this script to the notebook or upload it with the dataset.
    3. Run:
       !python kaggle_merge_common_dataset.py

Local usage from the project root:
    python scripts/processing/kaggle_merge_common_dataset.py

Outputs are written to /kaggle/working by default:
    common_publications_all_records.csv
    common_publications_deduplicated.csv
    common_publications_manual_review_candidates.csv
    common_publications_merge_log.csv
    common_publications_run_log.txt
    common_publications_schema.csv
    common_publications_summary.csv

For local runs, the default input directory is data and the default output
directory is data/processed/common.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import math
import re
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
LOCAL_INPUT_DIR = PROJECT_ROOT / "data"
LOCAL_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "common"
DEFAULT_COLLECTION_START_YEAR = 2016
DEFAULT_COLLECTION_END_YEAR = date.today().year
DEFAULT_COLLECTION_YEAR_SUFFIX = f"{DEFAULT_COLLECTION_START_YEAR}_{DEFAULT_COLLECTION_END_YEAR}"

EXPECTED_FILES = {
    "crossref": f"crossref_clean_{DEFAULT_COLLECTION_YEAR_SUFFIX}_enriched.csv",
    "openalex": "openalex_sri_lanka_works.csv",
    "repositories_combined": "repositories_combined.csv",
    "sljol": "sljol.csv",
}

EXPECTED_FILE_CANDIDATES = {
    "crossref": (
        f"crossref_clean_{DEFAULT_COLLECTION_YEAR_SUFFIX}_enriched.csv",
        "crossref_clean_2016_2026_enriched.csv",
        "crossref_sri_lanka_works.csv",
    ),
    "openalex": ("openalex_sri_lanka_works.csv",),
    "repositories_combined": ("repositories_combined.csv",),
    "sljol": ("sljol.csv",),
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
    "cited_by_count": "Best available citation count selected by merge ordering.",
    "is_referenced_by_count": "Crossref citation count; kept separately from OpenAlex cited_by_count.",
    "reference_count": "Best available reference count selected by merge ordering.",
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

PROVENANCE_COLUMNS = {
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "source_set_specs",
    "raw_identifiers",
}

DEFAULT_FIELD_SOURCE_POLICY = {
    "doi": ["crossref", "openalex", "sljol", "repositories_combined"],
    "openalex_id": ["openalex"],
    "title": ["crossref", "openalex", "sljol", "repositories_combined"],
    "publication_year": ["crossref", "openalex", "sljol", "repositories_combined"],
    "publication_date": ["crossref", "openalex", "sljol", "repositories_combined"],
    "published_date": ["crossref", "openalex", "sljol", "repositories_combined"],
    "type": ["crossref", "openalex", "sljol", "repositories_combined"],
    "subtype": ["crossref", "openalex", "sljol", "repositories_combined"],
    "publication_type": ["crossref", "openalex", "sljol", "repositories_combined"],
    "abstract": ["crossref", "repositories_combined", "sljol", "openalex"],
    "publisher": ["crossref", "openalex", "sljol", "repositories_combined"],
    "publisher_location": ["crossref", "openalex", "sljol", "repositories_combined"],
    "journal": ["crossref", "openalex", "sljol", "repositories_combined"],
    "container_title": ["crossref", "openalex", "sljol", "repositories_combined"],
    "source_name": ["crossref", "openalex", "sljol", "repositories_combined"],
    "source_type": ["openalex", "crossref", "sljol", "repositories_combined"],
    "issn_l": ["crossref", "openalex", "sljol", "repositories_combined"],
    "volume": ["crossref", "openalex", "sljol", "repositories_combined"],
    "issue": ["crossref", "openalex", "sljol", "repositories_combined"],
    "page": ["crossref", "openalex", "sljol", "repositories_combined"],
    "first_page": ["crossref", "openalex", "sljol", "repositories_combined"],
    "last_page": ["crossref", "openalex", "sljol", "repositories_combined"],
    "article_number": ["crossref", "openalex", "sljol", "repositories_combined"],
    "language": ["openalex", "crossref", "sljol", "repositories_combined"],
    "rights": ["repositories_combined", "sljol", "crossref", "openalex"],
    "license": ["crossref", "openalex", "repositories_combined", "sljol"],
    "license_url": ["crossref", "openalex", "repositories_combined", "sljol"],
    "oa_status": ["openalex", "crossref", "sljol", "repositories_combined"],
    "is_oa": ["openalex", "crossref", "sljol", "repositories_combined"],
    "cited_by_count": ["openalex", "crossref"],
    "is_referenced_by_count": ["crossref"],
    "reference_count": ["crossref", "openalex"],
    "referenced_works_count": ["openalex"],
    "references_json": ["crossref", "openalex", "sljol", "repositories_combined"],
    "primary_topic": ["openalex"],
    "primary_field": ["openalex"],
    "primary_subfield": ["openalex"],
    "primary_domain": ["openalex"],
    "event_name": ["crossref", "openalex", "sljol", "repositories_combined"],
    "event_acronym": ["crossref", "openalex", "sljol", "repositories_combined"],
    "event_location": ["crossref", "openalex", "sljol", "repositories_combined"],
    "event_start_date": ["crossref", "openalex", "sljol", "repositories_combined"],
    "event_end_date": ["crossref", "openalex", "sljol", "repositories_combined"],
}

BLANK_STRINGS = {"", "nan", "none", "null", "na", "n/a", "[]", "{}"}
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>;]+", re.IGNORECASE)
YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")
ARTIFACT_TITLE_RE = re.compile(
    r"\b(?:additional file|supplementary|supplemental|figure|fig\.?|table|"
    r"dataset|data set|appendix|annex|image|plate)\b",
    re.IGNORECASE,
)
DUPLICATE_REVIEW_TITLE_SIMILARITY_THRESHOLD = 0.80
DUPLICATE_REVIEW_YEAR_SPAN_THRESHOLD = 1
TAG_RE = re.compile(r"<[^>]+>")
INLINE_TEXT_TAG_RE = re.compile(
    r"<(i|em|b|strong|u|span|jats:[^>\s/]+)(?:\s+[^>]*)?>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)
COMPACT_TEXT_TAG_RE = re.compile(
    r"<(scp|sub|sup|inf)(?:\s+[^>]*)?>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)
SOURCE_ENTITY_FIXES = {
    "&apos;": "'",
    "&squo;": "'",
}


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


def decode_html_entities(text: str) -> str:
    previous = text
    for _ in range(3):
        decoded = html.unescape(previous)
        for source, replacement in SOURCE_ENTITY_FIXES.items():
            decoded = decoded.replace(source, replacement)
        if decoded == previous:
            break
        previous = decoded
    return previous


def replace_compact_text_tag(match: re.Match[str]) -> str:
    tag = match.group(1).casefold()
    content = match.group(2)

    if tag == "scp":
        previous = match.string[match.start() - 1] if match.start() else ""
        if len(content) == 1 and content.isupper() and previous.isalpha():
            return f" {content}"

    return content


def strip_markup(value: Any) -> Any:
    text = first_text(value)
    if is_blank(text):
        return pd.NA

    cleaned = decode_html_entities(str(text))

    for _ in range(3):
        next_text = COMPACT_TEXT_TAG_RE.sub(replace_compact_text_tag, cleaned)
        next_text = INLINE_TEXT_TAG_RE.sub(lambda match: f" {match.group(2)} ", next_text)
        if next_text == cleaned:
            break
        cleaned = next_text

    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([,.;:!?%)\]\}])", r"\1", cleaned)
    cleaned = re.sub(r"([\(\[\{])\s+", r"\1", cleaned)

    return cleaned or pd.NA


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
    # Keep this local so the script can run standalone when uploaded to Kaggle.
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


def normalize_title_key(value: Any) -> Any:
    text = strip_markup(value)
    if is_blank(text):
        return pd.NA

    return normalize_key_text(str(text))


def normalize_author_key(value: Any) -> str:
    names = split_multi_value(value)
    if not names:
        return ""

    return normalize_key_text(names[0])


def normalize_key_text(value: Any) -> str:
    text = str(value).casefold()
    output: list[str] = []
    previous_was_space = True

    for character in text:
        category_group = unicodedata.category(character)[0]
        if category_group in {"L", "M", "N"} or unicodedata.category(character) == "Cf":
            output.append(character)
            previous_was_space = False
        elif not previous_was_space:
            output.append(" ")
            previous_was_space = True

    return "".join(output).strip()


def normalize_field_source_policy(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("Field source policy must be a JSON object mapping field names to source lists.")

    policy: dict[str, list[str]] = {}
    for column, sources in value.items():
        if column not in COMMON_COLUMNS:
            raise ValueError(f"Unknown field in source policy: {column}")
        if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
            raise ValueError(f"Source policy for {column} must be a list of source dataset names.")

        cleaned_sources = [source.strip() for source in sources if source.strip()]
        if not cleaned_sources:
            raise ValueError(f"Source policy for {column} must include at least one source.")
        policy[column] = cleaned_sources

    return policy


def load_field_source_policy(path: Path | None) -> dict[str, list[str]]:
    policy = {column: list(sources) for column, sources in DEFAULT_FIELD_SOURCE_POLICY.items()}
    if path is None:
        return policy

    with path.open(encoding="utf-8") as handle:
        overrides = normalize_field_source_policy(json.load(handle))

    policy.update(overrides)
    return policy


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


def parsed_items(value: Any) -> list[Any]:
    parsed = parse_literal(value)
    if is_blank(parsed):
        return []
    if isinstance(parsed, (list, tuple, set)):
        return [item for item in parsed if not is_blank(item)]
    return [parsed]


def collect_nested_values(value: Any, keys: set[str]) -> list[Any]:
    parsed = parse_literal(value)
    if is_blank(parsed):
        return []

    if isinstance(parsed, dict):
        values: list[Any] = []
        normalized_keys = {key.casefold() for key in keys}
        for key, item in parsed.items():
            if str(key).casefold() in normalized_keys:
                values.extend(flatten_values(item))
            elif isinstance(item, (dict, list, tuple, set)):
                values.extend(collect_nested_values(item, keys))
        return values

    if isinstance(parsed, (list, tuple, set)):
        values: list[Any] = []
        for item in parsed:
            values.extend(collect_nested_values(item, keys))
        return values

    return []


def crossref_person_names(value: Any) -> Any:
    names: list[str] = []
    for person in parsed_items(value):
        if isinstance(person, dict):
            name = first_text(person.get("name"))
            if is_blank(name):
                given = first_text(person.get("given"))
                family = first_text(person.get("family"))
                parts = [str(part) for part in (given, family) if not is_blank(part)]
                name = " ".join(parts) if parts else pd.NA
            if not is_blank(name):
                names.append(str(name))
            continue

        text = first_text(person)
        if not is_blank(text):
            names.append(str(text))

    return unique_text(names)


def crossref_person_affiliations(value: Any) -> Any:
    affiliations: list[Any] = []
    for person in parsed_items(value):
        if not isinstance(person, dict):
            continue
        for affiliation in parsed_items(person.get("affiliation")):
            if isinstance(affiliation, dict):
                affiliations.extend(collect_nested_values(affiliation, {"name"}))
            else:
                affiliations.append(affiliation)

    return unique_text(affiliations)


def crossref_person_orcids(value: Any) -> Any:
    orcids: list[Any] = []
    for person in parsed_items(value):
        if not isinstance(person, dict):
            continue
        orcid = first_nonblank(person.get("ORCID"), person.get("orcid"))
        if not is_blank(orcid):
            orcids.append(orcid)

    return unique_text(orcids)


def crossref_funder_names(value: Any) -> Any:
    return unique_text(collect_nested_values(value, {"name"}))


def crossref_funder_dois(value: Any) -> Any:
    return unique_text(collect_nested_values(value, {"DOI", "doi"}))


def crossref_funder_ids(value: Any) -> Any:
    return unique_text(collect_nested_values(value, {"id"}))


def crossref_funder_awards(value: Any) -> Any:
    return unique_text(collect_nested_values(value, {"award", "award-number"}))


def crossref_license_urls(value: Any) -> Any:
    return unique_text(collect_nested_values(value, {"URL", "url"}))


def page_first(value: Any) -> Any:
    text = first_text(value)
    if is_blank(text):
        return pd.NA

    return re.split(r"\s*[-–—]\s*", str(text), maxsplit=1)[0].strip() or pd.NA


def page_last(value: Any) -> Any:
    text = first_text(value)
    if is_blank(text):
        return pd.NA

    parts = re.split(r"\s*[-–—]\s*", str(text), maxsplit=1)
    return (parts[-1].strip() if parts else "") or pd.NA


def fill_output_from_series(output: pd.DataFrame, target: str, values: pd.Series) -> None:
    mask = output[target].map(is_blank) & values.map(lambda value: not is_blank(value))
    if mask.any():
        output.loc[mask, target] = values.loc[mask]


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
    assign_column(output, "title", df, ["title"], strip_markup)
    assign_column(output, "publication_year", df, ["publication_year"], normalize_year)
    assign_column(output, "publication_date", df, ["publication_date"], normalize_date)
    assign_column(output, "type", df, ["type"])
    assign_column(output, "publication_type", df, ["type"])
    assign_column(output, "cited_by_count", df, ["cited_by_count"], normalize_int)
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
    source_dataset: str = "crossref",
) -> pd.DataFrame:
    output = empty_common_frame(df.index)
    output["source_dataset"] = source_dataset

    assign_column(output, "source_record_id", df, ["DOI", "doi"], normalize_doi)
    assign_column(output, "doi", df, ["DOI", "doi"], normalize_doi)
    assign_column(output, "url", df, ["URL", "url"])
    assign_column(output, "landing_page_url", df, ["URL", "url"])
    assign_column(output, "title", df, ["title"], strip_markup)
    assign_column(output, "subtitle", df, ["subtitle"], strip_markup)
    assign_column(output, "original_title", df, ["original-title", "original_title"], strip_markup)
    assign_column(output, "abstract", df, ["abstract"], strip_markup)
    assign_column(output, "publication_year", df, ["publication_year"], normalize_year)
    assign_column(output, "publication_date", df, ["issued.date-parts", "issued", "issued_date"], normalize_date_parts)
    assign_column(output, "created_date", df, ["created.date-parts", "created", "created_date"], normalize_date_parts)
    assign_column(
        output,
        "published_date",
        df,
        ["published.date-parts", "published", "published-online", "published_date"],
        normalize_date_parts,
    )
    assign_column(output, "type", df, ["type"])
    assign_column(output, "subtype", df, ["subtype"])
    assign_column(output, "publication_type", df, ["type"])
    assign_column(output, "authors", df, ["author_name"], unique_text)
    assign_column(output, "author_names", df, ["author_name"], unique_text)
    if "author" in df.columns:
        author_names = df["author"].map(crossref_person_names)
        fill_output_from_series(output, "author_names", author_names)
        fill_output_from_series(output, "authors", author_names)
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
    if "author" in df.columns:
        fill_output_from_series(
            output,
            "author_affiliations",
            df["author"].map(crossref_person_affiliations),
        )
        fill_output_from_series(output, "author_orcids", df["author"].map(crossref_person_orcids))
    output["editors"] = df.apply(lambda row: crossref_person_name(row, "editor"), axis=1)
    if "editor" in df.columns:
        fill_output_from_series(output, "editors", df["editor"].map(crossref_person_names))
    assign_column(output, "publisher", df, ["publisher"])
    assign_column(output, "publisher_location", df, ["publisher-location", "publisher_location"])
    assign_column(output, "journal", df, ["container-title", "container_title"], strip_markup)
    assign_column(output, "container_title", df, ["container-title", "container_title"], strip_markup)
    assign_column(output, "source_name", df, ["container-title", "container_title"], strip_markup)
    assign_column(output, "issn", df, ["ISSN", "issn"], unique_text)
    assign_column(output, "issn_l", df, ["ISSN", "issn"], first_text)
    assign_column(output, "volume", df, ["volume"])
    assign_column(output, "issue", df, ["issue"])
    assign_column(output, "page", df, ["page"])
    if "page" in df.columns:
        fill_output_from_series(output, "first_page", df["page"].map(page_first))
        fill_output_from_series(output, "last_page", df["page"].map(page_last))
    assign_column(output, "article_number", df, ["article-number", "article_number"])
    assign_column(output, "language", df, ["language"])
    assign_column(output, "license_url", df, ["license_URL", "license_url"])
    if "license" in df.columns:
        fill_output_from_series(output, "license_url", df["license"].map(crossref_license_urls))
    assign_column(output, "cited_by_count", df, ["is-referenced-by-count"], normalize_int)
    assign_column(output, "is_referenced_by_count", df, ["is-referenced-by-count"], normalize_int)
    assign_column(output, "reference_count", df, ["reference-count", "references-count"], normalize_int)
    assign_column(output, "references_json", df, ["references_json", "reference"], unique_text)
    assign_column(output, "funder_name", df, ["funder_name"], unique_text)
    assign_column(output, "funder_doi", df, ["funder_DOI", "funder_doi"], unique_text)
    assign_column(output, "funder_id", df, ["funder_id"], unique_text)
    assign_column(output, "funder_award", df, ["funder_award"], unique_text)
    if "funder" in df.columns:
        fill_output_from_series(output, "funder_name", df["funder"].map(crossref_funder_names))
        fill_output_from_series(output, "funder_doi", df["funder"].map(crossref_funder_dois))
        fill_output_from_series(output, "funder_id", df["funder"].map(crossref_funder_ids))
        fill_output_from_series(output, "funder_award", df["funder"].map(crossref_funder_awards))
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
    assign_column(output, "title", df, ["title"], strip_markup)
    assign_column(output, "abstract", df, ["abstract"], strip_markup)
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
    if source_dataset == "sljol":
        return normalize_crossref(
            df,
            include_raw_json=include_raw_json,
            source_dataset="sljol",
        )
    if source_dataset == "repositories_combined":
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

    source = row.get("source_dataset")
    source_record_id = row.get("source_record_id")
    if not is_blank(source) and not is_blank(source_record_id):
        return (
            f"source_record:{source}|{source_record_id}",
            "source_record_id",
            "No DOI; kept by source dataset and original source record ID.",
        )

    return (
        f"row:{row_number}",
        "row_number",
        "No DOI or source record ID; kept by input row number.",
    )


def record_merge_key(row: pd.Series, row_number: int) -> str:
    return record_merge_info(row, row_number)[0]


def manual_review_info(row: pd.Series) -> tuple[str, str, str] | None:
    doi = normalize_doi(row.get("doi"))
    if not is_blank(doi):
        return None

    title_key = normalize_title_key(row.get("title"))
    year = normalize_year(row.get("publication_year"))
    if is_blank(title_key) or is_blank(year):
        return None

    author_value = row.get("author_names")
    if is_blank(author_value):
        author_value = row.get("authors")
    author_key = normalize_author_key(author_value)

    if author_key:
        return (
            f"title_year_author:{title_key}|{year}|{author_key}",
            "title_year_first_author",
            "Missing DOI; possible match by normalized title, publication year, and first author. Manual inspection required.",
        )

    return (
        f"title_year:{title_key}|{year}",
        "title_year",
        "Missing DOI and first author; possible match by normalized title and publication year. Manual inspection required.",
    )


def completeness_score(row: pd.Series) -> int:
    ignored = {
        "source_dataset",
        "source_record_id",
        "source_datestamp",
        "raw_source_json",
    }
    return sum(not is_blank(row[column]) for column in COMMON_COLUMNS if column not in ignored)


def ordered_group(
    group: pd.DataFrame,
    *,
    column: str | None = None,
    field_source_policy: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    ordered = group.copy()
    ordered["_completeness"] = ordered.apply(completeness_score, axis=1)
    sort_columns = ["_completeness"]
    ascending = [False]

    if column is not None and field_source_policy is not None and column in field_source_policy:
        source_order = {
            source: index
            for index, source in enumerate(field_source_policy[column])
        }
        ordered["_field_source_priority"] = (
            ordered["source_dataset"].map(source_order).fillna(len(source_order) + 99)
        )
        sort_columns.insert(0, "_field_source_priority")
        ascending.insert(0, True)

    return ordered.sort_values(
        sort_columns,
        ascending=ascending,
        kind="stable",
    )


def merge_group(
    group: pd.DataFrame,
    *,
    field_source_policy: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    if field_source_policy is None:
        field_source_policy = DEFAULT_FIELD_SOURCE_POLICY

    merged: dict[str, Any] = {}

    for column in COMMON_COLUMNS:
        ordered = ordered_group(
            group,
            column=column,
            field_source_policy=field_source_policy,
        )

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


def comparable_value(column: str, value: Any) -> Any:
    if is_blank(value):
        return pd.NA

    if column == "doi":
        return normalize_doi(value)
    if column == "title":
        return normalize_title_key(value)
    if column == "publication_year":
        return normalize_year(value)
    if column in {
        "cited_by_count",
        "is_referenced_by_count",
        "reference_count",
        "referenced_works_count",
        "author_count",
    }:
        return normalize_int(value)
    if column in {"is_oa"}:
        return normalize_bool(value)
    if column in MULTI_VALUE_COLUMNS:
        values = sorted({normalize_key_text(item) for item in split_multi_value(value)})
        return ";".join(values) if values else pd.NA

    return normalize_key_text(clean_text(value))


def conflict_fields(group: pd.DataFrame) -> Any:
    skipped = PROVENANCE_COLUMNS | {"raw_source_json"}
    fields: list[str] = []

    for column in COMMON_COLUMNS:
        if column in skipped:
            continue

        values = {
            comparable
            for value in group[column]
            if not is_blank(comparable := comparable_value(column, value))
        }
        if len(values) > 1:
            fields.append(column)

    return "; ".join(fields) if fields else pd.NA


def min_title_similarity(group: pd.DataFrame) -> Any:
    title_keys = sorted(
        {
            str(title_key)
            for value in group["title"]
            if not is_blank(title_key := normalize_title_key(value))
        }
    )
    if len(title_keys) < 2:
        return pd.NA

    scores = [
        SequenceMatcher(None, left, right).ratio()
        for index, left in enumerate(title_keys)
        for right in title_keys[index + 1 :]
    ]
    return round(min(scores), 4) if scores else pd.NA


def publication_year_span(group: pd.DataFrame) -> Any:
    years = sorted(
        {
            int(year)
            for value in group["publication_year"]
            if not is_blank(year := normalize_year(value))
        }
    )
    if len(years) < 2:
        return pd.NA
    return years[-1] - years[0]


def artifact_title_flag(group: pd.DataFrame) -> bool:
    for value in group["title"]:
        if is_blank(value):
            continue
        if ARTIFACT_TITLE_RE.search(str(value)):
            return True
    return False


def duplicate_threshold_review_info(group: pd.DataFrame) -> dict[str, Any]:
    """Apply finalized duplicate thresholds to an automatic merge group."""

    title_similarity = min_title_similarity(group)
    year_span = publication_year_span(group)
    artifact_flag = artifact_title_flag(group)
    reasons: list[str] = []

    if (
        not is_blank(title_similarity)
        and title_similarity < DUPLICATE_REVIEW_TITLE_SIMILARITY_THRESHOLD
    ):
        reasons.append(
            "same DOI but normalized title similarity below "
            f"{DUPLICATE_REVIEW_TITLE_SIMILARITY_THRESHOLD:.2f}"
        )
    if not is_blank(year_span) and year_span > DUPLICATE_REVIEW_YEAR_SPAN_THRESHOLD:
        reasons.append(
            "same DOI but publication-year span greater than "
            f"{DUPLICATE_REVIEW_YEAR_SPAN_THRESHOLD}"
        )
    if artifact_flag:
        reasons.append("artifact-like title requires review")

    return {
        "duplicate_title_similarity_min": title_similarity,
        "duplicate_publication_year_span": year_span,
        "duplicate_artifact_title_flag": artifact_flag,
        "duplicate_threshold_review_flag": bool(reasons),
        "duplicate_threshold_review_reason": "; ".join(reasons) if reasons else pd.NA,
    }


def numeric_difference(left: Any, right: Any) -> Any:
    left_number = normalize_int(left)
    right_number = normalize_int(right)

    if is_blank(left_number) or is_blank(right_number):
        return pd.NA

    return int(left_number) - int(right_number)


def first_source_value(group: pd.DataFrame, column: str, source_dataset: str) -> Any:
    source_rows = group.loc[group["source_dataset"] == source_dataset]
    if source_rows.empty:
        return pd.NA

    ordered = source_rows.copy()
    ordered["_completeness"] = ordered.apply(completeness_score, axis=1)
    ordered = ordered.sort_values("_completeness", ascending=False, kind="stable")

    for value in ordered[column]:
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
    citation_difference = numeric_difference(
        first_source_value(group, "cited_by_count", "openalex"),
        first_source_value(group, "is_referenced_by_count", "crossref"),
    )
    reference_difference = numeric_difference(
        first_source_value(group, "referenced_works_count", "openalex"),
        first_source_value(group, "reference_count", "crossref"),
    )
    threshold_review = duplicate_threshold_review_info(group)

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
        "conflict_fields": conflict_fields(group),
        "citation_count_difference_oa_minus_crossref": citation_difference,
        "citation_count_divergence_flag": (
            abs(citation_difference) >= 10 if not is_blank(citation_difference) else pd.NA
        ),
        "reference_count_difference_oa_minus_crossref": reference_difference,
        "reference_count_divergence_flag": (
            reference_difference != 0 if not is_blank(reference_difference) else pd.NA
        ),
        **threshold_review,
        "input_row_numbers": "; ".join(str(index + 1) for index in group.index),
    }


def singleton_merge_log_row(
    merged_row_number: int,
    merge_key: str,
    row: pd.Series,
) -> dict[str, Any]:
    merged = {column: row[column] for column in COMMON_COLUMNS}

    return {
        "merged_row_number": merged_row_number,
        "action": "kept_single_record",
        "was_merged": False,
        "merge_method": row["_merge_method"],
        "merge_key": merge_key,
        "merge_reason": row["_merge_reason"],
        "input_record_count": 1,
        "source_datasets": row["source_dataset"],
        "source_record_ids": row["source_record_id"],
        "openalex_ids": row["openalex_id"],
        "normalized_dois": row["doi"],
        "final_doi": row["doi"],
        "final_title": row["title"],
        "final_publication_year": row["publication_year"],
        "final_authors": first_nonblank(row["author_names"], row["authors"]),
        "final_journal": first_nonblank(row["journal"], row["container_title"]),
        "non_empty_final_fields": completeness_score(pd.Series(merged)),
        "conflict_fields": pd.NA,
        "citation_count_difference_oa_minus_crossref": pd.NA,
        "citation_count_divergence_flag": pd.NA,
        "reference_count_difference_oa_minus_crossref": pd.NA,
        "reference_count_divergence_flag": pd.NA,
        "duplicate_title_similarity_min": pd.NA,
        "duplicate_publication_year_span": pd.NA,
        "duplicate_artifact_title_flag": False,
        "duplicate_threshold_review_flag": False,
        "duplicate_threshold_review_reason": pd.NA,
        "input_row_numbers": str(row["_input_row_number"]),
    }


def manual_review_row(
    candidate_group_number: int,
    candidate_key: str,
    group: pd.DataFrame,
) -> dict[str, Any]:
    group_size = len(group)
    review_method = first_text(group["_manual_review_method"].iloc[0])
    review_reason = first_text(group["_manual_review_reason"].iloc[0])

    return {
        "candidate_group_number": candidate_group_number,
        "review_status": "needs_manual_review",
        "review_method": review_method,
        "candidate_key": candidate_key,
        "review_reason": review_reason,
        "input_record_count": group_size,
        "source_datasets": unique_series_text(group["source_dataset"]),
        "source_record_ids": unique_series_text(group["source_record_id"]),
        "openalex_ids": unique_series_text(group["openalex_id"]),
        "normalized_dois": unique_series_text(group["doi"]),
        "titles": unique_series_text(group["title"]),
        "publication_years": unique_series_text(group["publication_year"]),
        "authors": unique_series_text(group["author_names"]),
        "journals": unique_series_text(group["journal"]),
        "urls": unique_series_text(group["url"]),
        "input_row_numbers": "; ".join(str(index + 1) for index in group.index),
    }


def build_manual_review_candidates(all_records: pd.DataFrame) -> pd.DataFrame:
    working = all_records.copy()
    review_infos = [manual_review_info(row) for _, row in working.iterrows()]
    working["_manual_review_key"] = [info[0] if info else pd.NA for info in review_infos]
    working["_manual_review_method"] = [info[1] if info else pd.NA for info in review_infos]
    working["_manual_review_reason"] = [info[2] if info else pd.NA for info in review_infos]

    candidate_rows: list[dict[str, Any]] = []
    candidates = working.loc[working["_manual_review_key"].map(lambda value: not is_blank(value))]

    for candidate_group_number, (candidate_key, group) in enumerate(
        candidates.groupby("_manual_review_key", sort=False, dropna=False),
        start=1,
    ):
        if len(group) < 2:
            continue
        candidate_rows.append(
            manual_review_row(
                len(candidate_rows) + 1,
                str(candidate_key),
                group,
            )
        )

    return pd.DataFrame(candidate_rows)


def deduplicate_publications(
    all_records: pd.DataFrame,
    *,
    return_log: bool = False,
    field_source_policy: dict[str, list[str]] | None = None,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    working = all_records.copy()
    merge_infos = [
        record_merge_info(row, row_number)
        for row_number, (_, row) in enumerate(working.iterrows(), start=1)
    ]
    working["_merge_key"] = [merge_info[0] for merge_info in merge_infos]
    working["_merge_method"] = [merge_info[1] for merge_info in merge_infos]
    working["_merge_reason"] = [merge_info[2] for merge_info in merge_infos]
    working["_input_row_number"] = range(1, len(working) + 1)
    working["_group_size"] = working["_merge_key"].map(
        working["_merge_key"].value_counts(sort=False, dropna=False)
    )

    merged_rows: list[dict[str, Any]] = []
    merge_log_rows: list[dict[str, Any]] = []
    duplicate_group_outputs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    duplicate_records = working.loc[working["_group_size"] > 1]
    for merge_key, group in duplicate_records.groupby("_merge_key", sort=False, dropna=False):
        merged = merge_group(group, field_source_policy=field_source_policy)
        duplicate_group_outputs[str(merge_key)] = (
            merged,
            merge_log_row(0, str(merge_key), group, merged),
        )

    first_group_rows = working.drop_duplicates("_merge_key", keep="first")
    for merged_row_number, (_, row) in enumerate(first_group_rows.iterrows(), start=1):
        merge_key = str(row["_merge_key"])
        if row["_group_size"] > 1:
            merged, log_row = duplicate_group_outputs[merge_key]
            log_row = log_row.copy()
            log_row["merged_row_number"] = merged_row_number
        else:
            merged = {column: row[column] for column in COMMON_COLUMNS}
            log_row = singleton_merge_log_row(merged_row_number, merge_key, row)

        merged_rows.append(merged)
        merge_log_rows.append(log_row)

    deduplicated = pd.DataFrame(merged_rows, columns=COMMON_COLUMNS)
    merge_log = pd.DataFrame(merge_log_rows)

    if return_log:
        return deduplicated, merge_log

    return deduplicated


def file_candidate_names(filenames: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(filenames, str):
        return (filenames,)
    return tuple(filenames)


def find_input_file(input_root: Path, filenames: str | tuple[str, ...] | list[str]) -> Path:
    candidate_names = file_candidate_names(filenames)

    for filename in candidate_names:
        direct_input = input_root / filename
        if direct_input.exists():
            return direct_input

    if input_root.exists():
        for filename in candidate_names:
            input_candidates = sorted(
                input_root.rglob(filename),
                key=lambda path: (len(path.parts), str(path)),
            )
            if input_candidates:
                return input_candidates[0]

    candidates: list[Path] = []
    if input_root != Path.cwd() and Path.cwd().exists():
        for filename in candidate_names:
            candidates.extend(Path.cwd().rglob(filename))

    if not candidates:
        expected = ", ".join(candidate_names)
        raise FileNotFoundError(
            f"Could not find any of: {expected}. In Kaggle, check /kaggle/input/*/."
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
    manual_review_candidates: pd.DataFrame,
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
                "metric": "manual_review_candidate_groups",
                "value": len(manual_review_candidates),
                "file": "common_publications_manual_review_candidates.csv",
            },
            {
                "metric": "manual_review_candidate_records",
                "value": (
                    int(manual_review_candidates["input_record_count"].sum())
                    if "input_record_count" in manual_review_candidates
                    else 0
                ),
                "file": "common_publications_manual_review_candidates.csv",
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
    manual_review_candidates: pd.DataFrame,
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
        f"Field source policy: {args.field_source_policy or 'built-in default'}",
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
            f"- manual-review candidate groups: {len(manual_review_candidates):,}",
            (
                "- manual-review candidate records: "
                f"{int(manual_review_candidates['input_record_count'].sum()):,}"
                if "input_record_count" in manual_review_candidates
                else "- manual-review candidate records: 0"
            ),
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
    parser.add_argument(
        "--field-source-policy",
        type=Path,
        default=None,
        help=(
            "Optional JSON object mapping common-schema fields to source-dataset "
            "ordered source lists. Unspecified fields use the built-in policy."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = {
        source_dataset: find_input_file(args.input_dir, EXPECTED_FILE_CANDIDATES[source_dataset])
        for source_dataset in EXPECTED_FILES
    }

    print("Found input files:")
    for source_dataset, path in input_paths.items():
        print(f"  {source_dataset}: {path}")

    if args.sample_rows:
        print(f"\nSample mode: reading first {args.sample_rows:,} rows from each file.")

    source_frames: dict[str, pd.DataFrame] = {}
    field_source_policy = load_field_source_policy(args.field_source_policy)
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
    manual_review_path = args.output_dir / "common_publications_manual_review_candidates.csv"

    print(f"\nWriting normalized records -> {all_records_path}", flush=True)
    all_records.to_csv(all_records_path, index=False)

    print("Deduplicating and building merge log...", flush=True)
    deduplicated, merge_log = deduplicate_publications(
        all_records,
        return_log=True,
        field_source_policy=field_source_policy,
    )

    print(f"Writing deduplicated records -> {deduplicated_path}", flush=True)
    deduplicated.to_csv(deduplicated_path, index=False)
    print(f"Writing merge log -> {merge_log_path}", flush=True)
    merge_log.to_csv(merge_log_path, index=False)

    print("Building manual-review candidate list...", flush=True)
    manual_review_candidates = build_manual_review_candidates(all_records)
    print(f"Writing manual-review candidates -> {manual_review_path}", flush=True)
    manual_review_candidates.to_csv(manual_review_path, index=False)
    schema_path = write_schema(args.output_dir)
    summary_path = write_summary(
        args.output_dir,
        input_paths=input_paths,
        source_frames=source_frames,
        all_records=all_records,
        deduplicated=deduplicated,
        manual_review_candidates=manual_review_candidates,
    )
    output_paths = {
        "all_records": all_records_path,
        "deduplicated": deduplicated_path,
        "merge_log": merge_log_path,
        "manual_review_candidates": manual_review_path,
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
        manual_review_candidates=manual_review_candidates,
        args=args,
        output_paths=output_paths,
    )

    print("\nDone.")
    print(f"  All normalized records: {len(all_records):,} -> {all_records_path}")
    print(f"  Deduplicated publications: {len(deduplicated):,} -> {deduplicated_path}")
    print(
        "  Manual-review candidate groups: "
        f"{len(manual_review_candidates):,} -> {manual_review_path}"
    )
    print(f"  Merge log: {merge_log_path}")
    print(f"  Run log: {run_log_path}")
    print(f"  Schema columns: {len(COMMON_COLUMNS):,} -> {schema_path}")
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
