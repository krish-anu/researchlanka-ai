"""Detailed data-quality validation reports."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from research_analytics.cleaning import (
    is_valid_doi,
    normalize_doi,
    normalize_publication_year,
    normalize_title_key,
)
from research_analytics.config import FrameworkConfig


@dataclass
class ValidationReport:
    total_records: int
    detected_columns: list[str]
    mapped_columns: dict[str, str]
    unmapped_columns: list[str]
    missing_required_columns: list[str]
    missing_value_percentages: dict[str, float]
    invalid_doi_count: int
    invalid_year_count: int
    duplicate_doi_count: int
    duplicate_title_count: int
    author_availability_percent: float
    institution_availability_percent: float
    citation_availability_percent: float
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_records(records: list[dict[str, Any]], config: FrameworkConfig) -> ValidationReport:
    """Validate mapped records without failing the full pipeline."""

    detected_columns = sorted({field for record in records for field in record if not field.startswith("_")})
    required_fields = list(config.validation.required)
    missing_required_columns = [field for field in required_fields if field not in detected_columns]
    missing_value_percentages = {
        field: _missing_percentage(records, field) for field in detected_columns
    }
    invalid_doi_count = sum(1 for record in records if _has_invalid_doi(record.get("doi")))
    invalid_year_count = sum(
        1 for record in records if _has_invalid_year(record.get("publication_year"), config)
    )
    duplicate_doi_count = _duplicate_count(
        normalize_doi(record.get("doi"))
        for record in records
        if record.get("doi") and is_valid_doi(record.get("doi"))
    )
    duplicate_title_count = _duplicate_count(
        normalize_title_key(record.get("title")) for record in records if record.get("title")
    )
    messages = []
    for field in missing_required_columns:
        messages.append(f"Required field is missing from the mapped dataset: {field}.")
    if "citation_count" not in detected_columns:
        messages.append("Citation analytics unavailable because citation_count is missing.")
    if "institutions" not in detected_columns:
        messages.append(
            "Institution collaboration analysis unavailable because institution metadata is missing."
        )
    if "authors" not in detected_columns:
        messages.append("Author network analysis unavailable because author metadata is missing.")

    return ValidationReport(
        total_records=len(records),
        detected_columns=detected_columns,
        mapped_columns=config.column_mapping,
        unmapped_columns=[
            column for column in detected_columns if column not in config.column_mapping.values()
        ],
        missing_required_columns=missing_required_columns,
        missing_value_percentages=missing_value_percentages,
        invalid_doi_count=invalid_doi_count,
        invalid_year_count=invalid_year_count,
        duplicate_doi_count=duplicate_doi_count,
        duplicate_title_count=duplicate_title_count,
        author_availability_percent=100 - _missing_percentage(records, "authors"),
        institution_availability_percent=100 - _missing_percentage(records, "institutions"),
        citation_availability_percent=100 - _missing_percentage(records, "citation_count"),
        messages=messages,
    )


def record_validation_errors(
    record: dict[str, Any],
    config: FrameworkConfig | None = None,
) -> list[str]:
    """Return record-level validation errors shared by all source adapters."""

    errors = []
    if config:
        for field in config.validation.required:
            if _is_blank(record.get(field)):
                errors.append(f"Missing required field: {field}")
        if config.validation.require_any and not any(
            not _is_blank(record.get(field)) for field in config.validation.require_any
        ):
            errors.append(
                "At least one identifying field is required: "
                + ", ".join(config.validation.require_any)
            )
    if _has_invalid_doi(record.get("doi")):
        errors.append("Invalid DOI value: doi")
    if config and _has_invalid_year(record.get("publication_year"), config):
        errors.append("Invalid publication year: publication_year")
    return errors


def _missing_percentage(records: list[dict[str, Any]], field: str) -> float:
    if not records:
        return 0.0
    missing = sum(1 for record in records if _is_blank(record.get(field)))
    return round(missing / len(records) * 100, 2)


def _duplicate_count(values) -> int:
    counter = Counter(value for value in values if value)
    return sum(count - 1 for count in counter.values() if count > 1)


def _has_invalid_doi(value: Any) -> bool:
    return not _is_blank(value) and not is_valid_doi(value)


def _has_invalid_year(value: Any, config: FrameworkConfig) -> bool:
    if _is_blank(value):
        return False
    year = normalize_publication_year(value)
    if year is None:
        return True
    minimum = config.cleaning.valid_year_minimum
    maximum = config.cleaning.valid_year_maximum
    if minimum is not None and year < minimum:
        return True
    if maximum is not None and year > maximum:
        return True
    return False


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().casefold() == "nan"
    if isinstance(value, list):
        return not value
    return False
