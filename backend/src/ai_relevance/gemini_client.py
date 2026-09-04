"""Small Gemini client used by the AI relevance runner."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from src.ai_relevance.config import GeminiConfig
from src.ai_relevance.fields import PublicationMetadata
from src.ai_relevance.prompt import build_classification_prompt
from src.ai_relevance.schema import AI_RESPONSE_SCHEMA, AIClassification, validate_ai_response


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeminiUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class GeminiClassificationResult:
    classification: AIClassification
    usage: GeminiUsage
    raw_response: str


class GeminiQuotaExceededError(RuntimeError):
    """Raised when Gemini reports a quota exhaustion that should stop a run."""


class GeminiAIClient:
    """Gemini structured-output client with bounded retry behaviour."""

    def __init__(self, config: GeminiConfig):
        if not config.api_key:
            raise ValueError("GEMINI_API_KEY is required to call Gemini")
        self.config = config
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - exercised by integration setup
            raise RuntimeError(
                "Install the official Google GenAI SDK: pip install google-genai"
            ) from exc

        self._types = types
        self._client = genai.Client(api_key=config.api_key)

    def classify(self, publication: PublicationMetadata) -> GeminiClassificationResult:
        prompt = build_classification_prompt(
            publication,
            prompt_version=self.config.prompt_version,
        )
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.config.model,
                    contents=prompt,
                    config=self._types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AI_RESPONSE_SCHEMA,
                        temperature=0,
                        candidate_count=1,
                    ),
                )
                raw_text = getattr(response, "text", "") or ""
                payload = json.loads(raw_text)
                classification = validate_ai_response(payload)
                return GeminiClassificationResult(
                    classification=classification,
                    usage=_usage_from_response(response),
                    raw_response=raw_text,
                )
            except Exception as exc:  # noqa: BLE001 - SDK exception types vary by release
                last_error = exc
                if _is_quota_exhausted(exc):
                    raise GeminiQuotaExceededError(str(exc)) from exc
                retryable = _is_retryable(exc)
                if not retryable or attempt >= self.config.max_retries:
                    break
                wait_seconds = min(2 ** (attempt - 1), 30)
                LOGGER.warning(
                    "Gemini request failed for publication_id=%s attempt=%s/%s; retrying in %ss: %s",
                    publication.publication_id,
                    attempt,
                    self.config.max_retries,
                    wait_seconds,
                    exc,
                )
                time.sleep(wait_seconds)

        raise RuntimeError(str(last_error) if last_error else "Gemini request failed")


class OpenRouterAIClient:
    """OpenRouter chat-completions client using JSON-schema structured outputs."""

    def __init__(self, config: GeminiConfig):
        if not config.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required when AI_LLM_PROVIDER=openrouter")
        self.config = config
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - requests is already a project dependency
            raise RuntimeError("Install requests to call OpenRouter") from exc
        self._requests = requests

    def classify(self, publication: PublicationMetadata) -> GeminiClassificationResult:
        prompt = build_classification_prompt(
            publication,
            prompt_version=self.config.prompt_version,
        )
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self._requests.post(
                    self.config.openrouter_base_url,
                    headers={
                        "Authorization": f"Bearer {self.config.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "stream": False,
                        "provider": {"require_parameters": True},
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "ai_relevance_classification",
                                "strict": True,
                                "schema": AI_RESPONSE_SCHEMA,
                            },
                        },
                    },
                    timeout=self.config.timeout_seconds,
                )
                if response.status_code == 429:
                    raise GeminiQuotaExceededError(response.text)
                if response.status_code >= 500:
                    raise RuntimeError(response.text)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                payload = json.loads(content) if isinstance(content, str) else content
                classification = validate_ai_response(payload)
                return GeminiClassificationResult(
                    classification=classification,
                    usage=_usage_from_openrouter(data),
                    raw_response=json.dumps(payload),
                )
            except Exception as exc:  # noqa: BLE001 - HTTP/SDK exception types vary
                last_error = exc
                if isinstance(exc, GeminiQuotaExceededError) or _is_quota_exhausted(exc):
                    raise GeminiQuotaExceededError(str(exc)) from exc
                retryable = _is_retryable(exc)
                if not retryable or attempt >= self.config.max_retries:
                    break
                wait_seconds = min(2 ** (attempt - 1), 30)
                LOGGER.warning(
                    "OpenRouter request failed for publication_id=%s attempt=%s/%s; retrying in %ss: %s",
                    publication.publication_id,
                    attempt,
                    self.config.max_retries,
                    wait_seconds,
                    exc,
                )
                time.sleep(wait_seconds)

        raise RuntimeError(str(last_error) if last_error else "OpenRouter request failed")


class OllamaAIClient:
    """Local Ollama chat client using JSON-schema formatted responses."""

    def __init__(self, config: GeminiConfig):
        self.config = config
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - requests is already a project dependency
            raise RuntimeError("Install requests to call Ollama") from exc
        self._requests = requests

    def classify(self, publication: PublicationMetadata) -> GeminiClassificationResult:
        prompt = build_classification_prompt(
            publication,
            prompt_version=self.config.prompt_version,
        )
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self._requests.post(
                    self.config.ollama_base_url,
                    json={
                        "model": self.config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "format": AI_RESPONSE_SCHEMA,
                        "options": {
                            "temperature": 0,
                            "top_k": 1,
                            "top_p": 1,
                            "seed": self.config.ollama_seed,
                        },
                    },
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "")
                payload = json.loads(content) if isinstance(content, str) else content
                classification = validate_ai_response(payload)
                return GeminiClassificationResult(
                    classification=classification,
                    usage=_usage_from_ollama(data),
                    raw_response=json.dumps(payload),
                )
            except Exception as exc:  # noqa: BLE001 - local HTTP errors vary
                last_error = exc
                retryable = _is_retryable(exc)
                if not retryable or attempt >= self.config.max_retries:
                    break
                wait_seconds = min(2 ** (attempt - 1), 30)
                LOGGER.warning(
                    "Ollama request failed for publication_id=%s attempt=%s/%s; retrying in %ss: %s",
                    publication.publication_id,
                    attempt,
                    self.config.max_retries,
                    wait_seconds,
                    exc,
                )
                time.sleep(wait_seconds)

        raise RuntimeError(str(last_error) if last_error else "Ollama request failed")


def _usage_from_response(response: Any) -> GeminiUsage:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return GeminiUsage()
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    total_tokens = int(getattr(usage, "total_token_count", 0) or 0)
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return GeminiUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _usage_from_openrouter(data: dict[str, Any]) -> GeminiUsage:
    usage = data.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return GeminiUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _usage_from_ollama(data: dict[str, Any]) -> GeminiUsage:
    input_tokens = int(data.get("prompt_eval_count") or 0)
    output_tokens = int(data.get("eval_count") or 0)
    return GeminiUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _is_retryable(error: Exception) -> bool:
    text = str(error).casefold()
    retry_markers = (
        "timeout",
        "temporar",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "unavailable",
        "connection",
    )
    return any(marker in text for marker in retry_markers)


def _is_quota_exhausted(error: Exception) -> bool:
    text = str(error).casefold()
    quota_markers = (
        "resource_exhausted",
        "generate_content_free_tier_requests",
        "quota exceeded",
        "quotaid",
        "generaterequestsperdayperprojectpermodel-freetier",
    )
    return any(marker in text for marker in quota_markers)


def estimated_cost(
    usage: GeminiUsage,
    *,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    return (
        usage.input_tokens / 1_000_000 * input_price_per_million
        + usage.output_tokens / 1_000_000 * output_price_per_million
    )
