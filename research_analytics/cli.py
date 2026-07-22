"""Command-line interface for the reusable framework."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_analytics.config import load_config
from research_analytics.pipeline import ResearchPipeline


def main() -> None:
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
        "run-all",
    ):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--config", required=True, type=Path)
        command_parser.add_argument("--sample-size", type=int, default=100)

    args = parser.parse_args()
    config = load_config(args.config)
    pipeline = ResearchPipeline(config)

    if args.command == "source-validate":
        report = pipeline.validate_source(sample_size=args.sample_size)
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return

    if args.command == "preview":
        print(json.dumps(pipeline.preview(limit=args.sample_size), indent=2, ensure_ascii=False))
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
        print(f"Imported {len(pipeline.result.transformed_records)} transformed records.")
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
        print(f"Found {len(pipeline.result.duplicate_candidates)} duplicate candidates.")
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

    result = pipeline.run_all()
    print(
        "Run complete: "
        f"{len(result.raw_records)} raw, "
        f"{len(result.cleaned_records)} cleaned, "
        f"{len(result.deduplicated_records)} deduplicated."
    )


if __name__ == "__main__":
    main()
