"""Serving helpers for publication classifier model endpoints."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.api.core.constants import API_VERSION, DATASET_STAGE
from src.api.core.errors import APIError
from src.api.core.serializers import normalize_value
from src.modeling.artifacts import file_sha256
from src.modeling.inference import expected_model_sha256, load_manifest, load_verified_model
from src.modeling.training import (
    DEFAULT_LABEL_COLUMN,
    DEFAULT_MODEL_FAMILY,
    DEFAULT_TEXT_COLUMNS,
    default_manifest_output,
    default_model_output,
)


DEFAULT_MODEL_ID = "publication-classifier"
DEFAULT_MAX_BATCH_SIZE = 100

ModelLoader = Callable[[Path, Path | None, bool], tuple[Any, str]]


@dataclass(frozen=True)
class ModelServingConfig:
    """Configuration for serving a trained publication text classifier."""

    model_id: str = DEFAULT_MODEL_ID
    label_column: str = DEFAULT_LABEL_COLUMN
    model_family: str = DEFAULT_MODEL_FAMILY
    model_path: Path = default_model_output(DEFAULT_LABEL_COLUMN)
    model_manifest_path: Path | None = default_manifest_output(DEFAULT_LABEL_COLUMN)
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    verify_checksum: bool = True
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE


def model_serving_config_from_env(environ: Mapping[str, str] | None = None) -> ModelServingConfig:
    """Build serving config from environment variables and model defaults."""

    environ = os.environ if environ is None else environ
    label_column = environ.get("RESEARCHLANKA_MODEL_LABEL_COLUMN", DEFAULT_LABEL_COLUMN)
    model_family = environ.get("RESEARCHLANKA_MODEL_FAMILY", DEFAULT_MODEL_FAMILY)
    text_columns = tuple(
        split_csv(environ.get("RESEARCHLANKA_MODEL_TEXT_COLUMNS"))
        or DEFAULT_TEXT_COLUMNS
    )
    model_path = Path(
        environ.get(
            "RESEARCHLANKA_MODEL_PATH",
            str(default_model_output(label_column, model_family)),
        )
    )
    manifest_value = environ.get(
        "RESEARCHLANKA_MODEL_MANIFEST_PATH",
        str(default_manifest_output(label_column, model_family)),
    ).strip()
    model_manifest_path = None if manifest_value.casefold() in {"", "none", "null"} else Path(manifest_value)
    verify_checksum = parse_env_bool(
        environ.get("RESEARCHLANKA_MODEL_VERIFY_CHECKSUM"),
        default=True,
        field="RESEARCHLANKA_MODEL_VERIFY_CHECKSUM",
    )
    max_batch_size = parse_env_positive_int(
        environ.get("RESEARCHLANKA_MODEL_MAX_BATCH_SIZE"),
        default=DEFAULT_MAX_BATCH_SIZE,
        field="RESEARCHLANKA_MODEL_MAX_BATCH_SIZE",
    )
    return ModelServingConfig(
        label_column=label_column,
        model_family=model_family,
        model_path=model_path,
        model_manifest_path=model_manifest_path,
        text_columns=text_columns,
        verify_checksum=verify_checksum,
        max_batch_size=max_batch_size,
    )


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_env_bool(value: str | None, *, default: bool, field: str = "value") -> bool:
    if value is None or value == "":
        return default
    if value.casefold() in {"true", "t", "yes", "y", "1"}:
        return True
    if value.casefold() in {"false", "f", "no", "n", "0"}:
        return False
    raise APIError(
        "invalid_model_configuration",
        f"{field} must be a boolean value.",
        status=500,
        details={"field": field, "value": value},
    )


def parse_env_positive_int(value: str | None, *, default: int, field: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise APIError(
            "invalid_model_configuration",
            f"{field} must be an integer.",
            status=500,
            details={"field": field},
        ) from exc
    if parsed < 1:
        raise APIError(
            "invalid_model_configuration",
            f"{field} must be at least 1.",
            status=500,
            details={"field": field},
        )
    return parsed


def default_model_loader(
    model_path: Path,
    model_manifest_path: Path | None,
    verify_checksum: bool,
) -> tuple[Any, str]:
    return load_verified_model(
        model_path=model_path,
        model_manifest_path=model_manifest_path,
        verify_checksum=verify_checksum,
    )


class PublicationClassifierService:
    """Load, cache, and apply a publication text classifier."""

    def __init__(
        self,
        config: ModelServingConfig | None = None,
        *,
        model_loader: ModelLoader = default_model_loader,
    ) -> None:
        self.config = config or model_serving_config_from_env()
        validate_model_serving_config(self.config)
        self.model_loader = model_loader
        self._model: Any | None = None
        self._model_sha256: str | None = None

    def list_models(self) -> dict[str, Any]:
        return {"data": [self.model_summary()], "meta": self.response_meta()}

    def model_summary(self) -> dict[str, Any]:
        manifest, manifest_error = self._manifest_payload()
        model_exists = self.config.model_path.exists()
        manifest_exists = self.config.model_manifest_path is not None and self.config.model_manifest_path.exists()
        model_sha256 = file_sha256(self.config.model_path) if model_exists else None
        expected_sha256 = expected_model_sha256(manifest) if manifest else None

        status = "ready"
        if not model_exists:
            status = "missing_model"
        elif manifest_error:
            status = "invalid_manifest"
        elif self.config.verify_checksum and self.config.model_manifest_path is not None and not manifest_exists:
            status = "missing_manifest"
        elif self.config.verify_checksum and expected_sha256 and model_sha256 != expected_sha256:
            status = "checksum_mismatch"

        manifest_config = manifest.get("config", {}) if isinstance(manifest, Mapping) else {}
        manifest_result = manifest.get("result", {}) if isinstance(manifest, Mapping) else {}
        label_counts = manifest.get("label_counts", {}) if isinstance(manifest, Mapping) else {}

        return normalize_value(
            {
                "id": self.config.model_id,
                "task": "publication_text_classification",
                "status": status,
                "available": status == "ready",
                "model_family": manifest_config.get("model_family", self.config.model_family),
                "label_column": manifest_config.get("label_column", self.config.label_column),
                "text_columns": manifest_config.get("text_columns", list(self.config.text_columns)),
                "model_path": str(self.config.model_path),
                "model_sha256": model_sha256,
                "manifest_path": str(self.config.model_manifest_path) if self.config.model_manifest_path else None,
                "manifest_available": manifest_exists,
                "expected_model_sha256": expected_sha256,
                "verify_checksum": self.config.verify_checksum,
                "max_batch_size": self.config.max_batch_size,
                "labels": label_count_rows(label_counts),
                "training": {
                    key: manifest_result.get(key)
                    for key in [
                        "input_rows",
                        "usable_rows",
                        "train_rows",
                        "test_rows",
                        "class_count",
                        "accuracy",
                        "macro_f1",
                        "weighted_f1",
                    ]
                    if key in manifest_result
                },
                "error": manifest_error,
            }
        )

    def model_detail(self, model_id: str) -> dict[str, Any]:
        self._ensure_model_id(model_id)
        return {"data": self.model_summary(), "meta": self.response_meta()}

    def predict_one(self, model_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        self._ensure_model_id(model_id)
        predictions, model_sha256 = self._predict_records([record])
        return {"data": predictions[0], "meta": self.response_meta(model_sha256=model_sha256)}

    def predict_batch(self, model_id: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        self._ensure_model_id(model_id)
        if not records:
            raise APIError(
                "invalid_prediction_input",
                "At least one prediction record is required.",
                status=422,
            )
        if len(records) > self.config.max_batch_size:
            raise APIError(
                "batch_too_large",
                f"Batch prediction accepts at most {self.config.max_batch_size} records.",
                status=413,
                details={"max_batch_size": self.config.max_batch_size},
            )
        predictions, model_sha256 = self._predict_records(records)
        return {"data": predictions, "meta": self.response_meta(model_sha256=model_sha256)}

    def response_meta(self, *, model_sha256: str | None = None) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "api_version": API_VERSION,
            "dataset_stage": DATASET_STAGE,
            "model_id": self.config.model_id,
        }
        if model_sha256:
            meta["model_sha256"] = model_sha256
        return meta

    def _predict_records(self, records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        prepared = [
            prepare_prediction_record(record, self.config.text_columns, index=index)
            for index, record in enumerate(records)
        ]
        model, model_sha256 = self._load_model()
        texts = [item["text"] for item in prepared]
        try:
            labels = [str(label) for label in model.predict(texts)]
            probabilities = prediction_probabilities(model, texts)
        except Exception as exc:
            raise APIError(
                "model_prediction_failed",
                "Publication classifier prediction failed.",
                status=500,
                details={"error": str(exc)},
            ) from exc
        if len(labels) != len(prepared) or len(probabilities) != len(prepared):
            raise APIError(
                "model_prediction_failed",
                "Publication classifier returned an invalid prediction shape.",
                status=500,
                details={
                    "records": len(prepared),
                    "labels": len(labels),
                    "probabilities": len(probabilities),
                },
            )
        rows = []
        for item, label, probability in zip(prepared, labels, probabilities, strict=True):
            scores = probability.get("scores")
            rows.append(
                normalize_value(
                    {
                        "index": item["index"],
                        "predicted_label": label,
                        "confidence": probability.get("confidence"),
                        "scores": scores,
                        "text": item["text"],
                        "metadata": item["metadata"],
                    }
                )
            )
        return rows, model_sha256

    def _load_model(self) -> tuple[Any, str]:
        if self._model is not None and self._model_sha256 is not None:
            return self._model, self._model_sha256
        if not self.config.model_path.exists():
            raise APIError(
                "model_unavailable",
                "Publication classifier model artifact is not available.",
                status=503,
                details={"model_path": str(self.config.model_path)},
            )
        try:
            model, model_sha256 = self.model_loader(
                self.config.model_path,
                self.config.model_manifest_path,
                self.config.verify_checksum,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise APIError(
                "model_unavailable",
                "Publication classifier could not be loaded.",
                status=503,
                details={"error": str(exc)},
            ) from exc
        self._model = model
        self._model_sha256 = model_sha256
        return model, model_sha256

    def _manifest_payload(self) -> tuple[dict[str, Any], str | None]:
        if self.config.model_manifest_path is None or not self.config.model_manifest_path.exists():
            return {}, None
        try:
            return load_manifest(self.config.model_manifest_path), None
        except (OSError, ValueError) as exc:
            return {}, str(exc)

    def _ensure_model_id(self, model_id: str) -> None:
        if model_id != self.config.model_id:
            raise APIError(
                "not_found",
                "Model not found.",
                status=404,
                details={"model_id": model_id},
            )


def prepare_prediction_record(
    record: Mapping[str, Any],
    text_columns: Sequence[str],
    *,
    index: int,
) -> dict[str, Any]:
    text = prediction_text(record, text_columns)
    if not text:
        raise APIError(
            "invalid_prediction_input",
            "Prediction input requires text or at least one non-empty configured text field.",
            status=422,
            details={"index": index, "text_columns": list(text_columns)},
        )
    return {
        "index": index,
        "text": text,
        "metadata": prediction_metadata(record, text_columns),
    }


def prediction_text(record: Mapping[str, Any], text_columns: Sequence[str]) -> str:
    explicit_text = normalize_text_part(record.get("text"))
    if explicit_text:
        return explicit_text
    return normalize_text_part(
        " ".join(
            part
            for part in [normalize_text_part(record.get(column)) for column in text_columns]
            if part
        )
    )


def prediction_metadata(record: Mapping[str, Any], text_columns: Sequence[str]) -> dict[str, Any]:
    excluded = {"text", "metadata", *text_columns}
    metadata = {key: value for key, value in record.items() if key not in excluded}
    explicit_metadata = record.get("metadata")
    if isinstance(explicit_metadata, Mapping):
        metadata.update(explicit_metadata)
    return dict(metadata)


def normalize_text_part(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(normalize_text_part(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def prediction_probabilities(model: Any, texts: Sequence[str]) -> list[dict[str, Any]]:
    if not hasattr(model, "predict_proba"):
        return [{"confidence": None, "scores": None} for _ in texts]

    probabilities = model.predict_proba(texts)
    classes = model_classes(model)
    rows = []
    for probability_row in probabilities:
        probabilities_as_float = [float(probability) for probability in probability_row]
        confidence = max(probabilities_as_float) if probabilities_as_float else None
        scores = None
        if classes and len(classes) == len(probabilities_as_float):
            scores = {
                str(label): probability
                for label, probability in zip(classes, probabilities_as_float, strict=True)
            }
        rows.append({"confidence": confidence, "scores": scores})
    return rows


def model_classes(model: Any) -> list[Any] | None:
    classes = getattr(model, "classes_", None)
    if classes is None and hasattr(model, "named_steps"):
        classifier = getattr(model, "named_steps", {}).get("classifier")
        classes = getattr(classifier, "classes_", None)
    if classes is None:
        return None
    return list(classes)


def validate_model_serving_config(config: ModelServingConfig) -> None:
    if not config.model_id.strip():
        raise APIError(
            "invalid_model_configuration",
            "Model id must be a non-empty value.",
            status=500,
            details={"field": "model_id"},
        )
    if config.max_batch_size < 1:
        raise APIError(
            "invalid_model_configuration",
            "max_batch_size must be at least 1.",
            status=500,
            details={"field": "max_batch_size"},
        )
    if not config.text_columns:
        raise APIError(
            "invalid_model_configuration",
            "At least one configured text column is required.",
            status=500,
            details={"field": "text_columns"},
        )


def label_count_rows(label_counts: Any) -> list[dict[str, Any]]:
    if not isinstance(label_counts, Mapping):
        return []
    return [
        {"label": str(label), "count": int(count)}
        for label, count in label_counts.items()
    ]
