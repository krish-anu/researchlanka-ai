"""Configurable cleaning utilities for publication records."""

from __future__ import annotations

import html
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

    if config.normalize_author_names:
        cleaned["authors"] = normalize_list_like(cleaned.get("authors"))
        rules_applied.append("normalize_author_names")

    if config.normalize_institutions:
        cleaned["institutions"] = normalize_list_like(cleaned.get("institutions"))
        rules_applied.append("normalize_institutions")

    provenance = dict(cleaned.get("_provenance") or {})
    provenance["cleaning_rules_applied"] = rules_applied
    cleaned["_provenance"] = provenance
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
