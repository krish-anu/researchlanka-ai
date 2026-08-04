"""Source onboarding, preview, and status reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_analytics.adapters.base import SourceAdapter
from research_analytics.config import FrameworkConfig
from research_analytics.schema import STANDARD_PUBLICATION_FIELDS
from research_analytics.validation import record_validation_errors


@dataclass
class SourceValidationReport:
    source: str
    source_type: str
    records_inspected: int
    valid_records: int
    invalid_records: int
    missing_title: int
    missing_year: int
    missing_doi: int
    invalid_doi: int
    invalid_year: int
    unmapped_columns: list[str]
    preview: list[dict[str, Any]]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceStatus:
    source_name: str
    source_type: str
    enabled: bool
    current_status: str
    records_collected: int = 0
    records_rejected: int = 0
    last_successful_run: str | None = None
    last_failed_run: str | None = None
    error_message: str | None = None
    next_scheduled_run: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_source_sample(
    adapter: SourceAdapter,
    config: FrameworkConfig,
    *,
    sample_size: int = 100,
) -> SourceValidationReport:
    """Inspect a source before full import so users can confirm mapping."""

    source_name = config.source.name or config.input.source_name
    source_type = config.source.type or config.input.format or "unknown"
    raw_records: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        adapter.connect()
    except Exception as exc:
        errors.append(f"Connection failed: {exc}")
        return SourceValidationReport(
            source=source_name,
            source_type=source_type,
            records_inspected=0,
            valid_records=0,
            invalid_records=0,
            missing_title=0,
            missing_year=0,
            missing_doi=0,
            invalid_doi=0,
            invalid_year=0,
            unmapped_columns=[],
            preview=[],
            errors=errors,
        )

    try:
        for raw_record in adapter.collect():
            raw_records.append(raw_record)
            if len(raw_records) >= sample_size:
                break
    except Exception as exc:
        errors.append(f"Sample collection failed: {exc}")

    transformed = []
    record_errors: list[list[str]] = []
    for raw_record in raw_records:
        try:
            record = adapter.transform(raw_record)
            transformed.append(record)
            record_errors.append(
                _unique_errors(adapter.validate(record) + record_validation_errors(record, config))
            )
        except Exception as exc:
            transformed.append({})
            record_errors.append([f"Transformation failed: {exc}"])

    invalid_records = sum(1 for item in record_errors if item)
    raw_columns = sorted({field for record in raw_records for field in record})
    mapped_source_columns = set(config.column_mapping)
    unmapped_columns = [
        field
        for field in raw_columns
        if field not in mapped_source_columns and field not in STANDARD_PUBLICATION_FIELDS
    ]

    return SourceValidationReport(
        source=source_name,
        source_type=source_type,
        records_inspected=len(raw_records),
        valid_records=len(raw_records) - invalid_records,
        invalid_records=invalid_records,
        missing_title=sum(1 for record in transformed if _is_blank(record.get("title"))),
        missing_year=sum(1 for record in transformed if _is_blank(record.get("publication_year"))),
        missing_doi=sum(1 for record in transformed if _is_blank(record.get("doi"))),
        invalid_doi=sum(
            1
            for record in transformed
            if "Invalid DOI value: doi" in record_validation_errors(record, config)
        ),
        invalid_year=sum(
            1
            for record in transformed
            if "Invalid publication year: publication_year"
            in record_validation_errors(record, config)
        ),
        unmapped_columns=unmapped_columns,
        preview=transformed[:5],
        errors=errors,
    )


def build_source_status(
    *,
    config: FrameworkConfig,
    records_collected: int,
    records_rejected: int,
    error_message: str | None = None,
) -> SourceStatus:
    now = datetime.now(timezone.utc).isoformat()
    return SourceStatus(
        source_name=config.source.name or config.input.source_name,
        source_type=config.source.type or config.input.format or "unknown",
        enabled=config.source.enabled,
        current_status="error" if error_message else "ok",
        records_collected=records_collected,
        records_rejected=records_rejected,
        last_successful_run=None if error_message else now,
        last_failed_run=now if error_message else None,
        error_message=error_message,
    )


def _unique_errors(errors: list[str]) -> list[str]:
    seen = set()
    unique = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            unique.append(error)
    return unique


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False
