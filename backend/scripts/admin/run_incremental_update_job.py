#!/usr/bin/env python3
"""Run the incremental update as a UI-triggered background job."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.training import parse_text_columns  # noqa: E402
from src.pipeline.incremental_update import (  # noqa: E402
    DEFAULT_DB_LABELS,
    DEFAULT_INITIAL_FROM_DATE,
    DEFAULT_STATE_BACKEND,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_STATE_PATH,
    DEFAULT_TEXT_COLUMNS,
    configured_model_path,
    parse_iso_date,
    parse_label_set,
    run_incremental_update,
)
from src.database.pipeline_state import DEFAULT_INCREMENTAL_STATE_KEY  # noqa: E402


DEFAULT_STATUS_PATH = PROJECT_ROOT / "outputs" / "incremental" / "ui_status.json"


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the incremental AI-only update job.")
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--log-path", type=Path, default=None)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument(
        "--state-backend",
        choices=("database", "json"),
        default=os.getenv(
            "RESEARCHLANKA_INCREMENTAL_STATE_BACKEND",
            DEFAULT_STATE_BACKEND,
        ),
    )
    parser.add_argument(
        "--state-key",
        default=os.getenv(
            "RESEARCHLANKA_INCREMENTAL_STATE_KEY",
            DEFAULT_INCREMENTAL_STATE_KEY,
        ),
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--from-date", type=parse_iso_date, default=None)
    parser.add_argument("--initial-from-date", type=parse_iso_date, default=DEFAULT_INITIAL_FROM_DATE)
    parser.add_argument(
        "--to-date",
        "--end-date",
        dest="to_date",
        type=parse_iso_date,
        default=date.today(),
    )
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--email", default=os.getenv("OPENALEX_EMAIL"))
    parser.add_argument("--api-key", default=os.getenv("OPENALEX_API_KEY"))
    parser.add_argument("--strict-lk-only", action="store_true")
    parser.add_argument("--model", type=Path, default=configured_model_path())
    parser.add_argument("--text-columns", type=parse_text_columns, default=list(DEFAULT_TEXT_COLUMNS))
    parser.add_argument("--confidence-review-threshold", type=float, default=None)
    parser.add_argument("--db-labels", type=parse_label_set, default=DEFAULT_DB_LABELS)
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
    base_status: dict[str, Any] = {
        "status": "running",
        "pid": os.getpid(), 
        "started_at": utc_now(),
        "finished_at": None,
        "message": "Incremental AI publication update is running.",
        "model": str(args.model),
        "db_labels": list(args.db_labels),
        "log_path": str(args.log_path) if args.log_path else None,
    }
    write_status(args.status, base_status)

    try:
        result = run_incremental_update(
            state_path=args.state,
            state_backend=args.state_backend,
            state_key=args.state_key,
            output_root=args.output_root,
            explicit_from_date=args.from_date,
            initial_from_date=args.initial_from_date,
            to_date=args.to_date,
            per_page=args.per_page,
            max_records=args.max_records,
            email=args.email,
            api_key=args.api_key,
            strict_lk_only=args.strict_lk_only,
            model_path=args.model,
            text_columns=tuple(args.text_columns),
            confidence_review_threshold=args.confidence_review_threshold,
            db_labels=tuple(args.db_labels),
            batch_size=args.batch_size,
            skip_db=False,
        )
    except Exception as exc:
        write_status(
            args.status,
            {
                **base_status,
                "status": "failed",
                "finished_at": utc_now(),
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        raise

    write_status(
        args.status,
        {
            **base_status,
            "status": "succeeded",
            "finished_at": utc_now(),
            "message": "Incremental AI publication update completed.",
            "result": {
                "run_id": result.run_id,
                "from_date": result.from_date,
                "to_date": result.to_date,
                "records_collected": result.records_collected,
                "records_selected_for_db": result.records_selected_for_db,
                "records_loaded": result.records_loaded,
                "csv_output": str(result.csv_output),
                "db_load_output": str(result.db_load_output),
                "checkpoint_output": str(result.checkpoint_output),
            },
        },
    )


if __name__ == "__main__":
    main()
