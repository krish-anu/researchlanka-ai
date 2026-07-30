"""Reusable configuration-driven research analytics pipeline."""

from __future__ import annotations

import logging
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


logger = logging.getLogger(__name__)


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
    database_load_count: int = 0


class ResearchPipeline:
    """One reusable pipeline controlled by configuration."""

    def __init__(self, config: FrameworkConfig) -> None:
        self.config = config
        self.result = PipelineResult()
        self.adapter = self._build_input_adapter()
        self.institution_registry = NationalInstitutionRegistry.from_config(config)

    def connect(self) -> None:
        logger.info("Checking source connection")
        self.adapter.connect()
        logger.info("Source connection check complete")

    def collect(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.collect:
            logger.info("Collect stage skipped by configuration")
            return self.result.raw_records
        logger.info("Collect stage started")
        self.result.raw_records = list(self.adapter.collect())
        logger.info("Collect stage complete: %s raw records", len(self.result.raw_records))
        return self.result.raw_records

    def transform(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.transform:
            self.result.transformed_records = list(self.result.raw_records)
            logger.info(
                "Transform stage skipped by configuration: %s records carried forward",
                len(self.result.transformed_records),
            )
            return self.result.transformed_records
        logger.info("Transform stage started: %s raw records", len(self.result.raw_records))
        self.result.transformed_records = [
            self.adapter.transform(record) for record in self.result.raw_records
        ]
        logger.info(
            "Transform stage complete: %s transformed records",
            len(self.result.transformed_records),
        )
        return self.result.transformed_records

    def validate(self) -> ValidationReport:
        logger.info("Validate stage started")
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
        logger.info(
            "Validate stage complete: %s valid, %s invalid",
            len(self.result.valid_records),
            len(self.result.invalid_records),
        )
        return self.result.validation_report

    def preview(self, limit: int = 5) -> list[dict[str, Any]]:
        return self.adapter.preview(limit)

    def validate_source(self, sample_size: int = 100) -> SourceValidationReport:
        return validate_source_sample(self.adapter, self.config, sample_size=sample_size)

    def clean(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.clean:
            self.result.cleaned_records = list(self.result.valid_records)
            logger.info(
                "Clean stage skipped by configuration: %s records carried forward",
                len(self.result.cleaned_records),
            )
            return self.result.cleaned_records
        logger.info("Clean stage started: %s valid records", len(self.result.valid_records))
        self.result.cleaned_records = [
            clean_record(record, self.config.cleaning) for record in self.result.valid_records
        ]
        logger.info("Clean stage complete: %s cleaned records", len(self.result.cleaned_records))
        return self.result.cleaned_records

    def resolve_entities(self) -> list[dict[str, Any]]:
        logger.info("Entity resolution stage started")
        records = self.result.cleaned_records or self.result.valid_records
        self.result.national_records = [
            enrich_national_context(
                record,
                self.institution_registry,
                national_country_code=self.config.project.country_code,
            )
            for record in records
        ]
        logger.info(
            "Entity resolution stage complete: %s records",
            len(self.result.national_records),
        )
        return self.result.national_records

    def deduplicate(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.deduplicate:
            self.result.deduplicated_records = list(
                self.result.national_records or self.result.cleaned_records
            )
            logger.info(
                "Deduplicate stage skipped by configuration: %s records carried forward",
                len(self.result.deduplicated_records),
            )
            return self.result.deduplicated_records
        source_records = self.result.national_records or self.result.cleaned_records
        logger.info("Deduplicate stage started: %s records", len(source_records))
        candidates = find_duplicate_candidates(
            source_records,
            self.config.deduplication,
        )
        self.result.duplicate_candidates = [candidate.to_dict() for candidate in candidates]
        duplicate_right_indexes = {
            candidate.right_index
            for candidate in candidates
            if candidate.match_type == "doi" and candidate.merge_decision == "auto_merge"
        }
        self.result.deduplicated_records = [
            record
            for index, record in enumerate(source_records)
            if index not in duplicate_right_indexes
        ]
        logger.info(
            "Deduplicate stage complete: %s candidates, %s deduplicated records",
            len(self.result.duplicate_candidates),
            len(self.result.deduplicated_records),
        )
        return self.result.deduplicated_records

    def run_analytics(self) -> dict[str, Any]:
        if not self.config.pipeline.run_analytics:
            self.result.analytics_summary = {}
            logger.info("Analytics stage skipped by configuration")
            return self.result.analytics_summary
        logger.info("Analytics stage started")
        self.result.analytics_summary = run_field_aware_analytics(
            self.result.deduplicated_records or self.result.cleaned_records
        )
        logger.info("Analytics stage complete")
        return self.result.analytics_summary

    def export(self) -> None:
        if not self.config.pipeline.export:
            logger.info("Export stage skipped by configuration")
            return
        logger.info("Export stage started: %s", self.config.export.output_dir)
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
        logger.info("Export stage complete: %s", self.config.export.output_dir)

    def load_database(self) -> int:
        if not self.config.pipeline.load_database:
            self.result.database_load_count = 0
            logger.info("Database load stage skipped by configuration")
            return self.result.database_load_count

        from src.database.loader import load_final_publications

        records = self.result.deduplicated_records or self.result.cleaned_records
        logger.info("Database load stage started: %s records", len(records))
        self.result.database_load_count = load_final_publications(records)
        logger.info(
            "Database load stage complete: %s records",
            self.result.database_load_count,
        )
        return self.result.database_load_count

    def run_all(self) -> PipelineResult:
        logger.info("Pipeline run started: %s", self.config.project.name)
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
        self.load_database()
        self.export()
        logger.info(
            "Pipeline run complete: %s raw, %s cleaned, %s deduplicated",
            len(self.result.raw_records),
            len(self.result.cleaned_records),
            len(self.result.deduplicated_records),
        )
        return self.result

    def _build_input_adapter(self):
        return build_adapter_from_config(self.config)
