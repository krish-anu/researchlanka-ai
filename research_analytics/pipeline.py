"""Reusable configuration-driven research analytics pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from research_analytics.adapters.registry import build_adapter_from_config
from research_analytics.analytics import run_field_aware_analytics
from research_analytics.cleaning import clean_record
from research_analytics.config import FrameworkConfig
from research_analytics.deduplication import find_duplicate_candidates
from research_analytics.exporters import export_pipeline_outputs
from research_analytics.institutions import NationalInstitutionRegistry, enrich_national_context
from research_analytics.source_validation import SourceValidationReport, validate_source_sample
from research_analytics.validation import ValidationReport, validate_records


@dataclass
class PipelineResult:
    raw_records: list[dict[str, Any]] = field(default_factory=list)
    transformed_records: list[dict[str, Any]] = field(default_factory=list)
    valid_records: list[dict[str, Any]] = field(default_factory=list)
    invalid_records: list[dict[str, Any]] = field(default_factory=list)
    cleaned_records: list[dict[str, Any]] = field(default_factory=list)
    national_records: list[dict[str, Any]] = field(default_factory=list)
    duplicate_candidates: list[dict[str, Any]] = field(default_factory=list)
    deduplicated_records: list[dict[str, Any]] = field(default_factory=list)
    validation_report: ValidationReport | None = None
    analytics_summary: dict[str, Any] | None = None


class ResearchPipeline:
    """One reusable pipeline controlled by configuration."""

    def __init__(self, config: FrameworkConfig) -> None:
        self.config = config
        self.result = PipelineResult()
        self.adapter = self._build_input_adapter()
        self.institution_registry = NationalInstitutionRegistry.from_config(config)

    def connect(self) -> None:
        self.adapter.connect()

    def collect(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.collect:
            return self.result.raw_records
        self.result.raw_records = list(self.adapter.collect())
        return self.result.raw_records

    def transform(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.transform:
            self.result.transformed_records = list(self.result.raw_records)
            return self.result.transformed_records
        self.result.transformed_records = [
            self.adapter.transform(record) for record in self.result.raw_records
        ]
        return self.result.transformed_records

    def validate(self) -> ValidationReport:
        records = self.result.transformed_records or self.result.raw_records
        self.result.valid_records = []
        self.result.invalid_records = []
        for record in records:
            errors = self.adapter.validate(record)
            if errors:
                invalid_record = dict(record)
                invalid_record["_validation_errors"] = errors
                invalid_record["processing_status"] = "invalid"
                self.result.invalid_records.append(invalid_record)
            else:
                self.result.valid_records.append(record)
        self.result.validation_report = validate_records(records, self.config)
        return self.result.validation_report

    def preview(self, limit: int = 5) -> list[dict[str, Any]]:
        return self.adapter.preview(limit)

    def validate_source(self, sample_size: int = 100) -> SourceValidationReport:
        return validate_source_sample(self.adapter, self.config, sample_size=sample_size)

    def clean(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.clean:
            self.result.cleaned_records = list(self.result.valid_records)
            return self.result.cleaned_records
        self.result.cleaned_records = [
            clean_record(record, self.config.cleaning) for record in self.result.valid_records
        ]
        return self.result.cleaned_records

    def resolve_entities(self) -> list[dict[str, Any]]:
        records = self.result.cleaned_records or self.result.valid_records
        self.result.national_records = [
            enrich_national_context(
                record,
                self.institution_registry,
                national_country_code=self.config.project.country_code,
            )
            for record in records
        ]
        return self.result.national_records

    def deduplicate(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.deduplicate:
            self.result.deduplicated_records = list(
                self.result.national_records or self.result.cleaned_records
            )
            return self.result.deduplicated_records
        candidates = find_duplicate_candidates(
            self.result.national_records or self.result.cleaned_records,
            self.config.deduplication,
        )
        self.result.duplicate_candidates = [candidate.to_dict() for candidate in candidates]
        duplicate_right_indexes = {
            candidate.right_index
            for candidate in candidates
            if candidate.match_type == "doi" and candidate.merge_decision == "auto_merge"
        }
        source_records = self.result.national_records or self.result.cleaned_records
        self.result.deduplicated_records = [
            record
            for index, record in enumerate(source_records)
            if index not in duplicate_right_indexes
        ]
        return self.result.deduplicated_records

    def run_analytics(self) -> dict[str, Any]:
        if not self.config.pipeline.run_analytics:
            self.result.analytics_summary = {}
            return self.result.analytics_summary
        self.result.analytics_summary = run_field_aware_analytics(
            self.result.deduplicated_records or self.result.cleaned_records
        )
        return self.result.analytics_summary

    def export(self) -> None:
        if not self.config.pipeline.export:
            return
        export_pipeline_outputs(
            output_dir=self.config.export.output_dir,
            cleaned_records=self.result.cleaned_records,
            deduplicated_records=self.result.deduplicated_records,
            duplicate_candidates=self.result.duplicate_candidates,
            raw_records=self.result.raw_records,
            invalid_records=self.result.invalid_records,
            validation_report=(
                self.result.validation_report.to_dict()
                if self.result.validation_report
                else None
            ),
            analytics_summary=self.result.analytics_summary,
        )

    def run_all(self) -> PipelineResult:
        self.collect()
        self.transform()
        if self.config.pipeline.validate:
            self.validate()
        else:
            self.result.valid_records = list(self.result.transformed_records)
        self.clean()
        self.resolve_entities()
        self.deduplicate()
        self.run_analytics()
        self.export()
        return self.result

    def _build_input_adapter(self):
        return build_adapter_from_config(self.config)
