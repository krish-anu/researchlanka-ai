"""Reusable configuration-driven research analytics pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from research_analytics.adapters.registry import build_adapter_from_config
from research_analytics.analytics import run_field_aware_analytics
from research_analytics.cleaning import clean_record
from research_analytics.config import FrameworkConfig, SourceConfig
from research_analytics.deduplication import find_duplicate_candidates
from research_analytics.exporters import export_pipeline_outputs
from research_analytics.institutions import NationalInstitutionRegistry, enrich_national_context
from research_analytics.source_validation import SourceValidationReport, validate_source_sample
from research_analytics.validation import (
    ValidationReport,
    record_validation_errors,
    validate_records,
)


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
    classification_result: dict[str, Any] | None = None
    topic_modeling_result: dict[str, Any] | None = None


class ResearchPipeline:
    """One reusable pipeline controlled by configuration."""

    def __init__(self, config: FrameworkConfig) -> None:
        self.config = config
        self.result = PipelineResult()
        self.adapters = self._build_input_adapters()
        self.adapter = self.adapters[0]
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
        records: list[dict[str, Any]] = []
        for adapter_index, adapter in enumerate(self.adapters):
            source_records = list(adapter.collect())
            records.extend(
                _tag_pipeline_source(record, adapter_index=adapter_index, source_index=index)
                for index, record in enumerate(source_records)
            )
            logger.info(
                "Collected %s raw records from adapter %s",
                len(source_records),
                adapter.__class__.__name__,
            )
        self.result.raw_records = records
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
            _tag_pipeline_source(
                self._adapter_for_record(record).transform(_untag_pipeline_source(record)),
                adapter_index=int(record.get("_pipeline_adapter_index", 0)),
                source_index=int(record.get("_pipeline_source_index", 0)),
            )
            for record in self.result.raw_records
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
            adapter = self._adapter_for_record(record)
            errors = _unique_errors(
                adapter.validate(record) + record_validation_errors(record, self.config)
            )
            if errors:
                invalid_record = _untag_pipeline_source(record)
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
            _untag_pipeline_source(clean_record(record, self.config.cleaning))
            for record in self.result.valid_records
        ]
        logger.info("Clean stage complete: %s cleaned records", len(self.result.cleaned_records))
        return self.result.cleaned_records

    def resolve_entities(self) -> list[dict[str, Any]]:
        if not self.config.pipeline.resolve_entities:
            self.result.national_records = list(self.result.cleaned_records or self.result.valid_records)
            logger.info(
                "Entity resolution stage skipped by configuration: %s records carried forward",
                len(self.result.national_records),
            )
            return self.result.national_records
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

    def load_database(
        self,
        *,
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> int:
        if not self.config.pipeline.load_database:
            self.result.database_load_count = 0
            logger.info("Database load stage skipped by configuration")
            return self.result.database_load_count

        from src.database.loader import load_final_publications
        from src.database.load_records import filter_records_by_publication_year

        if year_min is None:
            year_min = self.config.collection.start_year
        if year_max is None:
            year_max = self.config.collection.end_year

        records = self.result.deduplicated_records or self.result.cleaned_records
        records = list(
            filter_records_by_publication_year(
                records,
                year_min=year_min,
                year_max=year_max,
            )
        )
        if year_min is not None or year_max is not None:
            logger.info(
                "Database load year filter applied: min=%s max=%s remaining=%s",
                year_min,
                year_max,
                len(records),
            )
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
        self.classify()
        self.run_topic_modeling()
        self.load_database()
        self.export()
        logger.info(
            "Pipeline run complete: %s raw, %s cleaned, %s deduplicated",
            len(self.result.raw_records),
            len(self.result.cleaned_records),
            len(self.result.deduplicated_records),
        )
        return self.result

    def classify(self) -> dict[str, Any]:
        if not self.config.pipeline.classify:
            self.result.classification_result = {}
            logger.info("Classification stage skipped by configuration")
            return self.result.classification_result

        from src.modeling.classification_comparison import (
            ClassificationComparisonConfig,
            compare_classification_models,
        )
        from src.modeling.training import parse_document_frequency

        settings = self.config.machine_learning.get("classification", {})
        if not isinstance(settings, dict):
            settings = {}
        input_path = _stage_input_path(
            settings,
            default=Path("data/processed/common/common_publications_final.csv"),
        )
        output_dir = Path(settings.get("output_dir", "data/models/classification_comparison"))
        text_columns = tuple(settings.get("text_columns", ("title", "abstract", "topics", "keywords", "concepts")))
        model_families = tuple(settings.get("model_families", ("logistic_regression", "linear_svm")))

        result = compare_classification_models(
            ClassificationComparisonConfig(
                input_path=input_path,
                label_column=settings.get("label_column", "primary_field"),
                text_columns=text_columns,
                model_families=model_families,
                output_dir=output_dir,
                test_size=float(settings.get("test_size", 0.15)),
                random_state=int(settings.get("random_state", 42)),
                promote_final=settings.get("promote_final", True),
                max_rows=settings.get("max_rows"),
                min_class_count=settings.get("min_class_count", 20),
                max_features=int(settings.get("max_features", 50_000)),
                min_df=parse_document_frequency(str(settings.get("min_df", 2))),
                max_df=parse_document_frequency(str(settings.get("max_df", 0.95))),
                ngram_max=(
                    int(settings["ngram_max"])
                    if settings.get("ngram_max") is not None
                    else None
                ),
                keep_stop_words=bool(settings.get("keep_stop_words", False)),
                class_weight=settings.get("class_weight", "balanced"),
                max_iter=(
                    int(settings["max_iter"])
                    if settings.get("max_iter") is not None
                    else None
                ),
                c_values=_float_tuple(settings.get("c_values", (0.1, 1.0, 10.0))),
                cv_folds=int(settings.get("cv_folds", 3)),
                scoring=settings.get("scoring", "f1_macro"),
                ranking_metric=settings.get("ranking_metric", "macro_f1"),
            )
        )
        self.result.classification_result = {
            "comparison_output": str(result.comparison_output),
            "manifest_output": str(result.manifest_output),
            "model_count": result.model_count,
            "best_model_family": result.best_model_family,
            "final_model_output": str(result.final_model_output) if result.final_model_output else None,
        }
        logger.info("Classification stage complete: %s", self.result.classification_result)
        return self.result.classification_result

    def run_topic_modeling(self) -> dict[str, Any]:
        if not self.config.pipeline.topic_modeling:
            self.result.topic_modeling_result = {}
            logger.info("Topic-modeling stage skipped by configuration")
            return self.result.topic_modeling_result

        import pandas as pd
        from src.modeling.nmf_topic_modeling import TEXT_COLUMNS, run_final_pipeline

        settings = self.config.machine_learning.get("topic_modeling", {})
        if not isinstance(settings, dict):
            settings = {}
        input_path = _stage_input_path(
            settings,
            default=Path("data/processed/common/common_publications_final.csv"),
        )
        output_dir = Path(settings.get("output_dir", "data/processed/common/nmf"))
        frame = pd.read_csv(input_path, low_memory=False, nrows=settings.get("max_rows"))
        result = run_final_pipeline(
            df=frame,
            k=int(settings.get("k", 20)),
            output_dir=output_dir,
            text_columns=settings.get("text_columns", TEXT_COLUMNS),
            n_words=int(settings.get("n_words", 15)),
            naming_words=int(settings.get("naming_words", 3)),
            year_col=settings.get("year_col"),
            clean=bool(settings.get("clean", True)),
        )
        self.result.topic_modeling_result = {
            "output_dir": str(output_dir),
            "topic_count": len(result["topic_names"]),
            "coherence_cv": result["coherence_cv"],
            "diversity": result["diversity"],
            "redundancy": result["redundancy"],
        }
        logger.info("Topic-modeling stage complete: %s", self.result.topic_modeling_result)
        return self.result.topic_modeling_result

    def _build_input_adapters(self):
        source_configs = self._configured_sources()
        return [
            build_adapter_from_config(replace(self.config, source=source_config))
            for source_config in source_configs
        ]

    def _configured_sources(self) -> list[SourceConfig]:
        configured = []
        for name, source in self.config.sources.items():
            if not isinstance(source, dict) or source.get("enabled", True) is False:
                continue
            source_data = dict(source)
            source_data.setdefault("name", name)
            source_data.setdefault("type", source_data.get("adapter") or name)
            if source_data.get("endpoint") and not source_data.get("base_url"):
                source_data["base_url"] = source_data["endpoint"]
            if source_data.get("adapter") and not source_data.get("type"):
                source_data["type"] = source_data["adapter"]
            if _source_is_collectable(source_data):
                configured.append(SourceConfig(**source_data))
            else:
                logger.info("Skipping descriptive source without collection config: %s", name)

        source_name = self.config.source.name
        source_looks_derived_from_sources = bool(
            self.config.sources and source_name in self.config.sources
        )
        has_explicit_source = bool(
            self.config.source.type or self.config.source.path or self.config.source.base_url
        )

        if configured and (source_looks_derived_from_sources or not has_explicit_source):
            return configured
        if has_explicit_source:
            return [self.config.source]
        return [self.config.source]

    def _adapter_for_record(self, record: dict[str, Any]):
        index = int(record.get("_pipeline_adapter_index", 0)) if isinstance(record, dict) else 0
        return self.adapters[index]


def _unique_errors(errors: list[str]) -> list[str]:
    seen = set()
    unique = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            unique.append(error)
    return unique


def _source_is_collectable(source_data: dict[str, Any]) -> bool:
    source_type = source_data.get("type") or source_data.get("adapter") or source_data.get("format")
    if source_type in {"csv", "json", "jsonl", "ndjson", "excel", "xlsx", "xls", "xml"}:
        return bool(source_data.get("path"))
    if source_type in {"api", "rest_api", "oai_pmh", "openalex", "crossref"}:
        return True
    return bool(source_data.get("path") or source_data.get("base_url") or source_data.get("endpoint"))


def _tag_pipeline_source(
    record: dict[str, Any],
    *,
    adapter_index: int,
    source_index: int,
) -> dict[str, Any]:
    tagged = dict(record)
    tagged["_pipeline_adapter_index"] = adapter_index
    tagged["_pipeline_source_index"] = source_index
    return tagged


def _untag_pipeline_source(record: dict[str, Any]) -> dict[str, Any]:
    clean = dict(record)
    clean.pop("_pipeline_adapter_index", None)
    clean.pop("_pipeline_source_index", None)
    return clean


def _stage_input_path(settings: dict[str, Any], *, default: Path) -> Path:
    return Path(settings.get("input_path") or settings.get("input") or default)


def _float_tuple(value: Any) -> tuple[float, ...]:
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        values = [value]
    return tuple(float(item) for item in values)
