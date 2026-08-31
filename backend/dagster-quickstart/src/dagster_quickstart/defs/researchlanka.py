"""Dagster assets and jobs for the ResearchLanka analytics pipeline."""

from __future__ import annotations

import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pandas as pd
import requests
from dagster import AssetSelection, asset, define_asset_job


BACKEND_DIR = Path(__file__).resolve().parents[4]
CONFIG_PATH = BACKEND_DIR / "configurations" / "sri_lanka" / "config.json"
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
REPORT_DIR = BACKEND_DIR / "data" / "reports"
CROSSREF_JSONL_OUTPUT = PROCESSED_DIR / "crossref" / "crossref_sri_lanka_works.jsonl"
CROSSREF_CSV_OUTPUT = PROCESSED_DIR / "crossref" / "crossref_sri_lanka_works.csv"
SLJOL_JSONL_OUTPUT = RAW_DIR / "sljol" / "crossref_works.jsonl"
SLJOL_CSV_OUTPUT = PROCESSED_DIR / "sljol.csv"
COMMON_OUTPUT_DIR = PROCESSED_DIR / "common"
COMMON_ALL_RECORDS_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_all_records.csv"
COMMON_DEDUPLICATED_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_deduplicated.csv"
COMMON_MERGE_LOG_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_merge_log.csv"
COMMON_MANUAL_REVIEW_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_manual_review_candidates.csv"
COMMON_DEDUPLICATED_STREAM_SUMMARY_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_deduplicated_stream_summary.csv"
)
COMMON_FINAL_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_final.csv"
COMMON_REFERENCES_OUTPUT = COMMON_OUTPUT_DIR / "publication_references.csv"
COMMON_COUNT_AUDIT_OUTPUT = COMMON_OUTPUT_DIR / "publication_count_audit.csv"
COMMON_FINAL_SUMMARY_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_final_summary.csv"
COMMON_YEAR_FILTERED_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_final_2016_2026.csv"
COMMON_YEAR_FILTERED_SUMMARY_OUTPUT = COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_summary.csv"
COMMON_LANGUAGE_NORMALIZED_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_language_normalized.csv"
)
COMMON_LANGUAGE_NORMALIZED_SUMMARY_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_language_normalized_summary.csv"
)
COMMON_MULTIVALUE_NORMALIZED_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_multivalue_normalized.csv"
)
COMMON_MULTIVALUE_ITEMS_OUTPUT = COMMON_OUTPUT_DIR / "publication_multivalue_items_2016_2026.csv"
COMMON_MULTIVALUE_NORMALIZED_SUMMARY_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_multivalue_normalized_summary.csv"
)
COMMON_ANALYSIS_READY_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_analysis_ready.csv"
)
COMMON_ANALYSIS_READY_ISSUE_DIR = COMMON_OUTPUT_DIR / "preprocessing_issues_2016_2026"
COMMON_ANALYSIS_READY_SUMMARY_OUTPUT = (
    COMMON_OUTPUT_DIR / "common_publications_final_2016_2026_analysis_ready_summary.csv"
)
ALL_SOURCES_SOURCE_NAME = "researchlanka_all_sources_common_dataset"
DEFAULT_COLLECTION_START_YEAR = 2016
DEFAULT_COLLECTION_END_YEAR = 2026
DEFAULT_REPOSITORY_WORKERS = 3

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from research_analytics.config import FrameworkConfig, load_config  # noqa: E402
from research_analytics.pipeline import PipelineResult, ResearchPipeline  # noqa: E402
from src.collectors.crossref_collector import CrossrefCollector, CrossrefPrefixCollector  # noqa: E402
from src.collectors.dspace_rest_collector import DspaceRestCollector  # noqa: E402
from src.collectors.html_meta_collector import HtmlMetaCollector  # noqa: E402
from src.collectors.repository_registry import harvestable_targets, load_registry  # noqa: E402
from src.pipeline.collect_crossref import DEFAULT_AFFILIATION_QUERIES, collect_crossref  # noqa: E402
from src.pipeline.collect_sljol import SLJOL_DOI_PREFIX  # noqa: E402
from src.pipeline.build_analysis_ready_dataset import build_analysis_ready_dataset  # noqa: E402
from src.pipeline.build_final_common_dataset import build_final_common_dataset  # noqa: E402
from src.pipeline.build_language_normalized_dataset import build_language_normalized_dataset  # noqa: E402
from src.pipeline.build_multivalue_normalized_dataset import build_multivalue_normalized_dataset  # noqa: E402
from src.pipeline.build_year_filtered_dataset import build_year_filtered_dataset  # noqa: E402
from src.pipeline.harvest_all import HarvestOutcome, harvest_one  # noqa: E402
from src.pipeline.kaggle_merge_common_dataset import (  # noqa: E402
    COMMON_COLUMNS,
    DEFAULT_FIELD_SOURCE_POLICY,
    MULTI_VALUE_COLUMNS,
    build_manual_review_candidates,
    deduplicate_publications,
    is_blank,
    normalize_doi as normalize_common_doi,
    normalize_source_frame,
    split_multi_value,
    write_run_log,
    write_schema,
    write_summary as write_merge_summary,
)
from src.pipeline.kaggle_collect_openalex_sri_lanka import (  # noqa: E402
    default_progress_output as default_openalex_progress_output,
    collect_quality_report as collect_openalex_quality_report,
    main as collect_openalex_main,
    rebuild_csv_from_jsonl as rebuild_openalex_csv_from_jsonl,
)
from src.quality.audit_openalex_lk_affiliations import run_audit as run_openalex_lk_audit  # noqa: E402
from src.processing.convert_repositories_jsonl_to_csv import (  # noqa: E402
    DEFAULT_OUTPUT_PATH as REPOSITORIES_CSV_OUTPUT,
    convert as convert_repositories_to_csv,
    iter_input_files as iter_repository_input_files,
)
from src.processing.jsonl_to_csv import convert_to_csv  # noqa: E402
from src.processing.map_to_common_schema import discover_raw_institution_ids, map_one  # noqa: E402


OPENALEX_JSONL_OUTPUT = RAW_DIR / "openalex" / "openalex_sri_lanka_works.jsonl"
OPENALEX_CSV_OUTPUT = RAW_DIR / "openalex" / "openalex_sri_lanka_works.csv"
OPENALEX_PARQUET_OUTPUT = RAW_DIR / "openalex" / "openalex_sri_lanka_works.parquet"
OPENALEX_DOI_CONFLICTS_OUTPUT = RAW_DIR / "openalex" / "openalex_sri_lanka_doi_conflicts.csv"
OPENALEX_PAGINATION_OUTPUT = RAW_DIR / "openalex" / "openalex_sri_lanka_pagination_audit.json"
OPENALEX_LK_AUDIT_OUTPUT_DIR = REPORT_DIR / "openalex_lk_affiliation_audit"


@contextmanager
def backend_working_directory() -> Iterator[None]:
    """Run pipeline code from backend so relative config paths resolve."""

    previous_directory = Path.cwd()
    os.chdir(BACKEND_DIR)
    try:
        yield
    finally:
        os.chdir(previous_directory)


def load_pipeline_config(
    *,
    load_database: bool,
    source_path: str | Path | None = None,
    source_name: str | None = None,
) -> FrameworkConfig:
    config = load_config(CONFIG_PATH)
    pipeline_config = replace(config.pipeline, load_database=load_database)
    config = replace(config, pipeline=pipeline_config)
    if source_path is None:
        return config

    resolved_source_name = source_name or config.source.name or config.input.source_name
    source_path_text = str(source_path)
    input_config = replace(
        config.input,
        path=source_path_text,
        format="csv",
        source_name=resolved_source_name,
    )
    source_config = replace(
        config.source,
        name=resolved_source_name,
        type="csv",
        format="csv",
        path=source_path_text,
        delimiter=",",
    )
    return replace(config, input=input_config, source=source_config)


def build_pipeline(
    *,
    load_database: bool = False,
    result: PipelineResult | None = None,
    source_path: str | Path | None = None,
    source_name: str | None = None,
) -> ResearchPipeline:
    config = load_pipeline_config(
        load_database=load_database,
        source_path=source_path,
        source_name=source_name,
    )
    pipeline = ResearchPipeline(config)
    if result is not None:
        pipeline.result = result
    return pipeline


def build_all_sources_pipeline(
    *,
    load_database: bool = False,
    result: PipelineResult | None = None,
) -> ResearchPipeline:
    return build_pipeline(
        load_database=load_database,
        result=result,
        source_path=COMMON_ALL_RECORDS_OUTPUT,
        source_name=ALL_SOURCES_SOURCE_NAME,
    )


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    parsed = int(value)
    return None if parsed == 0 else parsed


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def normalized_id_set(values: tuple[str, ...]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def filter_repository_targets(
    targets: list[Any],
    *,
    include_ids: set[str],
    exclude_ids: set[str],
) -> list[Any]:
    """Filter repository targets by normalized target id sets."""

    return [
        target
        for target in targets
        if (not include_ids or target.id.casefold() in include_ids)
        and target.id.casefold() not in exclude_ids
    ]


def repository_raw_output_path(target: Any) -> Path:
    route = target.extra.get("harvest_route", "oai")
    filename = {
        "rest": "rest_items.jsonl",
        "html": "html_meta.jsonl",
    }.get(route, "oai_dc.jsonl")
    return RAW_DIR / target.id / filename


def skipped_existing_repository_outcome(target: Any) -> HarvestOutcome | None:
    output_path = repository_raw_output_path(target)
    existing_records = count_jsonl(output_path)
    if existing_records <= 0:
        return None
    return HarvestOutcome(
        id=target.id,
        name=target.name,
        record_count=existing_records,
        status="skipped_existing",
        error="Existing raw JSONL reused.",
        output_path=str(output_path),
    )


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    raise_csv_field_limit()
    with path.open(newline="", encoding="utf-8") as file:
        return sum(1 for _ in csv.DictReader(file))


def count_csv_columns(path: Path) -> int:
    if not path.exists():
        return 0
    raise_csv_field_limit()
    with path.open(newline="", encoding="utf-8") as file:
        return len(next(csv.reader(file), []))


def source_enabled(config: FrameworkConfig, source_name: str) -> bool:
    source = config.sources.get(source_name, {})
    return not isinstance(source, dict) or source.get("enabled", True) is not False


def common_source_csv_candidates() -> dict[str, tuple[str, Path]]:
    return {
        "openalex": ("openalex", OPENALEX_CSV_OUTPUT),
        "crossref": ("crossref", CROSSREF_CSV_OUTPUT),
        "sljol": ("national_journal_portal", SLJOL_CSV_OUTPUT),
        "repositories_combined": ("university_repositories", REPOSITORIES_CSV_OUTPUT),
    }


def available_common_source_csvs(
    config: FrameworkConfig,
) -> tuple[dict[str, Path], dict[str, str]]:
    input_paths: dict[str, Path] = {}
    skipped_sources: dict[str, str] = {}

    for source_dataset, (configured_source, path) in common_source_csv_candidates().items():
        if not source_enabled(config, configured_source):
            skipped_sources[source_dataset] = "disabled"
            continue
        if not path.exists():
            skipped_sources[source_dataset] = f"missing CSV: {path}"
            continue
        row_count = count_csv_rows(path)
        if row_count == 0:
            skipped_sources[source_dataset] = f"empty CSV: {path}"
            continue
        input_paths[source_dataset] = path

    return input_paths, skipped_sources


def prepare_existing_common_source_files(context) -> dict[str, Any]:
    """Prepare source CSVs from already-collected files without API harvesting."""

    metadata: dict[str, Any] = {"status": "prepared_existing_files"}

    if not OPENALEX_CSV_OUTPUT.exists() and OPENALEX_JSONL_OUTPUT.exists():
        context.log.info(
            f"OpenAlex CSV is missing; rebuilding from existing JSONL: {OPENALEX_JSONL_OUTPUT}."
        )
        rebuild_openalex_csv_from_jsonl(OPENALEX_JSONL_OUTPUT, OPENALEX_CSV_OUTPUT)
    metadata["openalex_csv_rows"] = count_csv_rows(OPENALEX_CSV_OUTPUT)
    metadata["openalex_csv_output"] = str(OPENALEX_CSV_OUTPUT)

    if not CROSSREF_CSV_OUTPUT.exists() and CROSSREF_JSONL_OUTPUT.exists():
        context.log.info(
            f"Crossref CSV is missing; converting existing JSONL: {CROSSREF_JSONL_OUTPUT}."
        )
        convert_to_csv(CROSSREF_JSONL_OUTPUT, CROSSREF_CSV_OUTPUT)
    metadata["crossref_csv_rows"] = count_csv_rows(CROSSREF_CSV_OUTPUT)
    metadata["crossref_csv_output"] = str(CROSSREF_CSV_OUTPUT)

    if SLJOL_JSONL_OUTPUT.exists():
        context.log.info(f"Converting existing SLJOL JSONL to CSV: {SLJOL_CSV_OUTPUT}.")
        convert_to_csv(SLJOL_JSONL_OUTPUT, SLJOL_CSV_OUTPUT)
    metadata["sljol_csv_rows"] = count_csv_rows(SLJOL_CSV_OUTPUT)
    metadata["sljol_csv_output"] = str(SLJOL_CSV_OUTPUT)

    raw_ids = discover_raw_institution_ids(RAW_DIR)
    mapped_total = 0
    if raw_ids:
        context.log.info(
            f"Mapping {len(raw_ids)} repository raw folders to common-schema JSONL files."
        )
        with backend_working_directory():
            for institution_id in raw_ids:
                mapped_total += map_one(institution_id)

    input_files = list(iter_repository_input_files(None))
    if input_files:
        context.log.info(
            f"Converting {len(input_files)} repository JSONL files to CSV: "
            f"{REPOSITORIES_CSV_OUTPUT}."
        )
        repository_rows = convert_repositories_to_csv(input_files, REPOSITORIES_CSV_OUTPUT)
    else:
        context.log.warning("No repository JSONL files found for CSV conversion.")
        repository_rows = 0

    metadata.update(
        {
            "repository_raw_ids": len(raw_ids),
            "repository_mapped_records": mapped_total,
            "repository_csv_rows": repository_rows,
            "repository_csv_output": str(REPOSITORIES_CSV_OUTPUT),
        }
    )
    return metadata


def run_collect_openalex_cli(args: list[str]) -> None:
    previous_argv = sys.argv
    sys.argv = ["kaggle_collect_openalex_sri_lanka.py", *args]
    try:
        collect_openalex_main()
    finally:
        sys.argv = previous_argv


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


def common_csv_metadata(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "rows": count_csv_rows(path),
        "columns": count_csv_columns(path),
    }


def clean_csv_value(value: Any) -> str:
    return "" if is_blank(value) else str(value)


def common_row_completeness(row: dict[str, Any]) -> int:
    ignored = {"source_dataset", "source_record_id", "source_datestamp", "raw_source_json"}
    return sum(not is_blank(row.get(column)) for column in COMMON_COLUMNS if column not in ignored)


def common_field_source_priority(column: str, source_dataset: str) -> int:
    source_order = DEFAULT_FIELD_SOURCE_POLICY.get(column)
    if source_order is None:
        return 0
    try:
        return source_order.index(source_dataset)
    except ValueError:
        return len(source_order) + 99


def common_merge_key(row: dict[str, Any], row_number: int) -> str:
    doi = normalize_common_doi(row.get("doi"))
    if not is_blank(doi):
        return f"doi:{doi}"

    source_dataset = row.get("source_dataset")
    source_record_id = row.get("source_record_id")
    if not is_blank(source_dataset) and not is_blank(source_record_id):
        return f"source_record:{source_dataset}|{source_record_id}"

    return f"row:{row_number}"


def new_common_merge_group(first_row_number: int) -> dict[str, Any]:
    return {
        "first_row_number": first_row_number,
        "group_size": 0,
        "scalar": {},
        "multi": {column: [] for column in MULTI_VALUE_COLUMNS},
    }


def deduplicate_common_csv_streaming(
    *,
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
    context: Any | None = None,
) -> dict[str, int]:
    """Deduplicate common CSV rows without building one large pandas groupby."""

    raise_csv_field_limit()
    groups: dict[str, dict[str, Any]] = {}
    output_order: list[str] = []
    input_rows = 0

    with input_csv.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for row in reader:
            input_rows += 1
            common_row = {column: row.get(column, "") for column in COMMON_COLUMNS}
            merge_key = common_merge_key(common_row, input_rows)
            group = groups.get(merge_key)
            if group is None:
                group = new_common_merge_group(input_rows)
                groups[merge_key] = group
                output_order.append(merge_key)

            group["group_size"] += 1
            completeness = common_row_completeness(common_row)
            source_dataset = str(common_row.get("source_dataset") or "")

            for column in COMMON_COLUMNS:
                value = common_row.get(column)
                if is_blank(value):
                    continue

                rank = (
                    common_field_source_priority(column, source_dataset),
                    -completeness,
                    input_rows,
                )
                if column in MULTI_VALUE_COLUMNS:
                    for item in split_multi_value(value):
                        if not is_blank(item):
                            group["multi"][column].append((rank, item))
                    continue

                current = group["scalar"].get(column)
                if current is None or rank < current[0]:
                    group["scalar"][column] = (rank, value)

            if context and input_rows % 25_000 == 0:
                context.log.info(f"Common deduplication processed {input_rows:,} rows.")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=COMMON_COLUMNS)
        writer.writeheader()
        for output_row_number, merge_key in enumerate(output_order, start=1):
            group = groups[merge_key]
            output_row: dict[str, str] = {}

            for column in COMMON_COLUMNS:
                if column in MULTI_VALUE_COLUMNS:
                    seen: set[str] = set()
                    values: list[str] = []
                    for _, item in sorted(group["multi"][column], key=lambda pair: pair[0]):
                        if item in seen:
                            continue
                        seen.add(item)
                        values.append(item)
                    output_row[column] = "; ".join(values)
                    continue

                output_row[column] = clean_csv_value(group["scalar"].get(column, (None, ""))[1])

            writer.writerow(output_row)
            if context and output_row_number % 25_000 == 0:
                context.log.info(f"Common deduplication wrote {output_row_number:,} rows.")

    merged_groups = sum(1 for group in groups.values() if group["group_size"] > 1)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv.open("w", newline="", encoding="utf-8") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerow({"metric": "input_csv", "value": str(input_csv)})
        writer.writerow({"metric": "output_csv", "value": str(output_csv)})
        writer.writerow({"metric": "input_rows", "value": input_rows})
        writer.writerow({"metric": "output_rows", "value": len(output_order)})
        writer.writerow({"metric": "merged_groups", "value": merged_groups})
        writer.writerow({"metric": "method", "value": "streaming_doi_source_record_merge"})

    return {
        "input_rows": input_rows,
        "output_rows": len(output_order),
        "merged_groups": merged_groups,
    }


@asset(group_name="researchlanka")
def researchlanka_openalex_api_collection(context) -> dict[str, Any]:
    """Collect Sri Lankan-affiliated works from OpenAlex before processing."""

    config = load_pipeline_config(load_database=False)
    if not source_enabled(config, "openalex") or not env_bool("RESEARCHLANKA_COLLECT_OPENALEX", True):
        metadata = {"status": "skipped", "reason": "OpenAlex source disabled"}
        context.add_output_metadata(metadata)
        return metadata

    max_records = env_int("RESEARCHLANKA_OPENALEX_MAX_RECORDS")
    args = [
        "--jsonl-output",
        str(OPENALEX_JSONL_OUTPUT),
        "--csv-output",
        str(OPENALEX_CSV_OUTPUT),
        "--parquet-output",
        str(OPENALEX_PARQUET_OUTPUT),
        "--doi-conflicts-output",
        str(OPENALEX_DOI_CONFLICTS_OUTPUT),
        "--pagination-output",
        str(OPENALEX_PAGINATION_OUTPUT),
        "--from-year",
        str(config.collection.start_year or DEFAULT_COLLECTION_START_YEAR),
        "--to-year",
        str(config.collection.end_year or DEFAULT_COLLECTION_END_YEAR),
        "--per-page",
        str(config.collection.batch_size),
    ]
    if max_records is not None:
        args.extend(["--max-records", str(max_records)])
    if env_bool("RESEARCHLANKA_OPENALEX_STRICT_LK_ONLY", False):
        args.append("--strict-lk-only")
    if not env_bool("RESEARCHLANKA_OPENALEX_WRITE_PARQUET", False):
        args.append("--no-parquet")
    if os.getenv("OPENALEX_EMAIL"):
        args.extend(["--email", os.environ["OPENALEX_EMAIL"]])
    progress_output = default_openalex_progress_output(OPENALEX_JSONL_OUTPUT)
    resume_requested = env_bool("RESEARCHLANKA_OPENALEX_RESUME", True)
    if resume_requested and OPENALEX_JSONL_OUTPUT.exists() and progress_output.exists():
        args.append("--resume")

    with backend_working_directory():
        run_collect_openalex_cli(args)

    quality = collect_openalex_quality_report(OPENALEX_JSONL_OUTPUT, records_skipped=0)
    metadata = {
        "status": "collected",
        "records": count_jsonl(OPENALEX_JSONL_OUTPUT),
        "csv_rows": count_csv_rows(OPENALEX_CSV_OUTPUT),
        "jsonl_output": str(OPENALEX_JSONL_OUTPUT),
        "csv_output": str(OPENALEX_CSV_OUTPUT),
        "max_records": max_records or 0,
        "missing_doi_count": int(quality["missing_doi_count"]),
        "duplicate_doi_count": int(quality["duplicate_doi_count"]),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_openalex_lk_affiliation_audit(
    context,
    researchlanka_openalex_api_collection: dict[str, Any],
) -> dict[str, Any]:
    """Audit publication-time LK affiliation evidence from stored OpenAlex works."""

    collection_metadata = researchlanka_openalex_api_collection
    if not env_bool("RESEARCHLANKA_RUN_OPENALEX_LK_AUDIT", True):
        metadata = {
            "status": "skipped",
            "reason": "RESEARCHLANKA_RUN_OPENALEX_LK_AUDIT is disabled",
            "collection_status": collection_metadata.get("status", ""),
        }
        context.add_output_metadata(metadata)
        return metadata
    if not OPENALEX_JSONL_OUTPUT.exists():
        raise FileNotFoundError(
            f"Cannot run OpenAlex LK affiliation audit; missing {OPENALEX_JSONL_OUTPUT}"
        )

    with backend_working_directory():
        summary = run_openalex_lk_audit(OPENALEX_JSONL_OUTPUT, OPENALEX_LK_AUDIT_OUTPUT_DIR)

    metadata = {
        "status": "audited",
        "input": str(OPENALEX_JSONL_OUTPUT),
        "output_dir": str(OPENALEX_LK_AUDIT_OUTPUT_DIR),
        "total_works": int(summary["overall"]["unique_openalex_work_ids"]),
        "total_authorships": int(summary["overall"]["total_authorships"]),
        "currently_lk_authorships": int(summary["overall"]["currently_lk_authorships"]),
        "strict_verified_dataset_size": int(
            summary["publication_impact"]["strict_verified_dataset_size"]
        ),
        "percentage_retained": float(summary["publication_impact"]["percentage_retained"]),
        "review_records": int(summary["publication_impact"]["records_sent_to_review"]),
        "issue_authorships": int(
            summary["potential_problems"]["at_least_one_issue_authorships"]["count"]
        ),
        "normalized_lk_only_authorships": int(
            summary["potential_problems"]["normalized_lk_only_authorships"]["count"]
        ),
        "explicit_conflict_authorships": int(
            summary["potential_problems"]["explicit_country_conflict_authorships"]["count"]
        ),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_crossref_api_collection(context) -> dict[str, Any]:
    """Collect Crossref records for Sri Lanka-related affiliation queries."""

    config = load_pipeline_config(load_database=False)
    if not source_enabled(config, "crossref") or not env_bool("RESEARCHLANKA_COLLECT_CROSSREF", True):
        metadata = {"status": "skipped", "reason": "Crossref source disabled"}
        context.add_output_metadata(metadata)
        return metadata

    max_records = env_int("RESEARCHLANKA_CROSSREF_MAX_RECORDS")
    rows = env_int("RESEARCHLANKA_CROSSREF_ROWS", 100) or 100
    queries = env_csv("RESEARCHLANKA_CROSSREF_QUERIES", DEFAULT_AFFILIATION_QUERIES)
    args = SimpleNamespace(
        query=list(queries),
        rows=rows,
        max_records=max_records,
        output=CROSSREF_JSONL_OUTPUT,
        email=os.getenv("CROSSREF_EMAIL"),
        from_year=config.collection.start_year or DEFAULT_COLLECTION_START_YEAR,
        until_year=config.collection.end_year or DEFAULT_COLLECTION_END_YEAR,
    )

    with backend_working_directory():
        collect_crossref(CrossrefCollector(email=args.email), args)
        convert_to_csv(CROSSREF_JSONL_OUTPUT, CROSSREF_CSV_OUTPUT)

    metadata = {
        "status": "collected",
        "records": count_jsonl(CROSSREF_JSONL_OUTPUT),
        "csv_rows": count_csv_rows(CROSSREF_CSV_OUTPUT),
        "jsonl_output": str(CROSSREF_JSONL_OUTPUT),
        "csv_output": str(CROSSREF_CSV_OUTPUT),
        "max_records": max_records or 0,
        "queries": ", ".join(queries),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_sljol_api_collection(context) -> dict[str, Any]:
    """Collect SLJOL metadata via Crossref's public prefix API."""

    config = load_pipeline_config(load_database=False)
    if not source_enabled(config, "national_journal_portal") or not env_bool("RESEARCHLANKA_COLLECT_SLJOL", True):
        metadata = {"status": "skipped", "reason": "SLJOL source disabled"}
        context.add_output_metadata(metadata)
        return metadata

    max_records = env_int("RESEARCHLANKA_SLJOL_MAX_RECORDS")
    rows = env_int("RESEARCHLANKA_SLJOL_ROWS", 500) or 500
    from_year = env_int("RESEARCHLANKA_SLJOL_FROM_YEAR", DEFAULT_COLLECTION_START_YEAR) or DEFAULT_COLLECTION_START_YEAR
    until_year = env_int("RESEARCHLANKA_SLJOL_UNTIL_YEAR", DEFAULT_COLLECTION_END_YEAR) or DEFAULT_COLLECTION_END_YEAR
    use_date_slicing = env_bool("RESEARCHLANKA_SLJOL_DATE_SLICING", True)
    collector = CrossrefPrefixCollector(
        prefix=SLJOL_DOI_PREFIX,
        email=os.getenv("CROSSREF_EMAIL"),
        rows=rows,
    )
    SLJOL_JSONL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with backend_working_directory(), SLJOL_JSONL_OUTPUT.open("w", encoding="utf-8") as output_file:
        works = (
            collector.iter_works(max_records=max_records)
            if not use_date_slicing
            else collector.iter_works_by_publication_date(
                start_year=from_year,
                end_year=until_year,
                max_records=max_records,
            )
        )
        for work in works:
            output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
            total += 1

    convert_to_csv(SLJOL_JSONL_OUTPUT, SLJOL_CSV_OUTPUT)

    metadata = {
        "status": "collected",
        "records": total,
        "csv_rows": count_csv_rows(SLJOL_CSV_OUTPUT),
        "jsonl_output": str(SLJOL_JSONL_OUTPUT),
        "csv_output": str(SLJOL_CSV_OUTPUT),
        "max_records": max_records or 0,
        "from_year": from_year,
        "until_year": until_year or 0,
        "date_slicing": use_date_slicing,
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_repository_collection(context) -> dict[str, Any]:
    """Harvest university repositories via OAI-PMH, REST API, or HTML metadata."""

    config = load_pipeline_config(load_database=False)
    if not source_enabled(config, "university_repositories") or not env_bool("RESEARCHLANKA_COLLECT_REPOSITORIES", True):
        metadata = {"status": "skipped", "reason": "Repository source disabled"}
        context.log.info("Repository collection skipped: university repository source is disabled.")
        context.add_output_metadata(metadata)
        return metadata

    max_records = env_int("RESEARCHLANKA_REPOSITORY_MAX_RECORDS_PER_TARGET")
    phase = os.getenv("RESEARCHLANKA_REPOSITORY_PHASE") or None
    timeout = env_int("RESEARCHLANKA_REPOSITORY_TIMEOUT", 30) or 30
    delay = env_float("RESEARCHLANKA_REPOSITORY_DELAY", 1.0)
    log_every = env_int("RESEARCHLANKA_REPOSITORY_LOG_EVERY", 500) or 500
    include_ids = normalized_id_set(env_csv("RESEARCHLANKA_REPOSITORY_INCLUDE_IDS", ()))
    exclude_ids = normalized_id_set(env_csv("RESEARCHLANKA_REPOSITORY_EXCLUDE_IDS", ()))
    skip_existing = env_bool("RESEARCHLANKA_REPOSITORY_SKIP_EXISTING", False)
    workers = max(
        env_int("RESEARCHLANKA_REPOSITORY_WORKERS", DEFAULT_REPOSITORY_WORKERS) or 1,
        1,
    )
    from_year = config.collection.start_year or DEFAULT_COLLECTION_START_YEAR
    until_year = config.collection.end_year or DEFAULT_COLLECTION_END_YEAR
    from_date = f"{from_year}-01-01"
    until_date = f"{until_year}-12-31"
    all_targets = harvestable_targets(load_registry(), phase=phase)
    targets = filter_repository_targets(
        all_targets,
        include_ids=include_ids,
        exclude_ids=exclude_ids,
    )
    outcomes: list[HarvestOutcome] = []
    harvest_targets = [
        target for target in targets if target.extra.get("harvest_route", "oai") != "crossref"
    ]
    workers = min(workers, max(len(harvest_targets), 1))

    context.log.info(
        "Starting repository collection: "
        f"{len(harvest_targets)} harvest targets, "
        f"phase={phase or 'all'}, "
        f"date_range={from_date}..{until_date}, "
        f"max_records_per_target={max_records or 'unlimited'}, "
        f"timeout={timeout}s, "
        f"skip_existing={skip_existing}, "
        f"workers={workers}, "
        f"log_every={log_every} records."
    )
    if include_ids:
        context.log.info(f"Repository include filter: {', '.join(sorted(include_ids))}.")
    if exclude_ids:
        context.log.info(f"Repository exclude filter: {', '.join(sorted(exclude_ids))}.")
    if not harvest_targets:
        context.log.warning("No repository harvest targets found for the current configuration.")

    with backend_working_directory():
        if workers == 1:
            for index, target in enumerate(harvest_targets, start=1):
                route = target.extra.get("harvest_route", "oai")
                context.log.info(
                    f"Harvesting repository target {index}/{len(harvest_targets)}: "
                    f"{target.id} ({target.name}) via {route}."
                )
                outcome = harvest_repository_target(
                    target,
                    max_records=max_records,
                    timeout=timeout,
                    delay=delay,
                    from_date=from_date,
                    until_date=until_date,
                    skip_existing=skip_existing,
                    context=context,
                    log_every=log_every,
                )
                outcomes.append(outcome)
                log_repository_outcome(context, outcome)
        else:
            context.log.info(
                f"Harvesting {len(harvest_targets)} repository targets with {workers} workers."
            )
            outcomes_by_id: dict[str, HarvestOutcome] = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_by_target = {
                    executor.submit(
                        harvest_repository_target,
                        target,
                        max_records=max_records,
                        timeout=timeout,
                        delay=delay,
                        from_date=from_date,
                        until_date=until_date,
                        skip_existing=skip_existing,
                        context=None,
                        log_every=log_every,
                    ): target
                    for target in harvest_targets
                }
                for future in as_completed(future_by_target):
                    target = future_by_target[future]
                    try:
                        outcome = future.result()
                    except Exception as exc:  # pragma: no cover - defensive guard
                        outcome = HarvestOutcome(
                            id=target.id,
                            name=target.name,
                            record_count=0,
                            status="error",
                            error=str(exc),
                            output_path=str(repository_raw_output_path(target)),
                        )
                    outcomes_by_id[target.id] = outcome
                    log_repository_outcome(context, outcome)

            outcomes = [
                outcomes_by_id[target.id]
                for target in harvest_targets
                if target.id in outcomes_by_id
            ]

        mapped_total = 0
        context.log.info("Mapping harvested repository records to the common schema.")
        for target in harvest_targets:
            if target.extra.get("harvest_route") == "crossref":
                continue
            mapped_records = map_one(target.id)
            mapped_total += mapped_records
            context.log.info(f"Mapped {mapped_records} repository records for {target.id}.")

        input_files = list(iter_repository_input_files(None))
        if input_files:
            context.log.info(
                f"Converting {len(input_files)} repository JSONL files to CSV: "
                f"{REPOSITORIES_CSV_OUTPUT}."
            )
            csv_total = convert_repositories_to_csv(input_files, REPOSITORIES_CSV_OUTPUT)
            context.log.info(f"Repository CSV conversion finished with {csv_total} rows.")
        else:
            context.log.warning("No repository JSONL files found for CSV conversion.")
            csv_total = 0

    report_path = write_repository_collection_report(
        outcomes,
        max_records=max_records,
        from_date=from_date,
        until_date=until_date,
    )
    context.log.info(f"Repository collection summary report written to {report_path}.")
    metadata = {
        "status": "collected",
        "target_count": len(outcomes),
        "ok_targets": sum(1 for outcome in outcomes if outcome.status == "ok"),
        "empty_targets": sum(1 for outcome in outcomes if outcome.status == "empty"),
        "error_targets": sum(1 for outcome in outcomes if outcome.status == "error"),
        "skipped_existing_targets": sum(
            1 for outcome in outcomes if outcome.status == "skipped_existing"
        ),
        "raw_records": sum(outcome.record_count for outcome in outcomes),
        "mapped_records": mapped_total,
        "csv_rows": csv_total,
        "csv_output": str(REPOSITORIES_CSV_OUTPUT),
        "report": str(report_path),
        "max_records_per_target": max_records or 0,
        "from_year": from_year,
        "until_year": until_year,
    }
    context.log.info(
        "Repository collection finished: "
        f"{metadata['ok_targets']} ok, "
        f"{metadata['empty_targets']} empty, "
        f"{metadata['error_targets']} errors, "
        f"{metadata['skipped_existing_targets']} skipped existing, "
        f"{metadata['raw_records']} raw records, "
        f"{metadata['mapped_records']} mapped records, "
        f"{metadata['csv_rows']} CSV rows."
    )
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_all_sources_collected(
    context,
) -> dict[str, Any]:
    """Gate downstream processing using already-collected source files."""

    prepared_metadata = prepare_existing_common_source_files(context)
    metadata = {
        **prepared_metadata,
        "status": "ready_without_collection",
        "openalex_records": count_jsonl(OPENALEX_JSONL_OUTPUT),
        "crossref_records": count_jsonl(CROSSREF_JSONL_OUTPUT),
        "sljol_records": count_jsonl(SLJOL_JSONL_OUTPUT),
        "repository_csv_rows": count_csv_rows(REPOSITORIES_CSV_OUTPUT),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_all_sources_common_dataset(
    context,
    researchlanka_all_sources_collected: dict[str, Any],
) -> dict[str, Any]:
    """Normalize every collected source into one all-records common CSV."""

    _ = researchlanka_all_sources_collected
    config = load_pipeline_config(load_database=False)
    input_paths, skipped_sources = available_common_source_csvs(config)
    unavailable_sources = {
        source: reason for source, reason in skipped_sources.items() if reason != "disabled"
    }
    if unavailable_sources and not env_bool("RESEARCHLANKA_ALLOW_PARTIAL_COMMON_DATASET", False):
        unavailable = "; ".join(
            f"{source}: {reason}" for source, reason in unavailable_sources.items()
        )
        raise FileNotFoundError(
            "Cannot build an all-source dataset because enabled source CSVs are unavailable. "
            f"{unavailable}. Set RESEARCHLANKA_ALLOW_PARTIAL_COMMON_DATASET=1 to continue "
            "with only the available sources."
        )
    if not input_paths:
        skipped = "; ".join(f"{source}: {reason}" for source, reason in skipped_sources.items())
        raise FileNotFoundError(f"No collected source CSVs are available for merging. {skipped}")

    COMMON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for source_dataset, reason in skipped_sources.items():
        context.log.warning(f"Skipping {source_dataset} during common merge: {reason}.")

    source_frames: dict[str, pd.DataFrame] = {}
    for source_dataset, path in input_paths.items():
        context.log.info(f"Normalizing {source_dataset} source CSV: {path}.")
        frame = normalize_source_frame(source_dataset, path, include_raw_json=False)
        source_frames[source_dataset] = frame
        context.log.info(f"Normalized {len(frame)} {source_dataset} rows.")

    all_records = pd.concat(source_frames.values(), ignore_index=True)
    context.log.info(f"Writing all-source records to {COMMON_ALL_RECORDS_OUTPUT}.")
    all_records.to_csv(COMMON_ALL_RECORDS_OUTPUT, index=False)

    metadata = {
        "status": "merged",
        "source_count": len(source_frames),
        "raw_records": len(all_records),
        "path": str(COMMON_ALL_RECORDS_OUTPUT),
        "merge_side_outputs": "skipped",
        **{f"{source}_rows": len(frame) for source, frame in source_frames.items()},
        **{f"{source}_skipped": reason for source, reason in skipped_sources.items()},
    }

    if env_bool("RESEARCHLANKA_COMMON_WRITE_MERGE_OUTPUTS", False):
        context.log.info("Building all-source deduplicated side outputs and merge log.")
        deduplicated, merge_log = deduplicate_publications(all_records, return_log=True)
        deduplicated.to_csv(COMMON_DEDUPLICATED_OUTPUT, index=False)
        merge_log.to_csv(COMMON_MERGE_LOG_OUTPUT, index=False)

        manual_review_candidates = build_manual_review_candidates(all_records)
        manual_review_candidates.to_csv(COMMON_MANUAL_REVIEW_OUTPUT, index=False)
        schema_path = write_schema(COMMON_OUTPUT_DIR)
        summary_path = write_merge_summary(
            COMMON_OUTPUT_DIR,
            input_paths=input_paths,
            source_frames=source_frames,
            all_records=all_records,
            deduplicated=deduplicated,
            manual_review_candidates=manual_review_candidates,
        )
        run_log_path = write_run_log(
            COMMON_OUTPUT_DIR,
            input_paths=input_paths,
            source_frames=source_frames,
            all_records=all_records,
            deduplicated=deduplicated,
            merge_log=merge_log,
            manual_review_candidates=manual_review_candidates,
            args=SimpleNamespace(
                input_dir="Dagster collected source CSVs",
                output_dir=COMMON_OUTPUT_DIR,
                sample_rows=None,
                include_raw_json=False,
                field_source_policy=None,
            ),
            output_paths={
                "all_records": COMMON_ALL_RECORDS_OUTPUT,
                "deduplicated": COMMON_DEDUPLICATED_OUTPUT,
                "merge_log": COMMON_MERGE_LOG_OUTPUT,
                "manual_review_candidates": COMMON_MANUAL_REVIEW_OUTPUT,
                "schema": schema_path,
                "summary": summary_path,
            },
        )
        metadata.update(
            {
                "merge_side_outputs": "written",
                "deduplicated_records": len(deduplicated),
                "manual_review_candidate_groups": len(manual_review_candidates),
                "deduplicated_path": str(COMMON_DEDUPLICATED_OUTPUT),
                "merge_log_path": str(COMMON_MERGE_LOG_OUTPUT),
                "manual_review_path": str(COMMON_MANUAL_REVIEW_OUTPUT),
                "summary_path": str(summary_path),
                "run_log_path": str(run_log_path),
            }
        )

    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_common_deduplicated_dataset(
    context,
    researchlanka_all_sources_common_dataset: dict[str, Any],
) -> dict[str, Any]:
    """Deduplicate and merge the 76-column common all-records dataset."""

    _ = researchlanka_all_sources_common_dataset
    context.log.info(f"Deduplicating common all-records CSV: {COMMON_ALL_RECORDS_OUTPUT}.")
    metadata = deduplicate_common_csv_streaming(
        input_csv=COMMON_ALL_RECORDS_OUTPUT,
        output_csv=COMMON_DEDUPLICATED_OUTPUT,
        summary_csv=COMMON_DEDUPLICATED_STREAM_SUMMARY_OUTPUT,
        context=context,
    )
    output_metadata = {
        "status": "deduplicated",
        "path": str(COMMON_DEDUPLICATED_OUTPUT),
        "summary_path": str(COMMON_DEDUPLICATED_STREAM_SUMMARY_OUTPUT),
        **metadata,
        **{
            f"deduplicated_{key}": value
            for key, value in common_csv_metadata(COMMON_DEDUPLICATED_OUTPUT).items()
        },
    }
    context.add_output_metadata(output_metadata)
    return output_metadata


@asset(group_name="researchlanka")
def researchlanka_common_final_dataset(
    context,
    researchlanka_common_deduplicated_dataset: dict[str, Any],
) -> dict[str, Any]:
    """Apply the documented 56-column final dataset decisions."""

    _ = researchlanka_common_deduplicated_dataset
    context.log.info("Building the 56-column final common publication dataset.")
    final, reference_rows, count_audit_rows = build_final_common_dataset(
        COMMON_DEDUPLICATED_OUTPUT,
        COMMON_FINAL_OUTPUT,
        COMMON_REFERENCES_OUTPUT,
        COMMON_COUNT_AUDIT_OUTPUT,
        COMMON_FINAL_SUMMARY_OUTPUT,
    )
    metadata = {
        "status": "finalized",
        "path": str(COMMON_FINAL_OUTPUT),
        "rows": len(final),
        "columns": len(final.columns),
        "references_path": str(COMMON_REFERENCES_OUTPUT),
        "reference_rows": reference_rows,
        "count_audit_path": str(COMMON_COUNT_AUDIT_OUTPUT),
        "count_audit_rows": count_audit_rows,
        "summary_path": str(COMMON_FINAL_SUMMARY_OUTPUT),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_common_year_filtered_dataset(
    context,
    researchlanka_common_final_dataset: dict[str, Any],
) -> dict[str, Any]:
    """Filter the final dataset to the configured 2016-2026 publication window."""

    _ = researchlanka_common_final_dataset
    filtered = build_year_filtered_dataset(
        COMMON_FINAL_OUTPUT,
        COMMON_YEAR_FILTERED_OUTPUT,
        COMMON_YEAR_FILTERED_SUMMARY_OUTPUT,
        start_year=DEFAULT_COLLECTION_START_YEAR,
        end_year=DEFAULT_COLLECTION_END_YEAR,
    )
    metadata = {
        "status": "year_filtered",
        "path": str(COMMON_YEAR_FILTERED_OUTPUT),
        "rows": len(filtered),
        "columns": len(filtered.columns),
        "start_year": DEFAULT_COLLECTION_START_YEAR,
        "end_year": DEFAULT_COLLECTION_END_YEAR,
        "summary_path": str(COMMON_YEAR_FILTERED_SUMMARY_OUTPUT),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_common_language_normalized_dataset(
    context,
    researchlanka_common_year_filtered_dataset: dict[str, Any],
) -> dict[str, Any]:
    """Normalize language codes after the year-filtered final dataset is built."""

    _ = researchlanka_common_year_filtered_dataset
    normalized = build_language_normalized_dataset(
        COMMON_YEAR_FILTERED_OUTPUT,
        COMMON_LANGUAGE_NORMALIZED_OUTPUT,
        COMMON_LANGUAGE_NORMALIZED_SUMMARY_OUTPUT,
    )
    mapping_path = COMMON_LANGUAGE_NORMALIZED_SUMMARY_OUTPUT.with_name(
        COMMON_LANGUAGE_NORMALIZED_SUMMARY_OUTPUT.stem.replace("_summary", "_mapping") + ".csv"
    )
    metadata = {
        "status": "language_normalized",
        "path": str(COMMON_LANGUAGE_NORMALIZED_OUTPUT),
        "rows": len(normalized),
        "columns": len(normalized.columns),
        "summary_path": str(COMMON_LANGUAGE_NORMALIZED_SUMMARY_OUTPUT),
        "mapping_path": str(mapping_path),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_common_multivalue_normalized_dataset(
    context,
    researchlanka_common_language_normalized_dataset: dict[str, Any],
) -> dict[str, Any]:
    """Normalize semicolon-separated fields and write exploded item sidecars."""

    _ = researchlanka_common_language_normalized_dataset
    normalized, item_rows = build_multivalue_normalized_dataset(
        COMMON_LANGUAGE_NORMALIZED_OUTPUT,
        COMMON_MULTIVALUE_NORMALIZED_OUTPUT,
        COMMON_MULTIVALUE_ITEMS_OUTPUT,
        COMMON_MULTIVALUE_NORMALIZED_SUMMARY_OUTPUT,
    )
    details_path = COMMON_MULTIVALUE_NORMALIZED_SUMMARY_OUTPUT.with_name(
        COMMON_MULTIVALUE_NORMALIZED_SUMMARY_OUTPUT.stem.replace("_summary", "_details")
        + ".csv"
    )
    metadata = {
        "status": "multivalue_normalized",
        "path": str(COMMON_MULTIVALUE_NORMALIZED_OUTPUT),
        "rows": len(normalized),
        "columns": len(normalized.columns),
        "items_path": str(COMMON_MULTIVALUE_ITEMS_OUTPUT),
        "item_rows": item_rows,
        "summary_path": str(COMMON_MULTIVALUE_NORMALIZED_SUMMARY_OUTPUT),
        "details_path": str(details_path),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_common_analysis_ready_dataset(
    context,
    researchlanka_common_multivalue_normalized_dataset: dict[str, Any],
) -> dict[str, Any]:
    """Build the analysis-ready dataset and preprocessing issue files."""

    _ = researchlanka_common_multivalue_normalized_dataset
    cleaned, issue_rows = build_analysis_ready_dataset(
        COMMON_MULTIVALUE_NORMALIZED_OUTPUT,
        COMMON_ANALYSIS_READY_OUTPUT,
        COMMON_ANALYSIS_READY_ISSUE_DIR,
        COMMON_ANALYSIS_READY_SUMMARY_OUTPUT,
    )
    metadata = {
        "status": "analysis_ready",
        "path": str(COMMON_ANALYSIS_READY_OUTPUT),
        "rows": len(cleaned),
        "columns": len(cleaned.columns),
        "issue_dir": str(COMMON_ANALYSIS_READY_ISSUE_DIR),
        "issue_rows": issue_rows,
        "summary_path": str(COMMON_ANALYSIS_READY_SUMMARY_OUTPUT),
    }
    context.add_output_metadata(metadata)
    return metadata


def harvest_repository_rest(
    target,
    *,
    max_records: int | None,
    timeout: int,
    context: Any | None = None,
    log_every: int = 500,
) -> HarvestOutcome:
    output_path = RAW_DIR / target.id / "rest_items.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not target.rest_api_endpoint:
        return HarvestOutcome(
            id=target.id,
            name=target.name,
            status="error",
            error="No REST API endpoint configured.",
            output_path=str(output_path),
        )

    verify_ssl = not target.extra.get("ssl_verify_failed", False)
    collector = DspaceRestCollector(
        api_base_url=target.rest_api_endpoint,
        timeout=timeout,
        page_size=100,
        verify_ssl=verify_ssl,
    )
    total = 0
    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            for item in collector.iter_items(max_records=max_records):
                output_file.write(json.dumps(item, ensure_ascii=False) + "\n")
                total += 1
                if context and log_every > 0 and total % log_every == 0:
                    context.log.info(
                        f"Repository target {target.id} collected {total} REST items so far."
                    )
    except requests.RequestException as exc:
        return HarvestOutcome(
            id=target.id,
            name=target.name,
            record_count=total,
            status="error",
            error=str(exc),
            output_path=str(output_path),
        )

    return HarvestOutcome(
        id=target.id,
        name=target.name,
        record_count=total,
        status="ok" if total else "empty",
        output_path=str(output_path),
    )


def harvest_repository_html(
    target,
    *,
    max_records: int | None,
    timeout: int,
    delay: float,
    context: Any | None = None,
    log_every: int = 500,
) -> HarvestOutcome:
    output_path = RAW_DIR / target.id / "html_meta.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_url = target.extra.get("browse_url") or target.repository_url
    if not base_url:
        return HarvestOutcome(
            id=target.id,
            name=target.name,
            status="error",
            error="No browse or repository URL configured.",
            output_path=str(output_path),
        )

    collector = HtmlMetaCollector(base_url=base_url, timeout=timeout, delay=delay)
    total = 0
    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            for item in collector.iter_items(max_records=max_records):
                output_file.write(json.dumps(item, ensure_ascii=False) + "\n")
                total += 1
                if context and log_every > 0 and total % log_every == 0:
                    context.log.info(
                        f"Repository target {target.id} collected {total} HTML items so far."
                    )
    except requests.RequestException as exc:
        return HarvestOutcome(
            id=target.id,
            name=target.name,
            record_count=total,
            status="error",
            error=str(exc),
            output_path=str(output_path),
        )

    return HarvestOutcome(
        id=target.id,
        name=target.name,
        record_count=total,
        status="ok" if total else "empty",
        output_path=str(output_path),
    )


def harvest_repository_target(
    target,
    *,
    max_records: int | None,
    timeout: int,
    delay: float,
    from_date: str,
    until_date: str,
    skip_existing: bool,
    context: Any | None = None,
    log_every: int = 500,
) -> HarvestOutcome:
    if skip_existing:
        existing_outcome = skipped_existing_repository_outcome(target)
        if existing_outcome is not None:
            return existing_outcome

    route = target.extra.get("harvest_route", "oai")
    if route == "rest":
        return harvest_repository_rest(
            target,
            max_records=max_records,
            timeout=timeout,
            context=context,
            log_every=log_every,
        )
    if route == "html":
        return harvest_repository_html(
            target,
            max_records=max_records,
            timeout=timeout,
            delay=delay,
            context=context,
            log_every=log_every,
        )

    return harvest_one(
        target,
        max_records=max_records,
        timeout=timeout,
        from_date=from_date,
        until_date=until_date,
        progress_callback=(
            (
                lambda total: context.log.info(
                    f"Repository target {target.id} collected {total} OAI records so far."
                )
            )
            if context
            else None
        ),
        progress_interval=log_every,
    )


def log_repository_outcome(context: Any, outcome: HarvestOutcome) -> None:
    outcome_message = (
        f"Repository target {outcome.id} finished with status={outcome.status}, "
        f"records={outcome.record_count}, output={outcome.output_path or 'none'}."
    )
    if outcome.status == "error":
        context.log.error(f"{outcome_message} Error: {outcome.error or 'unknown error'}")
    elif outcome.status == "empty":
        context.log.warning(outcome_message + (f" Note: {outcome.error}" if outcome.error else ""))
    elif outcome.status == "skipped_existing":
        context.log.info(outcome_message + " Existing raw file was reused.")
    else:
        context.log.info(outcome_message)


def write_repository_collection_report(
    outcomes: list[HarvestOutcome],
    *,
    max_records: int | None,
    from_date: str,
    until_date: str,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"dagster_collection_summary_{timestamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_records_per_target": max_records,
        "from_date": from_date,
        "until_date": until_date,
        "target_count": len(outcomes),
        "total_records": sum(outcome.record_count for outcome in outcomes),
        "results": [asdict(outcome) for outcome in outcomes],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return report_path


@asset(group_name="researchlanka")
def researchlanka_source_connection(
    context,
    researchlanka_all_sources_common_dataset: dict[str, Any],
) -> dict[str, str]:
    """Check that the configured input source can be reached."""

    _ = researchlanka_all_sources_common_dataset
    with backend_working_directory():
        pipeline = build_all_sources_pipeline()
        pipeline.connect()
    metadata = {
        "status": "connected",
        "config": str(CONFIG_PATH),
        "source_path": str(COMMON_ALL_RECORDS_OUTPUT),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka")
def researchlanka_source_preview(
    context,
    researchlanka_source_connection: dict[str, str],
) -> list[dict]:
    """Return a small preview from the configured input source."""

    _ = researchlanka_source_connection
    with backend_working_directory():
        pipeline = build_all_sources_pipeline()
        preview = pipeline.preview(limit=5)
    context.add_output_metadata({"preview_records": len(preview)})
    return preview


@asset(group_name="researchlanka")
def researchlanka_source_validation(
    context,
    researchlanka_source_preview: list[dict],
) -> dict:
    """Validate a sample from the configured input source before full import."""

    _ = researchlanka_source_preview
    with backend_working_directory():
        pipeline = build_all_sources_pipeline()
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
    researchlanka_source_validation: dict,
) -> PipelineResult:
    """Collect raw records from the configured source."""

    _ = researchlanka_source_validation
    with backend_working_directory():
        pipeline = build_all_sources_pipeline()
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
        pipeline = build_all_sources_pipeline(result=researchlanka_collected_records)
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
        pipeline = build_all_sources_pipeline(result=researchlanka_transformed_records)
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
        pipeline = build_all_sources_pipeline(result=researchlanka_validation_report)
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
        pipeline = build_all_sources_pipeline(result=researchlanka_cleaned_records)
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
        pipeline = build_all_sources_pipeline(result=researchlanka_national_records)
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
        pipeline = build_all_sources_pipeline(result=researchlanka_deduplicated_records)
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
        pipeline = build_all_sources_pipeline(result=researchlanka_analytics_summary)
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
        pipeline = build_all_sources_pipeline(
            load_database=True,
            result=researchlanka_analytics_summary,
        )
        loaded = pipeline.load_database()
    metadata = {**result_metadata(pipeline.result), "loaded_records": loaded}
    context.add_output_metadata(metadata)
    return metadata


researchlanka_export_job = define_asset_job(
    name="researchlanka_export_job",
    selection=AssetSelection.keys("researchlanka_export_files").upstream(),
)

researchlanka_database_job = define_asset_job(
    name="researchlanka_database_job",
    selection=AssetSelection.keys("researchlanka_database_loaded_records").upstream(),
)

researchlanka_source_check_job = define_asset_job(
    name="researchlanka_source_check_job",
    selection=AssetSelection.keys("researchlanka_source_validation").upstream(),
)

researchlanka_openalex_lk_audit_job = define_asset_job(
    name="researchlanka_openalex_lk_audit_job",
    selection=AssetSelection.keys("researchlanka_openalex_lk_affiliation_audit").upstream(),
)

researchlanka_common_preprocessing_job = define_asset_job(
    name="researchlanka_common_preprocessing_job",
    selection=AssetSelection.keys("researchlanka_common_analysis_ready_dataset").upstream(),
)

researchlanka_no_collection_preprocessing_job = define_asset_job(
    name="researchlanka_no_collection_preprocessing_job",
    selection=AssetSelection.keys("researchlanka_common_analysis_ready_dataset").upstream(),
)

researchlanka_all_assets_job = define_asset_job(
    name="researchlanka_all_assets_job",
    selection=AssetSelection.groups("researchlanka"),
)
