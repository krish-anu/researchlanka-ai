"""Build and optionally load the AI-only publication dataset."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.database.load_records import load_record_file
from src.pipeline.incremental_update import (
    AI_COLUMNS,
    DEFAULT_DB_LABELS,
    DEFAULT_TEXT_COLUMNS,
    apply_ai_classification,
    configured_model_path,
    filter_rows_for_database,
    parse_label_set,
)
from src.modeling.training import parse_text_columns


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_2016_2026.csv"
DEFAULT_CLASSIFIED_OUTPUT = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_2016_2026_ai_classified.csv"
DEFAULT_AI_OUTPUT = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_2016_2026_ai_only.csv"

logger = logging.getLogger(__name__)


def read_csv_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = [*fieldnames, *[column for column in AI_COLUMNS if column not in fieldnames]]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_ai_publication_dataset(
    *,
    input_csv: Path,
    classified_output: Path,
    ai_output: Path,
    model_path: Path,
    text_columns: tuple[str, ...],
    confidence_review_threshold: float | None,
    db_labels: tuple[str, ...],
    load_db: bool,
    batch_size: int,
) -> dict[str, Any]:
    rows, fieldnames = read_csv_rows(input_csv)
    classified_rows = apply_ai_classification(
        rows,
        model_path=model_path,
        text_columns=text_columns,
        confidence_review_threshold=confidence_review_threshold,
    )
    selected_rows = filter_rows_for_database(classified_rows, labels=db_labels)

    write_csv(classified_output, classified_rows, fieldnames)
    write_csv(ai_output, selected_rows, fieldnames)

    loaded = 0
    if load_db:
        loaded = load_record_file(ai_output, batch_size=batch_size, reset=True)

    return {
        "input_rows": len(rows),
        "classified_output": str(classified_output),
        "ai_output": str(ai_output),
        "selected_rows": len(selected_rows),
        "db_labels": list(db_labels),
        "loaded_rows": loaded,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify the historical dataset and keep AI publications only.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--classified-output", type=Path, default=DEFAULT_CLASSIFIED_OUTPUT)
    parser.add_argument("--ai-output", type=Path, default=DEFAULT_AI_OUTPUT)
    parser.add_argument("--model", type=Path, default=configured_model_path())
    parser.add_argument("--text-columns", type=parse_text_columns, default=list(DEFAULT_TEXT_COLUMNS))
    parser.add_argument("--confidence-review-threshold", type=float, default=None)
    parser.add_argument("--db-labels", type=parse_label_set, default=DEFAULT_DB_LABELS)
    parser.add_argument("--load-db", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    result = build_ai_publication_dataset(
        input_csv=args.input,
        classified_output=args.classified_output,
        ai_output=args.ai_output,
        model_path=args.model,
        text_columns=tuple(args.text_columns),
        confidence_review_threshold=args.confidence_review_threshold,
        db_labels=tuple(args.db_labels),
        load_db=args.load_db,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
