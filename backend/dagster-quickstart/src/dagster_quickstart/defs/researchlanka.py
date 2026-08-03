"""Dagster assets and jobs for the ResearchLanka analytics pipeline."""

from __future__ import annotations

import csv
import json
import os
import sys
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
ALL_SOURCES_SOURCE_NAME = "researchlanka_all_sources_common_dataset"
DEFAULT_COLLECTION_START_YEAR = 2016
DEFAULT_COLLECTION_END_YEAR = 2026

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
from src.pipeline.harvest_all import HarvestOutcome, harvest_one  # noqa: E402
from src.pipeline.kaggle_merge_common_dataset import (  # noqa: E402
    build_manual_review_candidates,
    deduplicate_publications,
    normalize_source_frame,
    write_run_log,
    write_schema,
    write_summary,
)
from src.pipeline.kaggle_collect_openalex_sri_lanka import (  # noqa: E402
    DEFAULT_CSV_OUTPUT as OPENALEX_CSV_OUTPUT,
    DEFAULT_DOI_CONFLICTS_OUTPUT as OPENALEX_DOI_CONFLICTS_OUTPUT,
    DEFAULT_JSONL_OUTPUT as OPENALEX_JSONL_OUTPUT,
    DEFAULT_PAGINATION_OUTPUT as OPENALEX_PAGINATION_OUTPUT,
    DEFAULT_PARQUET_OUTPUT as OPENALEX_PARQUET_OUTPUT,
    default_progress_output as default_openalex_progress_output,
    collect_quality_report as collect_openalex_quality_report,
    main as collect_openalex_main,
)
from src.processing.convert_repositories_jsonl_to_csv import (  # noqa: E402
    DEFAULT_OUTPUT_PATH as REPOSITORIES_CSV_OUTPUT,
    convert as convert_repositories_to_csv,
    iter_input_files as iter_repository_input_files,
)
from src.processing.jsonl_to_csv import convert_to_csv  # noqa: E402
from src.processing.map_to_common_schema import map_one  # noqa: E402


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
    from_year = config.collection.start_year or DEFAULT_COLLECTION_START_YEAR
    until_year = config.collection.end_year or DEFAULT_COLLECTION_END_YEAR
    from_date = f"{from_year}-01-01"
    until_date = f"{until_year}-12-31"
    targets = harvestable_targets(load_registry(), phase=phase)
    outcomes: list[HarvestOutcome] = []
    harvest_targets = [
        target for target in targets if target.extra.get("harvest_route", "oai") != "crossref"
    ]

    context.log.info(
        "Starting repository collection: "
        f"{len(harvest_targets)} harvest targets, "
        f"phase={phase or 'all'}, "
        f"date_range={from_date}..{until_date}, "
        f"max_records_per_target={max_records or 'unlimited'}, "
        f"timeout={timeout}s, "
        f"log_every={log_every} records."
    )
    if not harvest_targets:
        context.log.warning("No repository harvest targets found for the current configuration.")

    with backend_working_directory():
        for index, target in enumerate(targets, start=1):
            route = target.extra.get("harvest_route", "oai")
            if route == "crossref":
                context.log.info(
                    f"Skipping repository target {target.id} ({target.name}): "
                    "route is handled by Crossref collection."
                )
                continue
            context.log.info(
                f"Harvesting repository target {index}/{len(targets)}: "
                f"{target.id} ({target.name}) via {route}."
            )
            if route == "rest":
                outcome = harvest_repository_rest(
                    target,
                    max_records=max_records,
                    timeout=timeout,
                    context=context,
                    log_every=log_every,
                )
            elif route == "html":
                outcome = harvest_repository_html(
                    target,
                    max_records=max_records,
                    timeout=timeout,
                    delay=delay,
                    context=context,
                    log_every=log_every,
                )
            else:
                outcome = harvest_one(
                    target,
                    max_records=max_records,
                    timeout=timeout,
                    from_date=from_date,
                    until_date=until_date,
                    progress_callback=lambda total, current_target=target: context.log.info(
                        f"Repository target {current_target.id} collected {total} OAI records so far."
                    ),
                    progress_interval=log_every,
                )
            outcomes.append(outcome)

            outcome_message = (
                f"Repository target {outcome.id} finished with status={outcome.status}, "
                f"records={outcome.record_count}, output={outcome.output_path or 'none'}."
            )
            if outcome.status == "error":
                context.log.error(
                    f"{outcome_message} Error: {outcome.error or 'unknown error'}"
                )
            elif outcome.status == "empty":
                context.log.warning(
                    f"{outcome_message}"
                    + (f" Note: {outcome.error}" if outcome.error else "")
                )
            else:
                context.log.info(outcome_message)

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
        f"{metadata['raw_records']} raw records, "
        f"{metadata['mapped_records']} mapped records, "
        f"{metadata['csv_rows']} CSV rows."
    )
    context.add_output_metadata(metadata)
    return metadata


@asset(
    group_name="researchlanka",
    deps=[
        researchlanka_openalex_api_collection,
        researchlanka_crossref_api_collection,
        researchlanka_sljol_api_collection,
        researchlanka_repository_collection,
    ],
)
def researchlanka_all_sources_collected(context) -> dict[str, Any]:
    """Gate downstream processing until every enabled source has been collected."""

    metadata = {
        "status": "ready",
        "openalex_records": count_jsonl(OPENALEX_JSONL_OUTPUT),
        "crossref_records": count_jsonl(CROSSREF_JSONL_OUTPUT),
        "sljol_records": count_jsonl(SLJOL_JSONL_OUTPUT),
        "repository_csv_rows": count_csv_rows(REPOSITORIES_CSV_OUTPUT),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(group_name="researchlanka", deps=[researchlanka_all_sources_collected])
def researchlanka_all_sources_common_dataset(context) -> dict[str, Any]:
    """Normalize every collected source into one all-records common CSV."""

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
        summary_path = write_summary(
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


@asset(group_name="researchlanka", deps=[researchlanka_all_sources_common_dataset])
def researchlanka_source_connection(context) -> dict[str, str]:
    """Check that the configured input source can be reached."""

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


@asset(group_name="researchlanka", deps=[researchlanka_source_connection])
def researchlanka_source_preview(context) -> list[dict]:
    """Return a small preview from the configured input source."""

    with backend_working_directory():
        pipeline = build_all_sources_pipeline()
        preview = pipeline.preview(limit=5)
    context.add_output_metadata({"preview_records": len(preview)})
    return preview


@asset(group_name="researchlanka", deps=[researchlanka_source_preview])
def researchlanka_source_validation(context) -> dict:
    """Validate a sample from the configured input source before full import."""

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


@asset(group_name="researchlanka", deps=[researchlanka_source_validation])
def researchlanka_collected_records(context) -> PipelineResult:
    """Collect raw records from the configured source."""

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
    selection="*researchlanka_export_files",
)

researchlanka_database_job = define_asset_job(
    name="researchlanka_database_job",
    selection="*researchlanka_database_loaded_records",
)

researchlanka_source_check_job = define_asset_job(
    name="researchlanka_source_check_job",
    selection="*researchlanka_source_validation",
)

researchlanka_all_assets_job = define_asset_job(
    name="researchlanka_all_assets_job",
    selection=AssetSelection.groups("researchlanka"),
)
