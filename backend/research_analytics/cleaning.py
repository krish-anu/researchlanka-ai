"""Configurable cleaning utilities for publication records."""

from __future__ import annotations

import ast
from datetime import date, datetime
import html
import json
import math
import re
import unicodedata
from typing import Any

from research_analytics.config import CleaningConfig

DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
DOI_VALUE_RE = re.compile(r"^10\.\d{4,9}/[^\s\"'<>]+$", re.IGNORECASE)
INLINE_TEXT_TAG_RE = re.compile(
    r"<\s*(sub|sup|i|b|em|strong|scp|inf)\b[^>]*>(.*?)<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
TITLE_SPACE_RE = re.compile(r"\s+")
UNICODE_WORD_JOINERS = {"\u200c", "\u200d"}
YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")
TITLE_ENTITY_FIXES = {
    "&squo;": "'",
    "&lsquo;": "'",
    "&rsquo;": "'",
}


def clean_record(record: dict[str, Any], config: CleaningConfig) -> dict[str, Any]:
    """Apply enabled cleaning rules and return a new record."""

    cleaned = dict(record)
    rules_applied: list[str] = []

    if config.normalize_doi:
        cleaned["doi"] = normalize_doi(cleaned.get("doi"))
        rules_applied.append("normalize_doi")

    if config.normalize_title:
        title = normalize_title(cleaned.get("title"))
        cleaned["title"] = title
        cleaned["normalized_title"] = normalize_title_key(title)
        rules_applied.append("normalize_title")

    if config.normalize_publication_dates:
        publication_date = normalize_publication_date(cleaned.get("publication_date"))
        publication_year = normalize_publication_year(
            cleaned.get("publication_year") or publication_date
        )
        if publication_date is None and publication_year is not None:
            publication_date = str(publication_year)
        cleaned["publication_date"] = publication_date
        cleaned["publication_year"] = publication_year
        rules_applied.append("normalize_publication_dates")

    if config.normalize_author_names:
        cleaned["authors"] = normalize_list_like(cleaned.get("authors"))
        rules_applied.append("normalize_author_names")

    if config.normalize_institutions:
        cleaned["institutions"] = normalize_list_like(cleaned.get("institutions"))
        rules_applied.append("normalize_institutions")

    provenance = dict(cleaned.get("_provenance") or {})
    provenance["cleaning_rules_applied"] = rules_applied
    cleaned["_provenance"] = provenance
    cleaned["processing_status"] = "cleaned"
    return cleaned


def normalize_doi(value: Any) -> str | None:
    """Normalize DOI strings without assuming that every record has a DOI."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    doi = str(value).strip().lower()
    if not doi or doi == "nan":
        return None
    doi = DOI_PREFIX_RE.sub("", doi).strip()
    doi = doi.replace(" ", "")
    doi = doi.rstrip(".,;:)]}")
    return doi or None


def is_valid_doi(value: Any) -> bool:
    """Return True when a value normalizes to a syntactically valid DOI."""

    doi = normalize_doi(value)
    return bool(doi and DOI_VALUE_RE.fullmatch(doi))


def decode_title_entities(value: str) -> str:
    """Decode nested HTML entities and common source-specific entity typos."""

    previous = value
    for _ in range(3):
        decoded = html.unescape(previous)
        for source, replacement in TITLE_ENTITY_FIXES.items():
            decoded = decoded.replace(source, replacement)
        if decoded == previous:
            break
        previous = decoded
    return previous


def replace_inline_title_tag(match: re.Match[str]) -> str:
    tag = match.group(1).casefold()
    content = match.group(2)
    previous = match.string[match.start() - 1] if match.start() else ""
    following = match.string[match.end()] if match.end() < len(match.string) else ""

    if tag in {"sub", "sup", "inf"} and content.strip().isalnum():
        return content.strip()

    if tag == "scp" and len(content.strip()) == 1 and content.strip().isupper():
        prefix = " " if previous.isalpha() and following.isalpha() else ""
        return f"{prefix}{content.strip()}"

    return f" {content} "


def normalize_title(value: Any) -> str | None:
    """Normalize publication titles for display and downstream matching."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None

    text = decode_title_entities(str(value))
    for _ in range(3):
        next_text = INLINE_TEXT_TAG_RE.sub(replace_inline_title_tag, text)
        if next_text == text:
            break
        text = next_text

    text = TAG_RE.sub(" ", text)
    text = TITLE_SPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\s+([,.;:!?%)\]\}])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    return text or None


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = TITLE_SPACE_RE.sub(" ", str(value)).strip()
    return text or None


def normalize_title_key(value: Any) -> str | None:
    text = normalize_title(value)
    if not text:
        return None
    output: list[str] = []
    previous_was_space = True
    for character in text.casefold():
        if (
            character.isalnum()
            or unicodedata.category(character).startswith("M")
            or character in UNICODE_WORD_JOINERS
        ):
            output.append(character)
            previous_was_space = False
        elif not previous_was_space:
            output.append(" ")
            previous_was_space = True
    return "".join(output).strip() or None


def normalize_publication_date(value: Any) -> str | None:
    """Normalize publication dates to YYYY, YYYY-MM, or YYYY-MM-DD."""

    if _is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    parsed = parse_literal(value)
    if isinstance(parsed, dict) and "date-parts" in parsed:
        return normalize_date_parts(parsed["date-parts"])
    if isinstance(parsed, list):
        return normalize_date_parts(parsed)

    text = normalize_text(parsed)
    if not text:
        return None
    if text[0] in "[{":
        reparsed = parse_literal(text)
        if reparsed is not text:
            return normalize_publication_date(reparsed)

    if re.fullmatch(r"\d{4}", text):
        return text

    year_month = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
    if year_month:
        year = int(year_month.group(1))
        month = int(year_month.group(2))
        return f"{year:04d}-{month:02d}" if 1 <= month <= 12 else f"{year:04d}"

    year_month_day = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if year_month_day:
        return format_date_parts(
            [
                int(year_month_day.group(1)),
                int(year_month_day.group(2)),
                int(year_month_day.group(3)),
            ]
        )

    slash_date = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if slash_date:
        first = int(slash_date.group(1))
        second = int(slash_date.group(2))
        year = int(slash_date.group(3))
        day, month = (first, second) if first > 12 else (second, first)
        return format_date_parts([year, month, day])

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def normalize_publication_year(value: Any) -> int | None:
    """Normalize a publication year or date-like value to an integer year."""

    if _is_blank(value) or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.year
    if isinstance(value, date):
        return value.year
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if not math.isnan(value) and value.is_integer() else None

    parsed = parse_literal(value)
    if isinstance(parsed, dict) and "date-parts" in parsed:
        return normalize_publication_year(parsed["date-parts"])
    if isinstance(parsed, list):
        normalized_date = normalize_date_parts(parsed)
        return normalize_publication_year(normalized_date)

    text = normalize_text(parsed)
    if not text:
        return None
    match = YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def normalize_date_parts(value: Any) -> str | None:
    parsed = parse_literal(value)
    if isinstance(parsed, dict) and "date-parts" in parsed:
        parsed = parsed["date-parts"]
    if not isinstance(parsed, list):
        return normalize_publication_date(parsed)

    parts = parsed[0] if parsed and isinstance(parsed[0], list) else parsed
    normalized_parts: list[int] = []
    for part in parts[:3]:
        if _is_blank(part):
            break
        try:
            normalized_parts.append(int(float(str(part).strip())))
        except ValueError:
            break
    return format_date_parts(normalized_parts)


def format_date_parts(parts: list[int]) -> str | None:
    if not parts:
        return None
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
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return f"{year:04d}-{month:02d}"


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


def normalize_list_like(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().casefold() == "nan"
    if isinstance(value, list):
        return not value
    return False
