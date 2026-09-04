"""Gemini AI relevance classification runner with checkpoint/resume support."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Protocol

import pandas as pd

from src.ai_relevance.config import (
    DEFAULT_CANDIDATE_OUTPUT,
    DEFAULT_FIRST_TEST_IDS_OUTPUT,
    DEFAULT_FIRST_TEST_OUTPUT,
    GeminiConfig,
)
from src.ai_relevance.fields import present_metadata_columns, publication_metadata
from src.ai_relevance.gemini_client import (
    GeminiAIClient,
    GeminiClassificationResult,
    GeminiQuotaExceededError,
    GeminiUsage,
    OllamaAIClient,
    OpenRouterAIClient,
    estimated_cost,
)
from src.ai_relevance.sampling import select_first_test_records
from src.modeling.artifacts import write_csv_artifact
from src.utils.io_utils import load_dataset, save_dataset


LOGGER = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "publication_id",
    "ai_llm_label",
    "ai_llm_confidence",
    "ai_llm_category",
    "ai_llm_reason",
    "ai_llm_evidence",
    "ai_llm_model",
    "ai_prompt_version",
    "ai_llm_status",
    "ai_llm_error",
    "ai_llm_processed_at",
    "ai_llm_input_tokens",
    "ai_llm_output_tokens",
    "ai_llm_total_tokens",
    "sampling_bucket",
]


class ClassificationClient(Protocol):
    def classify(self, publication: Any) -> GeminiClassificationResult:
        ...


@dataclass(frozen=True)
class GeminiRunConfig:
    input_path: Path = DEFAULT_CANDIDATE_OUTPUT
    output_path: Path = DEFAULT_FIRST_TEST_OUTPUT
    selected_ids_output: Path = DEFAULT_FIRST_TEST_IDS_OUTPUT
    limit: int = 10
    first_test: bool = True
    resume: bool = False
    random_seed: int = 42
    gemini: GeminiConfig = GeminiConfig()


@dataclass(frozen=True)
class GeminiRunResult:
    output_path: Path
    selected_ids_output: Path
    model: str
    prompt_version: str
    attempted: int
    successful: int
    failed: int
    invalid_response: int
    skipped_existing: int
    ai: int
    non_ai: int
    review: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


def _existing_success_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    frame = load_dataset(output_path)
    if "publication_id" not in frame.columns or "ai_llm_status" not in frame.columns:
        return set()
    return set(
        frame.loc[frame["ai_llm_status"] == "success", "publication_id"].astype(str)
    )


def _existing_rows(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    return load_dataset(output_path).to_dict("records")


def _result_row(
    record: dict[str, Any],
    *,
    gemini_config: GeminiConfig,
    result: GeminiClassificationResult | None,
    status: str,
    error: str = "",
) -> dict[str, Any]:
    metadata = publication_metadata(record)
    row = {
        "publication_id": metadata.publication_id,
        "ai_llm_label": "",
        "ai_llm_confidence": "",
        "ai_llm_category": "",
        "ai_llm_reason": "",
        "ai_llm_evidence": "",
        "ai_llm_model": gemini_config.model,
        "ai_prompt_version": gemini_config.prompt_version,
        "ai_llm_status": status,
        "ai_llm_error": error,
        "ai_llm_processed_at": datetime.now(UTC).isoformat(),
        "ai_llm_input_tokens": "0",
        "ai_llm_output_tokens": "0",
        "ai_llm_total_tokens": "0",
        "sampling_bucket": str(record.get("sampling_bucket", "")),
    }
    for column in present_metadata_columns(list(record.keys())):
        row[column] = record.get(column, "")
    if result is not None:
        row.update(result.classification.as_output_fields())
        row["ai_llm_input_tokens"] = str(result.usage.input_tokens)
        row["ai_llm_output_tokens"] = str(result.usage.output_tokens)
        row["ai_llm_total_tokens"] = str(result.usage.total_tokens)
    return row


def _fieldnames(rows: Iterable[dict[str, Any]]) -> list[str]:
    fieldnames = list(OUTPUT_COLUMNS)
    for row in rows:
        for column in row:
            if column not in fieldnames:
                fieldnames.append(column)
    return fieldnames


def run_gemini_classification(
    config: GeminiRunConfig,
    *,
    client: ClassificationClient | None = None,
) -> GeminiRunResult:
    """Classify a bounded set of publications and checkpoint after each row."""

    if config.first_test and config.limit != 10:
        raise ValueError("The first Gemini test must use --limit 10 exactly")
    if config.output_path.exists() and not config.resume:
        raise FileExistsError(
            f"Output already exists: {config.output_path}. Use --resume or choose a new output path."
        )

    candidates = load_dataset(config.input_path)
    if "publication_id" not in candidates.columns:
        candidates = candidates.copy()
        candidates["publication_id"] = [
            publication_metadata(record, fallback=index).publication_id
            for index, record in candidates.iterrows()
        ]
    selected = select_first_test_records(
        candidates,
        limit=config.limit,
        random_seed=config.random_seed,
    )
    save_dataset(selected[["publication_id"]], config.selected_ids_output)

    if client is not None:
        gemini_client = client
    elif config.gemini.provider == "openrouter":
        gemini_client = OpenRouterAIClient(config.gemini)
    elif config.gemini.provider == "google":
        gemini_client = GeminiAIClient(config.gemini)
    elif config.gemini.provider == "ollama":
        gemini_client = OllamaAIClient(config.gemini)
    else:
        raise ValueError("AI_LLM_PROVIDER must be 'google', 'openrouter', or 'ollama'")
    existing_rows = _existing_rows(config.output_path) if config.resume else []
    success_ids = _existing_success_ids(config.output_path) if config.resume else set()
    rows = list(existing_rows)

    attempted = successful = failed = invalid_response = skipped_existing = 0
    for index, record in enumerate(selected.to_dict("records"), start=1):
        metadata = publication_metadata(record, fallback=index)
        if metadata.publication_id in success_ids:
            skipped_existing += 1
            LOGGER.info("Skipping already successful publication_id=%s", metadata.publication_id)
            continue

        attempted += 1
        try:
            result = gemini_client.classify(metadata)
            row = _result_row(record, gemini_config=config.gemini, result=result, status="success")
            successful += 1
            LOGGER.info(
                "Gemini AI relevance %s/%s publication_id=%s status=success label=%s tokens=%s",
                index,
                config.limit,
                metadata.publication_id,
                result.classification.label,
                result.usage.total_tokens,
            )
        except ValueError as exc:
            invalid_response += 1
            row = _result_row(
                record,
                gemini_config=config.gemini,
                result=None,
                status="invalid_response",
                error=str(exc),
            )
            LOGGER.warning("Invalid Gemini response publication_id=%s: %s", metadata.publication_id, exc)
        except GeminiQuotaExceededError as exc:
            LOGGER.error(
                "Gemini quota exhausted after %s attempted record(s). "
                "Checkpoint is preserved at %s; rerun with --resume after quota resets or billing is enabled.",
                attempted - 1,
                config.output_path,
            )
            break
        except Exception as exc:  # noqa: BLE001 - keep the run moving after one bad record
            failed += 1
            row = _result_row(
                record,
                gemini_config=config.gemini,
                result=None,
                status="failed",
                error=str(exc),
            )
            LOGGER.warning("Gemini classification failed publication_id=%s: %s", metadata.publication_id, exc)

        rows = [existing for existing in rows if existing.get("publication_id") != row["publication_id"]]
        rows.append(row)
        write_csv_artifact(config.output_path, fieldnames=_fieldnames(rows), rows=rows)

    output = pd.DataFrame(rows)
    success = output[output.get("ai_llm_status", "") == "success"] if not output.empty else output
    usage = GeminiUsage(
        input_tokens=int(pd.to_numeric(output.get("ai_llm_input_tokens", []), errors="coerce").fillna(0).sum()) if not output.empty else 0,
        output_tokens=int(pd.to_numeric(output.get("ai_llm_output_tokens", []), errors="coerce").fillna(0).sum()) if not output.empty else 0,
        total_tokens=int(pd.to_numeric(output.get("ai_llm_total_tokens", []), errors="coerce").fillna(0).sum()) if not output.empty else 0,
    )
    return GeminiRunResult(
        output_path=config.output_path,
        selected_ids_output=config.selected_ids_output,
        model=config.gemini.model,
        prompt_version=config.gemini.prompt_version,
        attempted=attempted,
        successful=successful,
        failed=failed,
        invalid_response=invalid_response,
        skipped_existing=skipped_existing,
        ai=int((success.get("ai_llm_label", pd.Series(dtype=str)) == "AI").sum()) if not success.empty else 0,
        non_ai=int((success.get("ai_llm_label", pd.Series(dtype=str)) == "NON_AI").sum()) if not success.empty else 0,
        review=int((success.get("ai_llm_label", pd.Series(dtype=str)) == "REVIEW").sum()) if not success.empty else 0,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        estimated_cost_usd=estimated_cost(
            usage,
            input_price_per_million=config.gemini.input_price_per_million,
            output_price_per_million=config.gemini.output_price_per_million,
        ),
    )


def render_run_summary(result: GeminiRunResult) -> str:
    return "\n".join(
        [
            "Gemini AI Relevance Test",
            "-------------------------",
            "",
            f"Model: {result.model}",
            f"Prompt version: {result.prompt_version}",
            f"Total attempted: {result.attempted}",
            f"Successful: {result.successful}",
            f"Failed: {result.failed}",
            f"Invalid responses: {result.invalid_response}",
            f"Skipped existing successful: {result.skipped_existing}",
            f"AI: {result.ai}",
            f"NON_AI: {result.non_ai}",
            f"REVIEW: {result.review}",
            f"Input tokens: {result.input_tokens}",
            f"Output tokens: {result.output_tokens}",
            f"Total tokens: {result.total_tokens}",
            f"ESTIMATED COST: ${result.estimated_cost_usd:.6f}",
            f"Output file: {result.output_path}",
            "",
            "FIRST 10-RECORD TEST COMPLETED.",
            "No further Gemini calls were made.",
            "Stopped after the requested 10-record test.",
            "10-record Gemini test completed. No further publication classification was started.",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gemini AI relevance classification.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CANDIDATE_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_FIRST_TEST_OUTPUT)
    parser.add_argument("--selected-ids-output", type=Path, default=DEFAULT_FIRST_TEST_IDS_OUTPUT)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--first-test", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    result = run_gemini_classification(
        GeminiRunConfig(
            input_path=args.input,
            output_path=args.output,
            selected_ids_output=args.selected_ids_output,
            limit=args.limit,
            first_test=args.first_test,
            resume=args.resume,
            random_seed=args.random_seed,
            gemini=GeminiConfig.from_env(),
        )
    )
    print(render_run_summary(result))
