"""Publication metadata normalization for AI relevance decisions."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from src.utils.column_resolve import clean_str, first_present, is_present


PUBLICATION_ID_COLUMNS = (
    "record_number",
    "publication_id",
    "openalex_id",
    "doi",
    "source_record_id",
)
AI_EVIDENCE_COLUMNS = (
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
)
PRESERVED_METADATA_COLUMNS = (
    "record_number",
    "openalex_id",
    "doi",
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
    "publication_year",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
)


@dataclass(frozen=True)
class PublicationMetadata:
    """Metadata supplied to Gemini for exactly one publication."""

    publication_id: str
    title: str
    abstract: str
    keywords: str
    topics: str
    concepts: str
    primary_topic: str
    primary_subfield: str
    primary_field: str
    primary_domain: str

    def as_prompt_payload(self) -> dict[str, str]:
        return {
            "publication_id": self.publication_id,
            "title": self.title,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "topics": self.topics,
            "concepts": self.concepts,
            "primary_topic": self.primary_topic,
            "primary_subfield": self.primary_subfield,
            "primary_field": self.primary_field,
            "primary_domain": self.primary_domain,
        }


def normalize_multivalue(value: Any) -> str:
    """Render nulls, lists, JSON/list-like strings, and scalars as compact text."""

    if not is_present(value):
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item).strip() for item in value if clean_str(item))
    if isinstance(value, dict):
        return "; ".join(f"{key}: {item}" for key, item in value.items() if is_present(item))

    text = str(value).strip()
    if text == "" or text.casefold() in {"nan", "none", "null"}:
        return ""

    if (text.startswith("[") and text.endswith("]")) or (
        text.startswith("{") and text.endswith("}")
    ):
        parsed: Any
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return text
        return normalize_multivalue(parsed)

    return text


def publication_id(record: Mapping[str, Any], fallback: int | str) -> str:
    value, _ = first_present(record, PUBLICATION_ID_COLUMNS)
    return normalize_multivalue(value) or f"row-{fallback}"


def publication_metadata(record: Mapping[str, Any], *, fallback: int | str = "") -> PublicationMetadata:
    """Build the exact evidence payload allowed for AI relevance classification."""

    return PublicationMetadata(
        publication_id=publication_id(record, fallback),
        title=normalize_multivalue(record.get("title")),
        abstract=normalize_multivalue(record.get("abstract")),
        keywords=normalize_multivalue(record.get("keywords")),
        topics=normalize_multivalue(record.get("topics")),
        concepts=normalize_multivalue(record.get("concepts")),
        primary_topic=normalize_multivalue(record.get("primary_topic")),
        primary_subfield=normalize_multivalue(record.get("primary_subfield")),
        primary_field=normalize_multivalue(record.get("primary_field")),
        primary_domain=normalize_multivalue(record.get("primary_domain")),
    )


def combined_evidence_text(record: Mapping[str, Any]) -> str:
    """Concatenate only allowed evidence fields for sampling/search signals."""

    return " ".join(
        normalize_multivalue(record.get(column))
        for column in AI_EVIDENCE_COLUMNS
        if normalize_multivalue(record.get(column))
    ).casefold()


def present_metadata_columns(columns: list[str]) -> list[str]:
    return [column for column in PRESERVED_METADATA_COLUMNS if column in columns]
