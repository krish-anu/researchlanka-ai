#!/usr/bin/env python3
"""Add OpenRouter Gemini predictions to the 150-row human verification CSV."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience for local runs
    load_dotenv = None

from src.ai_relevance.config import GeminiConfig  # noqa: E402
from src.ai_relevance.fields import publication_metadata  # noqa: E402
from src.ai_relevance.gemini_client import (  # noqa: E402
    GeminiQuotaExceededError,
    OpenRouterAIClient,
)


DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_150_human_verification_qwen3_mode_prediction.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_150_human_verification_qwen3_gemini_mode_prediction.csv"
)
GEMINI_COLUMN = "Gemini 3.8 Flash"


LOGGER = logging.getLogger(__name__)


def _load_env_files() -> None:
    if load_dotenv is None:
        return
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")


def _ensure_columns(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    defaults = {
        GEMINI_COLUMN: "",
        "gemini_confidence": 0.0,
        "gemini_category": "",
        "gemini_reason": "",
        "gemini_evidence": "",
        "gemini_status": "",
        "gemini_error": "",
        "gemini_model": "",
        "gemini_prompt_version": "",
        "gemini_processed_at": "",
        "gemini_input_tokens": 0,
        "gemini_output_tokens": 0,
        "gemini_total_tokens": 0,
    }
    for column, default in defaults.items():
        if column not in output.columns:
            output[column] = default
    text_columns = [
        GEMINI_COLUMN,
        "gemini_category",
        "gemini_reason",
        "gemini_evidence",
        "gemini_status",
        "gemini_error",
        "gemini_model",
        "gemini_prompt_version",
        "gemini_processed_at",
    ]
    for column in text_columns:
        output[column] = output[column].fillna("").astype("object")
    numeric_columns = [
        "gemini_confidence",
        "gemini_input_tokens",
        "gemini_output_tokens",
        "gemini_total_tokens",
    ]
    for column in numeric_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    return output


def _normalize_label(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    if text in {"TRUE", "AI", "YES", "1"}:
        return "AI"
    if text in {"FALSE", "NON_AI", "NON-AI", "NON AI", "NO", "0"}:
        return "NON_AI"
    if text == "REVIEW":
        return "REVIEW"
    return None


def _mode_prediction(row: pd.Series) -> str:
    labels = [
        _normalize_label(row.get("ai_llm_label")),
        _normalize_label(row.get("Qwen3-8B 4-bit")),
        _normalize_label(row.get(GEMINI_COLUMN)),
    ]
    labels = [label for label in labels if label is not None]
    if not labels:
        return "REVIEW"

    counts = {label: labels.count(label) for label in set(labels)}
    top_count = max(counts.values())
    winners = sorted(label for label, count in counts.items() if count == top_count)
    if len(winners) == 1:
        return winners[0]

    return "REVIEW"


def add_gemini_predictions(
    *,
    input_path: Path,
    output_path: Path,
    model: str,
    limit: int | None,
    resume: bool,
    delay_seconds: float,
    rate_limit_retries: int,
    rate_limit_wait_seconds: float,
) -> None:
    source = pd.read_csv(input_path)
    if resume and output_path.exists():
        saved = pd.read_csv(output_path)
        if len(saved) != len(source):
            raise ValueError(
                f"Cannot resume: {output_path} has {len(saved)} rows but {input_path} has {len(source)} rows"
            )
        frame = saved
    else:
        frame = source

    frame = _ensure_columns(frame)
    config = GeminiConfig(
        provider="openrouter",
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openrouter_base_url=os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1/chat/completions",
        ),
        model=model,
        prompt_version=os.getenv("AI_PROMPT_VERSION", "v3"),
        max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "3")),
        timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "300")),
    )
    client = OpenRouterAIClient(config)

    pending = frame[~frame["gemini_status"].eq("success")].index.tolist()
    if limit is not None:
        pending = pending[:limit]

    LOGGER.info("Pending Gemini/OpenRouter rows: %s", len(pending))
    for position, idx in enumerate(pending, start=1):
        record = frame.loc[idx].to_dict()
        metadata = publication_metadata(record, fallback=idx)
        for rate_limit_attempt in range(rate_limit_retries + 1):
            try:
                result = client.classify(metadata)
                break
            except GeminiQuotaExceededError:
                if rate_limit_attempt >= rate_limit_retries:
                    LOGGER.exception(
                        "OpenRouter quota/rate limit reached. Saved checkpoint at %s",
                        output_path,
                    )
                    frame["mode_prediction"] = frame.apply(_mode_prediction, axis=1)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    frame.to_csv(output_path, index=False)
                    return
                LOGGER.warning(
                    "OpenRouter rate-limited row %s/%s. Waiting %.0f seconds before retry %s/%s.",
                    position,
                    len(pending),
                    rate_limit_wait_seconds,
                    rate_limit_attempt + 1,
                    rate_limit_retries,
                )
                time.sleep(rate_limit_wait_seconds)
        try:
            classification = result.classification
            frame.at[idx, GEMINI_COLUMN] = classification.label
            frame.at[idx, "gemini_confidence"] = classification.confidence
            frame.at[idx, "gemini_category"] = classification.ai_category
            frame.at[idx, "gemini_reason"] = classification.reason
            frame.at[idx, "gemini_evidence"] = " | ".join(classification.evidence)
            frame.at[idx, "gemini_status"] = "success"
            frame.at[idx, "gemini_error"] = ""
            frame.at[idx, "gemini_model"] = model
            frame.at[idx, "gemini_prompt_version"] = config.prompt_version
            frame.at[idx, "gemini_processed_at"] = datetime.now(UTC).isoformat()
            frame.at[idx, "gemini_input_tokens"] = result.usage.input_tokens
            frame.at[idx, "gemini_output_tokens"] = result.usage.output_tokens
            frame.at[idx, "gemini_total_tokens"] = result.usage.total_tokens
            LOGGER.info(
                "Gemini/OpenRouter %s/%s publication_id=%s label=%s",
                position,
                len(pending),
                metadata.publication_id,
                classification.label,
            )
        except Exception as exc:  # noqa: BLE001 - preserve row-level failure and continue
            frame.at[idx, "gemini_status"] = "failed"
            frame.at[idx, "gemini_error"] = str(exc)
            frame.at[idx, "gemini_model"] = model
            frame.at[idx, "gemini_prompt_version"] = config.prompt_version
            LOGGER.warning("Gemini/OpenRouter failed publication_id=%s: %s", metadata.publication_id, exc)

        frame["mode_prediction"] = frame.apply(_mode_prediction, axis=1)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output_path, index=False)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    frame["mode_prediction"] = frame.apply(_mode_prediction, axis=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    LOGGER.info("Saved %s", output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=os.getenv("AI_LLM_MODEL", "gemini-3.8-flash"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--rate-limit-retries", type=int, default=0)
    parser.add_argument("--rate-limit-wait-seconds", type=float, default=120.0)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    _load_env_files()
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    add_gemini_predictions(
        input_path=args.input,
        output_path=args.output,
        model=args.model,
        limit=args.limit,
        resume=args.resume,
        delay_seconds=args.delay_seconds,
        rate_limit_retries=args.rate_limit_retries,
        rate_limit_wait_seconds=args.rate_limit_wait_seconds,
    )


if __name__ == "__main__":
    main()
