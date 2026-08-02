"""Detailed data-quality validation reports."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from research_analytics.cleaning import (
    is_valid_doi,
    normalize_doi,
    normalize_publication_date,
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
    year_date_mismatch_count: int
    missing_source_count: int
    source_name_mismatch_count: int
    duplicate_source_record_count: int
    source_record_conflict_count: int
    doi_year_conflict_count: int
    doi_title_conflict_count: int
    consistency_issue_count: int
    consistency_issues: list[dict[str, Any]]
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
    consistency_issues = _consistency_issues(records, config)
    year_date_mismatch_count = _issue_count(consistency_issues, "year_date_mismatch")
    missing_source_count = _issue_count(consistency_issues, "missing_source")
    source_name_mismatch_count = _issue_count(consistency_issues, "source_name_mismatch")
    duplicate_source_record_count = _issue_count(consistency_issues, "duplicate_source_record")
    source_record_conflict_count = _issue_count(consistency_issues, "source_record_conflict")
    doi_year_conflict_count = _issue_count(consistency_issues, "doi_year_conflict")
    doi_title_conflict_count = _issue_count(consistency_issues, "doi_title_conflict")
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
        year_date_mismatch_count=year_date_mismatch_count,
        missing_source_count=missing_source_count,
        source_name_mismatch_count=source_name_mismatch_count,
        duplicate_source_record_count=duplicate_source_record_count,
        source_record_conflict_count=source_record_conflict_count,
        doi_year_conflict_count=doi_year_conflict_count,
        doi_title_conflict_count=doi_title_conflict_count,
        consistency_issue_count=len(consistency_issues),
        consistency_issues=consistency_issues,
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
    if config and _has_year_date_mismatch(record):
        errors.append("Publication year does not match publication_date year")
    if config:
        source_name = _record_source_name(record)
        source_record_id = record.get("source_record_id")
        expected_source = _expected_source_name(config)
        if _is_blank(source_name):
            errors.append("Missing source name: source_name")
        elif expected_source and not _source_matches_expected(source_name, expected_source):
            errors.append(f"Unexpected source name: source_name must match {expected_source}")
        if not _is_blank(source_record_id) and _is_blank(source_name):
            errors.append("Source record ID requires source_name")
    return errors


def _consistency_issues(
    records: list[dict[str, Any]],
    config: FrameworkConfig,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_source = _expected_source_name(config)
    records_by_doi: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    records_by_source_key: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}

    for row_index, record in enumerate(records, start=1):
        doi = normalize_doi(record.get("doi"))
        if doi and is_valid_doi(doi):
            records_by_doi.setdefault(doi, []).append((row_index, record))

        source_name = _record_source_name(record)
        source_record_id = record.get("source_record_id")
        if _is_blank(source_name):
            issues.append(
                _issue(
                    row_index,
                    "missing_source",
                    "source_name",
                    source_name,
                    "Record has no source name or source dataset.",
                )
            )
        elif expected_source and not _source_matches_expected(source_name, expected_source):
            issues.append(
                _issue(
                    row_index,
                    "source_name_mismatch",
                    "source_name",
                    source_name,
                    f"Source name does not match configured source {expected_source}.",
                    expected=expected_source,
                )
            )

        if not _is_blank(source_record_id) and not _is_blank(source_name):
            source_key = (_source_key(source_name), str(source_record_id).strip())
            records_by_source_key.setdefault(source_key, []).append((row_index, record))

        if _has_year_date_mismatch(record):
            issues.append(
                _issue(
                    row_index,
                    "year_date_mismatch",
                    "publication_year",
                    record.get("publication_year"),
                    "Publication year does not match publication_date year.",
                    related_field="publication_date",
                    related_value=record.get("publication_date"),
                )
            )

    issues.extend(_doi_group_issues(records_by_doi))
    issues.extend(_source_key_group_issues(records_by_source_key))
    return issues


def _doi_group_issues(
    records_by_doi: dict[str, list[tuple[int, dict[str, Any]]]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for doi, group in records_by_doi.items():
        years = {
            year
            for _, record in group
            if (year := normalize_publication_year(record.get("publication_year"))) is not None
        }
        title_keys = {
            title_key
            for _, record in group
            if (title_key := normalize_title_key(record.get("title"))) is not None
        }
        rows = [row_index for row_index, _ in group]

        if len(years) > 1:
            issues.append(
                _issue(
                    None,
                    "doi_year_conflict",
                    "doi",
                    doi,
                    "Same DOI appears with conflicting publication years.",
                    related_field="publication_year",
                    related_value=sorted(years),
                    rows=rows,
                )
            )
        if len(title_keys) > 1:
            issues.append(
                _issue(
                    None,
                    "doi_title_conflict",
                    "doi",
                    doi,
                    "Same DOI appears with conflicting normalized titles.",
                    related_field="title",
                    related_value=sorted(title_keys),
                    rows=rows,
                )
            )
    return issues


def _source_key_group_issues(
    records_by_source_key: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for (source_name, source_record_id), group in records_by_source_key.items():
        if len(group) < 2:
            continue

        rows = [row_index for row_index, _ in group]
        issues.append(
            _issue(
                None,
                "duplicate_source_record",
                "source_record_id",
                source_record_id,
                "Same source name and source record ID appears more than once.",
                related_field="source_name",
                related_value=source_name,
                rows=rows,
            )
        )

        signatures = {
            (
                normalize_doi(record.get("doi")) or "",
                normalize_publication_year(record.get("publication_year")),
                normalize_title_key(record.get("title")) or "",
            )
            for _, record in group
        }
        if len(signatures) > 1:
            issues.append(
                _issue(
                    None,
                    "source_record_conflict",
                    "source_record_id",
                    source_record_id,
                    "Same source record key maps to conflicting DOI, year, or title evidence.",
                    related_field="source_name",
                    related_value=source_name,
                    rows=rows,
                )
            )
    return issues


def _issue(
    row_index: int | None,
    issue_type: str,
    field: str,
    value: Any,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    issue = {
        "row_index": row_index,
        "issue_type": issue_type,
        "field": field,
        "value": value,
        "message": message,
    }
    issue.update(extra)
    return issue


def _issue_count(issues: list[dict[str, Any]], issue_type: str) -> int:
    return sum(1 for issue in issues if issue["issue_type"] == issue_type)


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


def _has_year_date_mismatch(record: dict[str, Any]) -> bool:
    publication_year = normalize_publication_year(record.get("publication_year"))
    publication_date = normalize_publication_date(record.get("publication_date"))
    date_year = normalize_publication_year(publication_date)
    return publication_year is not None and date_year is not None and publication_year != date_year


def _expected_source_name(config: FrameworkConfig) -> str | None:
    return config.source.name or config.input.source_name


def _record_source_name(record: dict[str, Any]) -> Any:
    return record.get("source_name") or record.get("source_dataset")


def _source_key(value: Any) -> str:
    return ";".join(part.strip().casefold() for part in str(value).split(";") if part.strip())


def _source_matches_expected(value: Any, expected: str) -> bool:
    expected_key = expected.strip().casefold()
    return expected_key in {part.strip().casefold() for part in str(value).split(";")}


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
