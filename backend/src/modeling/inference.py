"""Reusable inference pipeline for saved publication text classifiers."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import joblib
import pandas as pd

from src.modeling.artifacts import file_sha256, write_csv_artifact, write_json_artifact
from src.modeling.training import (
    DEFAULT_INPUT,
    DEFAULT_LABEL_COLUMN,
    DEFAULT_MODEL_FAMILY,
    DEFAULT_TEXT_COLUMNS,
    combined_text,
    default_manifest_output,
    default_model_output,
    parse_text_columns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA_COLUMNS = [
    "record_number",
    "publication_year",
    "title",
    "doi",
    "openalex_id",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
]


@dataclass(frozen=True)
class ModelInferenceConfig:
    """Configuration for applying a saved classifier to publication text."""

    input_path: Path = DEFAULT_INPUT
    model_path: Path = default_model_output(DEFAULT_LABEL_COLUMN)
    output_path: Path | None = None
    inference_manifest_path: Path | None = None
    model_manifest_path: Path | None = default_manifest_output(DEFAULT_LABEL_COLUMN)
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    metadata_columns: tuple[str, ...] = tuple(DEFAULT_METADATA_COLUMNS)
    max_rows: int | None = None
    verify_checksum: bool = True


@dataclass(frozen=True)
class InferenceResult:
    """Paths and summary stats produced by one inference run."""

    predictions_output: Path
    inference_manifest_output: Path
    model_path: Path
    input_rows: int
    predicted_rows: int
    skipped_rows: int
    model_sha256: str
    predictions_sha256: str


def default_inference_output(
    label_column: str = DEFAULT_LABEL_COLUMN,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    stem = default_model_output(label_column, model_family).stem
    return PROJECT_ROOT / "data" / "models" / f"{stem}_inference_predictions.csv"


def default_inference_manifest_output(
    label_column: str = DEFAULT_LABEL_COLUMN,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    stem = default_model_output(label_column, model_family).stem
    return PROJECT_ROOT / "data" / "models" / f"{stem}_inference_manifest.json"


def parse_columns(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("at least one column is required")
    return columns


def json_ready_dataclass(value: object) -> dict[str, object]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_model_sha256(manifest: Mapping[str, Any]) -> str | None:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, Mapping):
        model_artifact = artifacts.get("model")
        if isinstance(model_artifact, Mapping):
            sha256 = model_artifact.get("sha256")
            if isinstance(sha256, str) and sha256:
                return sha256

    result = manifest.get("result")
    if isinstance(result, Mapping):
        sha256 = result.get("model_sha256")
        if isinstance(sha256, str) and sha256:
            return sha256
    return None


def verify_model_checksum(model_path: Path, model_manifest_path: Path) -> str:
    manifest = load_manifest(model_manifest_path)
    expected_sha256 = expected_model_sha256(manifest)
    if not expected_sha256:
        raise ValueError(f"No model SHA-256 found in manifest: {model_manifest_path}")

    actual_sha256 = file_sha256(model_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "Saved model checksum does not match manifest. "
            f"model={model_path} expected={expected_sha256} actual={actual_sha256}"
        )
    return actual_sha256


def load_verified_model(
    *,
    model_path: Path,
    model_manifest_path: Path | None,
    verify_checksum: bool,
) -> tuple[Any, str]:
    if verify_checksum and model_manifest_path is not None:
        model_sha256 = verify_model_checksum(model_path, model_manifest_path)
    else:
        model_sha256 = file_sha256(model_path)

    return joblib.load(model_path), model_sha256


def existing_columns(input_path: Path) -> list[str]:
    return list(pd.read_csv(input_path, nrows=0).columns)


def selected_input_columns(
    *,
    input_path: Path,
    text_columns: Iterable[str],
    metadata_columns: Iterable[str],
) -> tuple[list[str], list[str]]:
    available_columns = existing_columns(input_path)
    missing_text_columns = [column for column in text_columns if column not in available_columns]
    if missing_text_columns:
        raise ValueError(
            "Input CSV is missing required text columns: "
            + ", ".join(missing_text_columns)
        )

    present_metadata_columns = [
        column
        for column in metadata_columns
        if column in available_columns
    ]
    usecols = list(dict.fromkeys([*text_columns, *present_metadata_columns]))
    return usecols, present_metadata_columns


def load_inference_frame(
    input_path: Path,
    *,
    text_columns: list[str] | tuple[str, ...],
    metadata_columns: list[str] | tuple[str, ...],
    max_rows: int | None,
) -> tuple[pd.DataFrame, int, list[str]]:
    usecols, present_metadata_columns = selected_input_columns(
        input_path=input_path,
        text_columns=text_columns,
        metadata_columns=metadata_columns,
    )
    frame = pd.read_csv(
        input_path,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        nrows=max_rows,
    )
    input_rows = len(frame)
    inference_frame = frame[present_metadata_columns].copy()
    inference_frame.insert(0, "source_row", frame.index)
    inference_frame["text"] = combined_text(frame, text_columns)
    inference_frame = inference_frame[inference_frame["text"] != ""]
    return inference_frame, input_rows, present_metadata_columns


def confidence_scores(model: Any, text: pd.Series) -> list[float | None]:
    if len(text) == 0:
        return []
    if not hasattr(model, "predict_proba"):
        return [None for _ in range(len(text))]

    probabilities = model.predict_proba(text)
    return [float(row.max()) for row in probabilities]


def prediction_output_rows(
    *,
    inference_frame: pd.DataFrame,
    labels: Iterable[str],
    confidences: Iterable[float | None],
    metadata_columns: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (_, record), label, confidence in zip(
        inference_frame.iterrows(),
        labels,
        confidences,
        strict=True,
    ):
        row: dict[str, Any] = {
            "source_row": record["source_row"],
            "predicted_label": label,
            "confidence": "" if confidence is None else f"{confidence:.6f}",
        }
        for column in metadata_columns:
            row[column] = record[column]
        row["text"] = record["text"]
        rows.append(row)
    return rows


def prediction_fieldnames(metadata_columns: list[str]) -> list[str]:
    return [
        "source_row",
        "predicted_label",
        "confidence",
        *metadata_columns,
        "text",
    ]


def resolved_config(config: ModelInferenceConfig) -> ModelInferenceConfig:
    return ModelInferenceConfig(
        input_path=config.input_path,
        model_path=config.model_path,
        output_path=config.output_path or default_inference_output(),
        inference_manifest_path=config.inference_manifest_path
        or default_inference_manifest_output(),
        model_manifest_path=config.model_manifest_path,
        text_columns=config.text_columns,
        metadata_columns=config.metadata_columns,
        max_rows=config.max_rows,
        verify_checksum=config.verify_checksum,
    )


def run_model_inference(config: ModelInferenceConfig) -> InferenceResult:
    """Load a saved model, predict labels for publication text, and save outputs."""

    config = resolved_config(config)
    assert config.output_path is not None
    assert config.inference_manifest_path is not None

    model, model_sha256 = load_verified_model(
        model_path=config.model_path,
        model_manifest_path=config.model_manifest_path,
        verify_checksum=config.verify_checksum,
    )
    inference_frame, input_rows, present_metadata_columns = load_inference_frame(
        config.input_path,
        text_columns=config.text_columns,
        metadata_columns=config.metadata_columns,
        max_rows=config.max_rows,
    )

    labels = model.predict(inference_frame["text"]) if not inference_frame.empty else []
    confidences = confidence_scores(model, inference_frame["text"])
    rows = prediction_output_rows(
        inference_frame=inference_frame,
        labels=labels,
        confidences=confidences,
        metadata_columns=present_metadata_columns,
    )
    saved_predictions = write_csv_artifact(
        config.output_path,
        fieldnames=prediction_fieldnames(present_metadata_columns),
        rows=rows,
    )

    result = InferenceResult(
        predictions_output=config.output_path,
        inference_manifest_output=config.inference_manifest_path,
        model_path=config.model_path,
        input_rows=input_rows,
        predicted_rows=len(rows),
        skipped_rows=input_rows - len(rows),
        model_sha256=model_sha256,
        predictions_sha256=saved_predictions.sha256,
    )
    manifest = {
        "artifact_schema_version": 1,
        "config": json_ready_dataclass(config),
        "result": json_ready_dataclass(result),
        "artifacts": {
            "model": {
                "path": str(config.model_path),
                "sha256": model_sha256,
            },
            "predictions": saved_predictions.as_manifest_dict(),
            "inference_manifest": {"path": str(config.inference_manifest_path)},
        },
    }
    write_json_artifact(config.inference_manifest_path, manifest)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run inference with a saved publication text classifier and write "
            "prediction CSV plus an audit manifest."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input publication CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=default_model_output(DEFAULT_LABEL_COLUMN),
        help="Saved .joblib model path. Default: data/models/logistic_regression_primary_domain.joblib",
    )
    parser.add_argument(
        "--model-manifest",
        type=Path,
        default=default_manifest_output(DEFAULT_LABEL_COLUMN),
        help="Training manifest used to verify the model checksum.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Prediction CSV output. Default: data/models/logistic_regression_primary_domain_inference_predictions.csv",
    )
    parser.add_argument(
        "--inference-manifest",
        type=Path,
        default=None,
        help="Inference manifest JSON output. Default: data/models/logistic_regression_primary_domain_inference_manifest.json",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns to combine. Default: title,abstract,keywords",
    )
    parser.add_argument(
        "--metadata-columns",
        type=parse_columns,
        default=DEFAULT_METADATA_COLUMNS,
        help="Comma-separated metadata columns to copy when present.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional row limit for quick inference checks. Default: use all rows.",
    )
    parser.add_argument(
        "--skip-checksum",
        action="store_true",
        help="Load the model without verifying it against a training manifest.",
    )
    return parser.parse_args()


def result_summary(result: InferenceResult) -> str:
    return "\n".join(
        [
            f"Ran inference on {result.predicted_rows:,} rows.",
            f"Skipped rows: {result.skipped_rows:,}",
            f"Model: {result.model_path}",
            f"Model SHA-256: {result.model_sha256}",
            f"Predictions: {result.predictions_output}",
            f"Predictions SHA-256: {result.predictions_sha256}",
            f"Manifest: {result.inference_manifest_output}",
        ]
    )


def main() -> None:
    args = parse_args()
    result = run_model_inference(
        ModelInferenceConfig(
            input_path=args.input,
            model_path=args.model,
            output_path=args.output,
            inference_manifest_path=args.inference_manifest,
            model_manifest_path=args.model_manifest,
            text_columns=tuple(args.text_columns),
            metadata_columns=tuple(args.metadata_columns),
            max_rows=args.max_rows,
            verify_checksum=not args.skip_checksum,
        )
    )
    print(result_summary(result))


if __name__ == "__main__":
    main()
