"""Configuration for the AI relevance pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PUBLICATIONS_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_AI_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "ai"
DEFAULT_CANDIDATE_OUTPUT = DEFAULT_AI_OUTPUT_DIR / "ai_llm_5000_candidates.csv"
DEFAULT_FIRST_TEST_OUTPUT = DEFAULT_AI_OUTPUT_DIR / "ai_llm_test_10_predictions.csv"
DEFAULT_FIRST_TEST_IDS_OUTPUT = DEFAULT_AI_OUTPUT_DIR / "ai_llm_test_10_ids.csv"
DEFAULT_HUMAN_REVIEW_OUTPUT = DEFAULT_AI_OUTPUT_DIR / "ai_human_review_sample.csv"
DEFAULT_EVALUATION_DIR = PROJECT_ROOT / "data" / "reports" / "ai_relevance"


@dataclass(frozen=True)
class GeminiConfig:
    """Runtime settings for Gemini classification."""

    api_key: str | None = None
    model: str = "gemini-3.8-flash"
    prompt_version: str = "v1"
    max_retries: int = 3
    timeout_seconds: float = 60.0
    max_concurrency: int = 1
    input_price_per_million: float = 0.0
    output_price_per_million: float = 0.0

    @classmethod
    def from_env(cls) -> "GeminiConfig":
        """Load Gemini settings from environment variables."""

        return cls(
            api_key=os.getenv("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            prompt_version=os.getenv("AI_PROMPT_VERSION", "v1"),
            max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "3")),
            timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60")),
            max_concurrency=int(os.getenv("GEMINI_MAX_CONCURRENCY", "1")),
            input_price_per_million=float(
                os.getenv("GEMINI_INPUT_PRICE_PER_MILLION", "0")
            ),
            output_price_per_million=float(
                os.getenv("GEMINI_OUTPUT_PRICE_PER_MILLION", "0")
            ),
        )


@dataclass(frozen=True)
class AIRelevanceConfig:
    """Stable paths used by the AI relevance workflow."""

    publications_input: Path = DEFAULT_PUBLICATIONS_INPUT
    output_dir: Path = DEFAULT_AI_OUTPUT_DIR
    candidate_output: Path = DEFAULT_CANDIDATE_OUTPUT
    first_test_output: Path = DEFAULT_FIRST_TEST_OUTPUT
    first_test_ids_output: Path = DEFAULT_FIRST_TEST_IDS_OUTPUT
    human_review_output: Path = DEFAULT_HUMAN_REVIEW_OUTPUT
    evaluation_dir: Path = DEFAULT_EVALUATION_DIR
