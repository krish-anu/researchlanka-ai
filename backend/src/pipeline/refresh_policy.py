"""Shared production refresh policy for publication ingestion entry points."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AI_RELEVANCE_MODEL_MANIFEST_PATH = (
    PROJECT_ROOT / "configurations" / "ai_relevance_model_manifest.json"
)
FALLBACK_AI_RELEVANCE_MODEL_PATH = (
    PROJECT_ROOT
    / "data"
    / "models"
    / "ai_relevance"
    / "metadata_ablation"
    / "A2_title_abstract_keywords.joblib"
)
FALLBACK_TEXT_COLUMNS = ("title", "abstract", "keywords")
FALLBACK_AUTO_AI_THRESHOLD = 0.85
FALLBACK_AUTO_NON_AI_THRESHOLD = 0.4
DEFAULT_DB_LABELS = ("AI", "review")


@dataclass(frozen=True)
class AIRelevanceModelManifest:
    """Versioned production contract for AI relevance inference."""

    model_id: str
    model_type: str
    model_path: Path
    features: tuple[str, ...]
    calibrator: str | None
    calibrator_path: Path | None
    secondary_model_path: Path | None
    auto_ai_threshold: float
    auto_non_ai_threshold: float
    training_dataset: str | None
    created_at: str | None
    sha256: str | None


@dataclass(frozen=True)
class PublicationRefreshPolicy:
    """One policy shared by full, incremental, Kaggle, and admin refreshes."""

    model_path: Path | None
    text_columns: tuple[str, ...]
    confidence_review_threshold: float
    db_labels: tuple[str, ...] = DEFAULT_DB_LABELS
    auto_non_ai_threshold: float = FALLBACK_AUTO_NON_AI_THRESHOLD
    calibrator_path: Path | None = None
    secondary_model_path: Path | None = None
    model_manifest_path: Path | None = None
    model_id: str | None = None


def _resolve_project_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def configured_model_manifest_path(value: str | Path | None = None) -> Path | None:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_RELEVANCE_MODEL_MANIFEST_PATH")
    if raw_value in (None, ""):
        raw_value = DEFAULT_AI_RELEVANCE_MODEL_MANIFEST_PATH
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    return _resolve_project_path(raw_value)


def load_ai_relevance_model_manifest(
    manifest_path: str | Path | None = None,
) -> AIRelevanceModelManifest:
    selected_path = configured_model_manifest_path(manifest_path)
    if selected_path is None or not selected_path.is_file():
        return AIRelevanceModelManifest(
            model_id="ai-relevance-xgb-a2-v1",
            model_type="xgboost",
            model_path=FALLBACK_AI_RELEVANCE_MODEL_PATH,
            features=FALLBACK_TEXT_COLUMNS,
            calibrator="sigmoid-v1",
            calibrator_path=None,
            secondary_model_path=None,
            auto_ai_threshold=FALLBACK_AUTO_AI_THRESHOLD,
            auto_non_ai_threshold=FALLBACK_AUTO_NON_AI_THRESHOLD,
            training_dataset="human-reviewed-v4",
            created_at="2026-09-27",
            sha256=None,
        )

    payload = json.loads(selected_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"AI relevance model manifest must be a JSON object: {selected_path}")

    features = payload.get("features")
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        raise ValueError("AI relevance model manifest requires string list field: features")
    if not features:
        raise ValueError("AI relevance model manifest must configure at least one feature.")

    model_path = _resolve_project_path(payload.get("model_path") or payload.get("artifact_path"))
    if model_path is None:
        raise ValueError("AI relevance model manifest requires model_path.")

    return AIRelevanceModelManifest(
        model_id=str(payload.get("model_id") or selected_path.stem),
        model_type=str(payload.get("model_type") or "unknown"),
        model_path=model_path,
        features=tuple(features),
        calibrator=payload.get("calibrator"),
        calibrator_path=_resolve_project_path(payload.get("calibrator_path")),
        secondary_model_path=_resolve_project_path(payload.get("secondary_model_path")),
        auto_ai_threshold=float(payload.get("auto_ai_threshold", FALLBACK_AUTO_AI_THRESHOLD)),
        auto_non_ai_threshold=float(
            payload.get("auto_non_ai_threshold", FALLBACK_AUTO_NON_AI_THRESHOLD)
        ),
        training_dataset=payload.get("training_dataset"),
        created_at=payload.get("created_at"),
        sha256=payload.get("sha256"),
    )


DEFAULT_AI_RELEVANCE_MODEL_MANIFEST = load_ai_relevance_model_manifest()
DEFAULT_AI_RELEVANCE_MODEL_PATH = DEFAULT_AI_RELEVANCE_MODEL_MANIFEST.model_path
DEFAULT_TEXT_COLUMNS = DEFAULT_AI_RELEVANCE_MODEL_MANIFEST.features
DEFAULT_AUTO_AI_THRESHOLD = DEFAULT_AI_RELEVANCE_MODEL_MANIFEST.auto_ai_threshold
DEFAULT_AUTO_NON_AI_THRESHOLD = DEFAULT_AI_RELEVANCE_MODEL_MANIFEST.auto_non_ai_threshold
DEFAULT_CONFIDENCE_REVIEW_THRESHOLD = DEFAULT_AUTO_AI_THRESHOLD


def configured_model_path(value: str | Path | None = None) -> Path | None:
    raw_value = value or os.getenv("RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH")
    raw_value = raw_value or os.getenv("INCREMENTAL_MODEL")
    if raw_value in (None, ""):
        return load_ai_relevance_model_manifest().model_path
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    return _resolve_project_path(raw_value)


def configured_text_columns(value: tuple[str, ...] | list[str] | str | None = None) -> tuple[str, ...]:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_RELEVANCE_TEXT_COLUMNS")
    if raw_value in (None, ""):
        return load_ai_relevance_model_manifest().features
    if isinstance(raw_value, str):
        return tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return tuple(str(item).strip() for item in raw_value if str(item).strip())


def configured_auto_ai_threshold(value: float | str | None = None) -> float:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_AUTO_AI_THRESHOLD")
    if raw_value in (None, ""):
        return load_ai_relevance_model_manifest().auto_ai_threshold
    threshold = float(raw_value)
    if threshold < 0 or threshold > 1:
        raise ValueError("auto AI threshold must be between 0 and 1.")
    return threshold


def configured_auto_non_ai_threshold(value: float | str | None = None) -> float:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_AUTO_NON_AI_THRESHOLD")
    if raw_value in (None, ""):
        return load_ai_relevance_model_manifest().auto_non_ai_threshold
    threshold = float(raw_value)
    if threshold < 0 or threshold > 1:
        raise ValueError("auto non-AI threshold must be between 0 and 1.")
    return threshold


def configured_calibrator_path(value: str | Path | None = None) -> Path | None:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_CALIBRATOR_PATH")
    if raw_value in (None, ""):
        raw_value = load_ai_relevance_model_manifest().calibrator_path
    if raw_value in (None, ""):
        return None
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    return _resolve_project_path(raw_value)


def configured_secondary_model_path(value: str | Path | None = None) -> Path | None:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_SECONDARY_MODEL_PATH")
    if raw_value in (None, ""):
        raw_value = load_ai_relevance_model_manifest().secondary_model_path
    if raw_value in (None, ""):
        return None
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    return _resolve_project_path(raw_value)


def configured_confidence_review_threshold(value: float | str | None = None) -> float:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_CONFIDENCE_REVIEW_THRESHOLD")
    if raw_value in (None, ""):
        return configured_auto_ai_threshold()
    threshold = float(raw_value)
    if threshold < 0 or threshold > 1:
        raise ValueError("confidence review threshold must be between 0 and 1.")
    return threshold


def default_refresh_policy(
    *,
    model_path: str | Path | None = None,
    confidence_review_threshold: float | str | None = None,
    text_columns: tuple[str, ...] | None = None,
    db_labels: tuple[str, ...] = DEFAULT_DB_LABELS,
) -> PublicationRefreshPolicy:
    manifest = load_ai_relevance_model_manifest()
    return PublicationRefreshPolicy(
        model_path=configured_model_path(model_path),
        text_columns=configured_text_columns(text_columns),
        confidence_review_threshold=configured_confidence_review_threshold(
            confidence_review_threshold
        ),
        db_labels=db_labels,
        auto_non_ai_threshold=configured_auto_non_ai_threshold(),
        calibrator_path=configured_calibrator_path(),
        secondary_model_path=configured_secondary_model_path(),
        model_manifest_path=configured_model_manifest_path(),
        model_id=manifest.model_id,
    )
