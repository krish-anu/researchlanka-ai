"""Command-line interface for the reusable framework."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from research_analytics.config import load_config
from research_analytics.pipeline import ResearchPipeline

STAGES = (
    "collect",
    "transform",
    "validate",
    "clean",
    "resolve_entities",
    "deduplicate",
    "analyze",
    "load_database",
    "export",
    "all",
)


def load_database_records(
    config: Any,
    *,
    dataset_path: Path | None = None,
    batch_size: int = 1000,
    limit: int | None = None,
    full_database: bool = False,
) -> int | dict[str, int]:
    """Load either the configured pipeline output or an explicit final dataset file.

    The default pipeline path is intentionally kept for backward compatibility, but
    a concrete dataset file is preferred when the user wants to load the final
    cleaned/deduplicated export (for example the 2016-2026 final CSV).
    """

    if dataset_path is not None:
        from src.database.load_records import (
            load_full_database_dataset,
            load_record_file,
        )

        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset file does not exist: {dataset_path}")

        if full_database:
            return load_full_database_dataset(
                dataset_path,
                batch_size=batch_size,
                limit=limit,
            )

        return load_record_file(
            dataset_path,
            batch_size=batch_size,
            limit=limit,
        )

    pipeline = ResearchPipeline(config)
    pipeline.collect()
    pipeline.transform()
    pipeline.validate()
    pipeline.clean()
    pipeline.resolve_entities()
    pipeline.deduplicate()
    return pipeline.load_database()


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--stage" in argv:
        run_stage_cli(argv)
        return

    parser = argparse.ArgumentParser(prog="research-framework")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in (
        "source-validate",
        "preview",
        "validate",
        "import",
        "clean",
        "deduplicate",
        "analyze",
        "load_database",
        "run-all",
    ):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--config", required=True, type=Path)
        command_parser.add_argument("--sample-size", type=int, default=100)
        command_parser.add_argument(
            "--dataset",
            type=Path,
            default=None,
            help="Optional final CSV/JSON/JSONL dataset to load directly into PostgreSQL.",
        )
        command_parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Batch size for direct dataset loading when --dataset is provided.",
        )
        command_parser.add_argument(
            "--full-database",
            action="store_true",
            help="Populate normalized relational tables as well as final_publications.",
        )
        command_parser.add_argument(
            "--log-level",
            default="INFO",
            choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
            help="Console log level. Logs are written to stderr.",
        )

    embeddings_parser = subparsers.add_parser("generate_embeddings")
    embeddings_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input publication CSV used to generate embeddings.",
    )
    embeddings_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output embeddings parquet path.",
    )
    embeddings_parser.add_argument(
        "--model-output",
        type=Path,
        default=None,
        help="Output embedder model (.joblib) path.",
    )
    embeddings_parser.add_argument(
        "--manifest-output",
        type=Path,
        default=None,
        help="Output embeddings manifest (.json) path.",
    )
    embeddings_parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Output embeddings summary (.txt) path.",
    )
    embeddings_parser.add_argument(
        "--text-columns",
        default="title,abstract,keywords",
        help="Comma-separated text columns to combine.",
    )
    embeddings_parser.add_argument(
        "--metadata-columns",
        default=(
            "record_number,publication_year,title,doi,openalex_id,"
            "source_dataset,source_institution_id,source_record_id"
        ),
        help="Comma-separated metadata columns included in the output parquet.",
    )
    embeddings_parser.add_argument(
        "--embedding-dim",
        type=int,
        default=384,
        help="Target embedding dimension. Default: 384",
    )
    embeddings_parser.add_argument(
        "--max-features",
        type=int,
        default=50_000,
        help="Maximum TF-IDF vocabulary size. Default: 50000",
    )
    embeddings_parser.add_argument(
        "--min-df",
        default="2",
        help="TF-IDF min_df as count or fraction. Default: 2",
    )
    embeddings_parser.add_argument(
        "--max-df",
        default="0.95",
        help="TF-IDF max_df as count or fraction. Default: 0.95",
    )
    embeddings_parser.add_argument(
        "--ngram-max",
        type=int,
        default=2,
        help="Upper bound for word n-grams. Default: 2",
    )
    embeddings_parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional cap on rows read from input CSV.",
    )
    embeddings_parser.add_argument(
        "--keep-stop-words",
        action="store_true",
        help="Keep stop words instead of removing English stop words.",
    )
    embeddings_parser.add_argument(
        "--disable-normalize",
        action="store_true",
        help="Disable L2 normalization on output embeddings.",
    )
    embeddings_parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed used by SVD. Default: 42",
    )
    embeddings_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Console log level. Logs are written to stderr.",
    )

    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    if args.command == "generate_embeddings":
        from src.modeling.embeddings import (
            PublicationEmbeddingConfig,
            generate_publication_text_embeddings,
            result_summary,
        )
        from src.modeling.inference import parse_columns
        from src.modeling.training import parse_document_frequency, parse_text_columns

        result = generate_publication_text_embeddings(
            PublicationEmbeddingConfig(
                input_path=args.input,
                output_path=args.output,
                model_output=args.model_output,
                manifest_output=args.manifest_output,
                summary_output=args.summary_output,
                text_columns=tuple(parse_text_columns(args.text_columns)),
                metadata_columns=tuple(parse_columns(args.metadata_columns)),
                embedding_dim=args.embedding_dim,
                max_rows=args.max_rows,
                max_features=args.max_features,
                min_df=parse_document_frequency(args.min_df),
                max_df=parse_document_frequency(args.max_df),
                ngram_max=args.ngram_max,
                keep_stop_words=args.keep_stop_words,
                normalize_embeddings=not args.disable_normalize,
                random_state=args.random_state,
            )
        )
        print(result_summary(result))
        return

    config = load_config(args.config)
    pipeline = ResearchPipeline(config)

    if args.command == "source-validate":
        report = pipeline.validate_source(sample_size=args.sample_size)
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return

    if args.command == "preview":
        print(
            json.dumps(
                pipeline.preview(limit=args.sample_size), indent=2, ensure_ascii=False
            )
        )
        return

    if args.command == "validate":
        pipeline.collect()
        pipeline.transform()
        report = pipeline.validate()
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return

    if args.command == "import":
        pipeline.collect()
        pipeline.transform()
        print(
            f"Imported {len(pipeline.result.transformed_records)} transformed records."
        )
        return

    if args.command == "clean":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        print(f"Cleaned {len(pipeline.result.cleaned_records)} records.")
        return

    if args.command == "deduplicate":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.deduplicate()
        print(
            f"Found {len(pipeline.result.duplicate_candidates)} duplicate candidates."
        )
        return

    if args.command == "analyze":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.deduplicate()
        summary = pipeline.run_analytics()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if args.command == "load_database":
        loaded = load_database_records(
            config,
            dataset_path=args.dataset,
            batch_size=args.batch_size,
            full_database=args.full_database,
        )
        if args.dataset is not None:
            if isinstance(loaded, dict):
                print(
                    "Loaded "
                    + ", ".join(f"{table}={count}" for table, count in loaded.items())
                    + f" from {args.dataset} into PostgreSQL."
                )
            else:
                print(f"Loaded {loaded} records from {args.dataset} into PostgreSQL.")
        else:
            print(f"Loaded {loaded} records into PostgreSQL.")
        return

    result = pipeline.run_all()
    print(
        "Run complete: "
        f"{len(result.raw_records)} raw, "
        f"{len(result.cleaned_records)} cleaned, "
        f"{len(result.deduplicated_records)} deduplicated."
    )


def run_stage_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="run_pipeline.py")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Console log level. Logs are written to stderr.",
    )
    args = parser.parse_args(argv)

    configure_logging(args.log_level)
    config = load_config(args.config)
    pipeline = ResearchPipeline(config)
    output = run_stage(pipeline, args.stage, sample_size=args.sample_size)

    if isinstance(output, dict):
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return
    print(output)


def run_stage(
    pipeline: ResearchPipeline, stage: str, *, sample_size: int = 100
) -> str | dict[str, Any]:
    """Run one practical pipeline stage, including its prerequisites."""

    if stage == "collect":
        pipeline.collect()
        return f"Collected {len(pipeline.result.raw_records)} raw records."

    if stage == "transform":
        pipeline.collect()
        pipeline.transform()
        return f"Transformed {len(pipeline.result.transformed_records)} records."

    if stage == "validate":
        pipeline.collect()
        pipeline.transform()
        return pipeline.validate().to_dict()

    if stage == "clean":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        return f"Cleaned {len(pipeline.result.cleaned_records)} records."

    if stage == "resolve_entities":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.resolve_entities()
        return f"Resolved national context for {len(pipeline.result.national_records)} records."

    if stage == "deduplicate":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.resolve_entities()
        pipeline.deduplicate()
        return (
            f"Found {len(pipeline.result.duplicate_candidates)} duplicate candidates."
        )

    if stage == "analyze":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.resolve_entities()
        pipeline.deduplicate()
        return pipeline.run_analytics()

    if stage == "export":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.resolve_entities()
        pipeline.deduplicate()
        pipeline.run_analytics()
        pipeline.export()
        return "Export complete."

    if stage == "load_database":
        pipeline.collect()
        pipeline.transform()
        pipeline.validate()
        pipeline.clean()
        pipeline.resolve_entities()
        pipeline.deduplicate()
        loaded = pipeline.load_database()
        return f"Loaded {loaded} records into PostgreSQL."

    result = pipeline.run_all()
    return (
        "Run complete: "
        f"{len(result.raw_records)} raw, "
        f"{len(result.cleaned_records)} cleaned, "
        f"{len(result.deduplicated_records)} deduplicated."
    )


def configure_logging(log_level: str) -> None:
    """Configure live CLI progress logs."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )


if __name__ == "__main__":
    main()
