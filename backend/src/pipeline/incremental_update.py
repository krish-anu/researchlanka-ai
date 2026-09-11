"""Incremental monthly/manual data refresh pipeline.

The full rebuild pipeline remains useful for historical backfills. This module
handles routine refreshes: collect only the publication-date window since the
last successful run, preprocess rows into the existing final-publications
contract, apply the AI/non-AI/review classifier, and upsert only selected labels
into PostgreSQL.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.collectors.openalex_collector import (
    LK_AUTHORSHIP_FILTER,
    OpenAlexCollector,
    openalex_work_id,
)
from src.database.load_records import load_record_file
from src.database.pipeline_state import (
    DEFAULT_INCREMENTAL_STATE_KEY,
    PipelineRunRecord,
    read_pipeline_checkpoint,
    record_failed_pipeline_run,
    record_successful_pipeline_run,
)
from src.modeling.training import combined_text, parse_text_columns
from src.pipeline.kaggle_collect_openalex_sri_lanka import (
    collect_quality_report,
    print_collection_report,
    write_doi_conflict_report,
)
from src.preprocessing.openalex_normalizer import CSV_COLUMNS, work_to_row


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = PROJECT_ROOT / "outputs" / "incremental" / "state.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "incremental" / "runs"
DEFAULT_INITIAL_FROM_DATE = date(2016, 1, 1)
DEFAULT_MODEL_PATH = (
    PROJECT_ROOT / "data" / "models" / "ai_relevance" / "ai_relevance_linear_svm.joblib"
)
DEFAULT_TEXT_COLUMNS = ("title", "abstract", "keywords", "topics", "concepts")
DEFAULT_DB_LABELS = ("AI",)
DEFAULT_STATE_BACKEND = "database"
AI_COLUMNS = (
    "ai_classification_label",
    "ai_classification_confidence",
    "ai_classification_model",
    "ai_classification_reason",
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncrementalRunResult:
    run_id: str
    from_date: str
    to_date: str
    raw_output: Path
    csv_output: Path
    db_load_output: Path
    records_collected: int
    records_selected_for_db: int
    records_loaded: int
    checkpoint_output: Path
    model_path: Path | None
    db_labels: tuple[str, ...]
    state_backend: str
    state_source: str


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO date: {value}") from exc


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Checkpoint must be a JSON object: {path}")
    return payload


def _date_after(value: date) -> date:
    return value + timedelta(days=1)


def checkpoint_from_date(
    path: Path,
    *,
    explicit_from_date: date | None,
    initial_from_date: date,
) -> date:
    if explicit_from_date is not None:
        return explicit_from_date

    checkpoint = load_checkpoint(path)
    last_collected = (
        checkpoint.get("last_successful_collection_date")
        or checkpoint.get("last_collected_date")
    )
    if isinstance(last_collected, str) and last_collected:
        return _date_after(parse_iso_date(last_collected))
    return initial_from_date


def database_from_date(
    *,
    explicit_from_date: date | None,
    initial_from_date: date,
    database_url: str | None = None,
    state_key: str = DEFAULT_INCREMENTAL_STATE_KEY,
) -> tuple[date, str]:
    if explicit_from_date is not None:
        return explicit_from_date, "explicit"

    checkpoint = read_pipeline_checkpoint(
        database_url=database_url,
        state_key=state_key,
        derive_from_final_publications=True,
    )
    if checkpoint.last_successful_collection_date is not None:
        return _date_after(checkpoint.last_successful_collection_date), checkpoint.source
    return initial_from_date, checkpoint.source


def save_checkpoint(
    path: Path,
    *,
    result: IncrementalRunResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_successful_collection_date": result.to_date,
        "last_collected_date": result.to_date,
        "last_successful_run_id": result.run_id,
        "last_successful_run_at": (
            datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "last_from_date": result.from_date,
        "last_records_collected": result.records_collected,
        "last_records_loaded": result.records_loaded,
        "last_raw_output": str(result.raw_output),
        "last_csv_output": str(result.csv_output),
        "last_db_load_output": str(result.db_load_output),
        "last_records_selected_for_db": result.records_selected_for_db,
        "last_db_labels": list(result.db_labels),
        "last_model_path": str(result.model_path) if result.model_path else None,
        "state_backend": result.state_backend,
        "state_source": result.state_source,
    }
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def date_filters(from_date: date, to_date: date) -> list[str]:
    return [
        LK_AUTHORSHIP_FILTER,
        f"from_publication_date:{from_date.isoformat()}",
        f"to_publication_date:{to_date.isoformat()}",
    ]


def collect_openalex_rows(
    *,
    from_date: date,
    to_date: date,
    raw_output: Path,
    per_page: int,
    max_records: int | None,
    email: str | None,
    api_key: str | None,
    strict_lk_only: bool,
) -> list[dict[str, Any]]:
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    collector = OpenAlexCollector(email=email, api_key=api_key)
    filters = date_filters(from_date, to_date)
    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []

    with raw_output.open("w", encoding="utf-8") as raw_file:
        pages = collector.iter_sri_lankan_work_pages(
            filters=filters,
            from_year=from_date.year,
            to_year=to_date.year,
            per_page=per_page,
            strict_lk_only=strict_lk_only,
        )
        for page in pages:
            for work in page.works:
                work_id = openalex_work_id(work)
                if work_id is None or work_id in seen_ids:
                    continue
                seen_ids.add(work_id)
                raw_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                rows.append(work_to_row(work))
                if max_records is not None and len(rows) >= max_records:
                    return rows
    return rows


def configured_model_path(value: str | Path | None = None) -> Path | None:
    raw_value = value or os.getenv("RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH")
    raw_value = raw_value or os.getenv("INCREMENTAL_MODEL") or DEFAULT_MODEL_PATH
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def validate_model_path(model_path: Path | None) -> None:
    if model_path is None:
        return
    if not model_path.exists():
        raise FileNotFoundError(
            "AI relevance model was not found at "
            f"{model_path}. Set RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH to the "
            "deployed .joblib artifact."
        )
    if not model_path.is_file():
        raise ValueError(f"AI relevance model path is not a file: {model_path}")


def prediction_text(frame: pd.DataFrame, text_columns: tuple[str, ...]) -> pd.Series:
    available_columns = [column for column in text_columns if column in frame.columns]
    if not available_columns:
        return pd.Series([""] * len(frame), index=frame.index)
    return combined_text(frame[available_columns].fillna(""), available_columns)


def normalize_prediction_label(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    normalized = text.casefold().replace("_", "-")
    if normalized in {"ai", "artificial-intelligence", "artificial intelligence"}:
        return "AI", ""
    if normalized in {"non-ai", "non ai", "not-ai", "not ai", "nonai"}:
        return "non-AI", ""
    if normalized in {"review", "manual-review", "manual review", "uncertain"}:
        return "review", ""
    return "review", f"unexpected_model_label:{text}"


def apply_ai_classification(
    rows: list[dict[str, Any]],
    *,
    model_path: Path | None,
    text_columns: tuple[str, ...],
    confidence_review_threshold: float | None,
) -> list[dict[str, Any]]:
    if not rows:
        return rows

    if model_path is None:
        return [
            {
                **row,
                "ai_classification_label": "review",
                "ai_classification_confidence": None,
                "ai_classification_model": None,
                "ai_classification_reason": "model_not_configured",
            }
            for row in rows
        ]

    validate_model_path(model_path)
    model = joblib.load(model_path)
    frame = pd.DataFrame(rows)
    text = prediction_text(frame, text_columns)
    predictions = list(model.predict(text)) if len(text) else []
    confidences: list[float | None]
    if hasattr(model, "predict_proba") and len(text):
        confidences = [float(values.max()) for values in model.predict_proba(text)]
    else:
        confidences = [None] * len(predictions)

    classified_rows: list[dict[str, Any]] = []
    for row, prediction, confidence in zip(rows, predictions, confidences, strict=True):
        label, reason = normalize_prediction_label(prediction)
        if (
            confidence_review_threshold is not None
            and confidence is not None
            and confidence < confidence_review_threshold
        ):
            label = "review"
            reason = f"confidence_below_threshold:{confidence_review_threshold:.3f}"
        classified_rows.append(
            {
                **row,
                "ai_classification_label": label,
                "ai_classification_confidence": (
                    None if confidence is None else f"{confidence:.6f}"
                ),
                "ai_classification_model": str(model_path),
                "ai_classification_reason": reason or None,
            }
        )
    return classified_rows


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [*CSV_COLUMNS, *AI_COLUMNS]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_label_set(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    raw_values = value.split(",") if isinstance(value, str) else list(value)
    labels = []
    for item in raw_values:
        label, reason = normalize_prediction_label(item)
        if reason:
            raise argparse.ArgumentTypeError(f"Unsupported AI classification label: {item}")
        labels.append(label)
    if not labels:
        raise argparse.ArgumentTypeError("At least one DB label is required.")
    return tuple(dict.fromkeys(labels))


def filter_rows_for_database(
    rows: list[dict[str, Any]],
    *,
    labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    allowed = set(labels)
    return [
        row
        for row in rows
        if str(row.get("ai_classification_label") or "").strip() in allowed
    ]


def run_incremental_update(
    *,
    state_path: Path,
    state_backend: str,
    state_key: str,
    output_root: Path,
    explicit_from_date: date | None,
    initial_from_date: date,
    to_date: date,
    per_page: int,
    max_records: int | None,
    email: str | None,
    api_key: str | None,
    strict_lk_only: bool,
    model_path: Path | None,
    text_columns: tuple[str, ...],
    confidence_review_threshold: float | None,
    db_labels: tuple[str, ...],
    batch_size: int,
    skip_db: bool,
) -> IncrementalRunResult:
    model_path = configured_model_path(model_path)
    validate_model_path(model_path)

    database_url = os.getenv("DATABASE_URL")
    if state_backend == "database":
        if skip_db or not database_url:
            logger.warning(
                "Database state requested without an active database; "
                "falling back to JSON checkpoint."
            )
            from_date = checkpoint_from_date(
                state_path,
                explicit_from_date=explicit_from_date,
                initial_from_date=initial_from_date,
            )
            state_source = "json_checkpoint" if explicit_from_date is None else "explicit"
            effective_state_backend = "json"
        else:
            from_date, state_source = database_from_date(
                explicit_from_date=explicit_from_date,
                initial_from_date=initial_from_date,
                database_url=database_url,
                state_key=state_key,
            )
            effective_state_backend = "database"
    elif state_backend == "json":
        from_date = checkpoint_from_date(
            state_path,
            explicit_from_date=explicit_from_date,
            initial_from_date=initial_from_date,
        )
        state_source = "json_checkpoint" if explicit_from_date is None else "explicit"
        effective_state_backend = "json"
    else:
        raise ValueError("state_backend must be 'database' or 'json'.")

    if from_date > to_date:
        raise ValueError(f"from_date {from_date} cannot be after to_date {to_date}")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / run_id
    raw_output = run_dir / "openalex_incremental_raw.jsonl"
    csv_output = run_dir / "openalex_incremental_classified.csv"
    db_load_output = run_dir / "openalex_incremental_db_load.csv"
    doi_conflicts_output = run_dir / "openalex_incremental_doi_conflicts.csv"

    records_loaded = 0
    rows: list[dict[str, Any]] = []
    db_rows: list[dict[str, Any]] = []
    logger.info(
        "Incremental collection window: %s to %s (state_backend=%s state_source=%s)",
        from_date,
        to_date,
        effective_state_backend,
        state_source,
    )
    try:
        rows = collect_openalex_rows(
            from_date=from_date,
            to_date=to_date,
            raw_output=raw_output,
            per_page=per_page,
            max_records=max_records,
            email=email,
            api_key=api_key,
            strict_lk_only=strict_lk_only,
        )
        rows = apply_ai_classification(
            rows,
            model_path=model_path,
            text_columns=text_columns,
            confidence_review_threshold=confidence_review_threshold,
        )
        write_rows_csv(csv_output, rows)
        db_rows = filter_rows_for_database(rows, labels=db_labels)
        write_rows_csv(db_load_output, db_rows)
        write_doi_conflict_report(raw_output, doi_conflicts_output)

        if skip_db:
            logger.info("Database load skipped by --skip-db")
        elif not database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Use --skip-db for a collection-only run."
            )
        else:
            records_loaded = load_record_file(db_load_output, batch_size=batch_size)
    except Exception as exc:
        if effective_state_backend == "database" and database_url:
            record_failed_pipeline_run(
                run=PipelineRunRecord(
                    run_id=run_id,
                    state_key=state_key,
                    from_date=from_date,
                    to_date=to_date,
                    status="failed",
                    records_collected=len(rows),
                    records_selected_for_db=len(db_rows),
                    records_loaded=records_loaded,
                    raw_output=raw_output,
                    csv_output=csv_output,
                    db_load_output=db_load_output,
                    model_path=model_path,
                    db_labels=db_labels,
                    error=str(exc),
                ),
                database_url=database_url,
            )
        raise

    result = IncrementalRunResult(
        run_id=run_id,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        raw_output=raw_output,
        csv_output=csv_output,
        db_load_output=db_load_output,
        records_collected=len(rows),
        records_selected_for_db=len(db_rows),
        records_loaded=records_loaded,
        checkpoint_output=state_path,
        model_path=model_path,
        db_labels=db_labels,
        state_backend=effective_state_backend,
        state_source=state_source,
    )
    if effective_state_backend == "database" and database_url:
        record_successful_pipeline_run(
            run=PipelineRunRecord(
                run_id=run_id,
                state_key=state_key,
                from_date=from_date,
                to_date=to_date,
                status="succeeded",
                records_collected=len(rows),
                records_selected_for_db=len(db_rows),
                records_loaded=records_loaded,
                raw_output=raw_output,
                csv_output=csv_output,
                db_load_output=db_load_output,
                model_path=model_path,
                db_labels=db_labels,
            ),
            database_url=database_url,
        )
    save_checkpoint(state_path, result=result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an incremental ResearchLanka refresh.")
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
        default=os.getenv("RESEARCHLANKA_INCREMENTAL_STATE_KEY", DEFAULT_INCREMENTAL_STATE_KEY),
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
    parser.add_argument("--email", default=None)
    parser.add_argument("--api-key", default=os.getenv("OPENALEX_API_KEY"))
    parser.add_argument("--strict-lk-only", action="store_true")
    parser.add_argument("--model", type=Path, default=configured_model_path())
    parser.add_argument("--text-columns", type=parse_text_columns, default=list(DEFAULT_TEXT_COLUMNS))
    parser.add_argument("--confidence-review-threshold", type=float, default=None)
    parser.add_argument(
        "--db-labels",
        type=parse_label_set,
        default=DEFAULT_DB_LABELS,
        help="Comma-separated labels to insert into PostgreSQL. Default: AI.",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--skip-db", action="store_true")
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
        skip_db=args.skip_db,
    )
    if result.records_collected:
        print_collection_report(collect_quality_report(result.raw_output, records_skipped=0))
    print(json.dumps({key: str(value) for key, value in asdict(result).items()}, indent=2))


if __name__ == "__main__":
    main()
