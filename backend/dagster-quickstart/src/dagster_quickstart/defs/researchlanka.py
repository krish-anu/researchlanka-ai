"""Dagster assets and jobs for the ResearchLanka analytics pipeline."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

from dagster import Definitions, asset, define_asset_job


BACKEND_DIR = Path(__file__).resolve().parents[4]
CONFIG_PATH = BACKEND_DIR / "configurations" / "sri_lanka" / "config.json"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from research_analytics.config import FrameworkConfig, load_config  # noqa: E402
from research_analytics.pipeline import PipelineResult, ResearchPipeline  # noqa: E402


@contextmanager
def backend_working_directory() -> Iterator[None]:
    """Run pipeline code from backend so relative config paths resolve."""

    previous_directory = Path.cwd()
    os.chdir(BACKEND_DIR)
    try:
        yield
    finally:
        os.chdir(previous_directory)


def load_pipeline_config(*, load_database: bool) -> FrameworkConfig:
    config = load_config(CONFIG_PATH)
    pipeline_config = replace(config.pipeline, load_database=load_database)
    return replace(config, pipeline=pipeline_config)


def build_pipeline(
    *,
    load_database: bool = False,
    result: PipelineResult | None = None,
) -> ResearchPipeline:
    config = load_pipeline_config(load_database=load_database)
    pipeline = ResearchPipeline(config)
    if result is not None:
        pipeline.result = result
    return pipeline


def result_metadata(result: PipelineResult) -> dict[str, int]:
    return {
        "raw_records": len(result.raw_records),
        "transformed_records": len(result.transformed_records),
        "valid_records": len(result.valid_records),
        "invalid_records": len(result.invalid_records),
        "cleaned_records": len(result.cleaned_records),
        "deduplicated_records": len(result.deduplicated_records),
        "duplicate_candidates": len(result.duplicate_candidates),
        "database_load_count": result.database_load_count,
    }


@asset(group_name="researchlanka")
def researchlanka_source_connection(context) -> dict[str, str]:
    """Check that the configured input source can be reached."""

    with backend_working_directory():
        pipeline = build_pipeline()
        pipeline.connect()
    metadata = {"status": "connected", "config": str(CONFIG_PATH)}
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_source_preview(context) -> list[dict]:
    """Return a small preview from the configured input source."""

    with backend_working_directory():
        pipeline = build_pipeline()
        preview = pipeline.preview(limit=5)
    context.add_output_metadata({"preview_records": len(preview)})
    return preview


@asset(group_name="researchlanka")
def researchlanka_source_validation(context) -> dict:
    """Validate a sample from the configured input source before full import."""

    with backend_working_directory():
        pipeline = build_pipeline()
        report = pipeline.validate_source(sample_size=100).to_dict()
    context.add_output_metadata(
        {
            "records_inspected": report["records_inspected"],
            "valid_records": report["valid_records"],
            "invalid_records": report["invalid_records"],
            "errors": len(report["errors"]),
        }
    )
    return report


@asset(group_name="researchlanka")
def researchlanka_collected_records(
    context,
    researchlanka_source_connection: dict[str, str],
) -> PipelineResult:
    """Collect raw records from the configured source."""

    with backend_working_directory():
        pipeline = build_pipeline()
        pipeline.collect()
    metadata = result_metadata(pipeline.result)
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_transformed_records(
    context,
    researchlanka_collected_records: PipelineResult,
) -> PipelineResult:
    """Transform raw records into the common project schema."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_collected_records)
        pipeline.transform()
    metadata = result_metadata(pipeline.result)
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_validation_report(
    context,
    researchlanka_transformed_records: PipelineResult,
) -> PipelineResult:
    """Validate transformed records and split valid/invalid records."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_transformed_records)
        report = pipeline.validate().to_dict()
    metadata = {
        **result_metadata(pipeline.result),
        "total_records": report["total_records"],
        "invalid_doi_count": report["invalid_doi_count"],
        "invalid_year_count": report["invalid_year_count"],
        "duplicate_doi_count": report["duplicate_doi_count"],
        "duplicate_title_count": report["duplicate_title_count"],
    }
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_cleaned_records(
    context,
    researchlanka_validation_report: PipelineResult,
) -> PipelineResult:
    """Clean and normalize valid records."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_validation_report)
        pipeline.clean()
    metadata = result_metadata(pipeline.result)
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_national_records(
    context,
    researchlanka_cleaned_records: PipelineResult,
) -> PipelineResult:
    """Resolve national institution and collaboration context."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_cleaned_records)
        pipeline.resolve_entities()
    metadata = result_metadata(pipeline.result)
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_deduplicated_records(
    context,
    researchlanka_national_records: PipelineResult,
) -> PipelineResult:
    """Find duplicate candidates and produce deduplicated records."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_national_records)
        pipeline.deduplicate()
    metadata = result_metadata(pipeline.result)
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_analytics_summary(
    context,
    researchlanka_deduplicated_records: PipelineResult,
) -> PipelineResult:
    """Run field-aware analytics on deduplicated records."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_deduplicated_records)
        analytics = pipeline.run_analytics()
    metadata = {
        **result_metadata(pipeline.result),
        "analytics_sections": len(analytics),
    }
    context.add_output_metadata(metadata)
    return pipeline.result


@asset(group_name="researchlanka")
def researchlanka_export_files(
    context,
    researchlanka_analytics_summary: PipelineResult,
) -> dict:
    """Export pipeline outputs without loading PostgreSQL."""

    with backend_working_directory():
        pipeline = build_pipeline(result=researchlanka_analytics_summary)
        pipeline.export()
    metadata = {
        **result_metadata(pipeline.result),
        "output_dir": str(BACKEND_DIR / pipeline.config.export.output_dir),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_database_loaded_records(
    context,
    researchlanka_analytics_summary: PipelineResult,
) -> dict[str, int]:
    """Load deduplicated records into PostgreSQL."""

    with backend_working_directory():
        pipeline = build_pipeline(load_database=True, result=researchlanka_analytics_summary)
        loaded = pipeline.load_database()
    metadata = {**result_metadata(pipeline.result), "loaded_records": loaded}
    context.add_output_metadata(metadata)
    return metadata


researchlanka_export_job = define_asset_job(
    name="researchlanka_export_job",
    selection="*researchlanka_export_files",
)

researchlanka_database_job = define_asset_job(
    name="researchlanka_database_job",
    selection="*researchlanka_database_loaded_records",
)

researchlanka_source_check_job = define_asset_job(
    name="researchlanka_source_check_job",
    selection=[
        "researchlanka_source_connection",
        "researchlanka_source_preview",
        "researchlanka_source_validation",
    ],
)

researchlanka_all_assets_job = define_asset_job(
    name="researchlanka_all_assets_job",
)

defs = Definitions(
    assets=[
        researchlanka_source_connection,
        researchlanka_source_preview,
        researchlanka_source_validation,
        researchlanka_collected_records,
        researchlanka_transformed_records,
        researchlanka_validation_report,
        researchlanka_cleaned_records,
        researchlanka_national_records,
        researchlanka_deduplicated_records,
        researchlanka_analytics_summary,
        researchlanka_export_files,
        researchlanka_database_loaded_records,
    ],
    jobs=[
        researchlanka_export_job,
        researchlanka_database_job,
        researchlanka_source_check_job,
        researchlanka_all_assets_job,
    ],
)
