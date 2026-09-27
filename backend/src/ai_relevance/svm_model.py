"""Train and apply a local AI relevance classifier from LLM-labelled records."""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GridSearchCV, train_test_split

from src.ai_relevance.calibration import (
    CALIBRATION_METHODS,
    calibration_metrics,
    choose_probability_thresholds,
    fit_probability_calibrator,
    reliability_table,
    write_calibration_curve_png,
)
from src.modeling.artifacts import (
    describe_artifact,
    dump_joblib_artifact,
    file_sha256,
    save_model_artifacts,
    write_csv_artifact,
    write_json_artifact,
)
from src.modeling.linear_svm_training import (
    build_pipeline,
    combined_text,
    parse_c_values,
    parse_class_weight,
    parse_document_frequency,
    parse_text_columns,
    prediction_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LABELLED_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_5000_predictions_openrouter_gemini_3_8_flash.csv"
)
DEFAULT_CORPUS_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models" / "ai_relevance"
DEFAULT_MODEL_OUTPUT = DEFAULT_MODEL_DIR / "model.joblib"
DEFAULT_METRICS_OUTPUT = DEFAULT_MODEL_DIR / "ai_relevance_linear_svm_metrics.txt"
DEFAULT_LABEL_COUNTS_OUTPUT = DEFAULT_MODEL_DIR / "ai_relevance_linear_svm_labels.csv"
DEFAULT_TEST_PREDICTIONS_OUTPUT = (
    DEFAULT_MODEL_DIR / "ai_relevance_linear_svm_test_predictions.csv"
)
DEFAULT_MANIFEST_OUTPUT = DEFAULT_MODEL_DIR / "model_manifest.json"
DEFAULT_CALIBRATOR_OUTPUT = DEFAULT_MODEL_DIR / "calibrator.joblib"
DEFAULT_CALIBRATION_REPORT_OUTPUT = DEFAULT_MODEL_DIR / "calibration_report.json"
DEFAULT_CALIBRATION_CURVE_OUTPUT = DEFAULT_MODEL_DIR / "calibration_curve.png"
DEFAULT_REST_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_relevance_svm_rest_predictions.csv"
)
DEFAULT_REST_MANIFEST_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_relevance_svm_rest_predictions_manifest.json"
)
DEFAULT_TEXT_COLUMNS = (
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
)
DEFAULT_METADATA_COLUMNS = (
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "openalex_id",
    "doi",
    "title",
    "publication_date",
    "publication_year",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
)
DEFAULT_LABELS = ("AI", "NON_AI")
PUBLICATION_ID_COLUMNS = (
    "record_number",
    "publication_id",
    "openalex_id",
    "doi",
    "source_record_id",
)


@dataclass(frozen=True)
class AIRelevanceSVMTrainingConfig:
    input_path: Path = DEFAULT_LABELLED_INPUT
    model_output: Path = DEFAULT_MODEL_OUTPUT
    metrics_output: Path = DEFAULT_METRICS_OUTPUT
    label_counts_output: Path = DEFAULT_LABEL_COUNTS_OUTPUT
    predictions_output: Path = DEFAULT_TEST_PREDICTIONS_OUTPUT
    manifest_output: Path = DEFAULT_MANIFEST_OUTPUT
    calibrator_output: Path = DEFAULT_CALIBRATOR_OUTPUT
    calibration_report_output: Path = DEFAULT_CALIBRATION_REPORT_OUTPUT
    calibration_curve_output: Path = DEFAULT_CALIBRATION_CURVE_OUTPUT
    text_columns: tuple[str, ...] = DEFAULT_TEXT_COLUMNS
    label_column: str = "ai_llm_label"
    status_column: str = "ai_llm_status"
    success_status: str = "success"
    labels: tuple[str, ...] = DEFAULT_LABELS
    test_size: float = 0.2
    random_state: int = 42
    max_rows: int | None = None
    min_class_count: int = 20
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 3
    c_values: tuple[float, ...] = (0.1, 1.0, 10.0)
    class_weight: str | None = "balanced"
    max_iter: int = 5000
    cv_folds: int = 3
    scoring: str = "f1_macro"
    calibration_size: float = 0.2
    calibration_bins: int = 10
    calibration_methods: tuple[str, ...] = CALIBRATION_METHODS
    target_auto_ai_precision: float = 0.90
    target_auto_non_ai_precision: float = 0.90


@dataclass(frozen=True)
class AIRelevanceSVMTrainingResult:
    model_output: Path
    metrics_output: Path
    label_counts_output: Path
    predictions_output: Path
    manifest_output: Path
    calibrator_output: Path
    calibration_report_output: Path
    calibration_curve_output: Path
    input_rows: int
    usable_rows: int
    train_rows: int
    test_rows: int
    calibration_rows: int
    class_count: int
    best_c: float
    best_cv_score: float
    accuracy: float
    macro_f1: float
    weighted_f1: float
    selected_calibrator: str = ""
    calibration_brier_score: float = 0.0
    calibration_ece: float = 0.0
    auto_ai_threshold: float = 0.85
    auto_non_ai_threshold: float = 0.4
    model_sha256: str = ""


@dataclass(frozen=True)
class AIRelevanceSVMPredictionConfig:
    input_path: Path = DEFAULT_CORPUS_INPUT
    labelled_input_path: Path = DEFAULT_LABELLED_INPUT
    model_path: Path = DEFAULT_MODEL_OUTPUT
    model_manifest_path: Path = DEFAULT_MANIFEST_OUTPUT
    output_path: Path = DEFAULT_REST_OUTPUT
    manifest_output: Path = DEFAULT_REST_MANIFEST_OUTPUT
    text_columns: tuple[str, ...] = DEFAULT_TEXT_COLUMNS
    metadata_columns: tuple[str, ...] = DEFAULT_METADATA_COLUMNS
    max_rows: int | None = None
    exclude_labelled: bool = True
    verify_checksum: bool = True


@dataclass(frozen=True)
class AIRelevanceSVMPredictionResult:
    output_path: Path
    manifest_output: Path
    model_path: Path
    input_rows: int
    excluded_rows: int
    skipped_blank_text_rows: int
    predicted_rows: int
    ai: int
    non_ai: int
    model_sha256: str
    predictions_sha256: str


def json_ready_dataclass(value: object) -> dict[str, object]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def _binary_ai_labels(labels: Iterable[str]) -> list[int]:
    binary: list[int] = []
    for label in labels:
        normalized = str(label).strip().casefold().replace("_", "-").replace(" ", "-")
        if normalized == "ai":
            binary.append(1)
        elif normalized in {"non-ai", "nonai"}:
            binary.append(0)
        else:
            raise ValueError(f"Unsupported binary AI relevance label: {label}")
    return binary


def _ai_probability_scores(model: Any, text: pd.Series) -> list[float]:
    if text.empty:
        return []
    classes = [str(label).strip().casefold().replace("_", "-") for label in model.classes_]
    if "ai" not in classes:
        raise ValueError("AI relevance model does not expose an AI class.")
    ai_index = classes.index("ai")
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(text)
        return [float(row[ai_index]) for row in probabilities]
    if hasattr(model, "decision_function"):
        margins = model.decision_function(text)
        if len(classes) != 2:
            raise ValueError("Decision-margin calibration requires a binary model.")
        scores_for_second_class = [
            1.0 / (1.0 + math.exp(-float(margin))) for margin in margins
        ]
        if ai_index == 1:
            return scores_for_second_class
        return [1.0 - score for score in scores_for_second_class]
    raise ValueError("Model must expose predict_proba or decision_function for calibration.")


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def _read_existing_columns(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def _selected_columns(
    path: Path,
    columns: Iterable[str],
    *,
    optional_columns: Iterable[str] = (),
) -> list[str]:
    existing = _read_existing_columns(path)
    missing = [column for column in columns if column not in existing]
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {', '.join(missing)}")
    selected = [*columns, *(column for column in optional_columns if column in existing)]
    return list(dict.fromkeys(selected))


def _clean_identifier(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none", "null"}:
        return ""
    return text


def publication_identifier(record: Mapping[str, Any], fallback: int | str) -> str:
    for column in PUBLICATION_ID_COLUMNS:
        if column in record:
            value = _clean_identifier(record[column])
            if value:
                return value
    return f"row-{fallback}"


def load_ai_training_frame(
    config: AIRelevanceSVMTrainingConfig,
) -> tuple[pd.DataFrame, int, pd.Series]:
    usecols = _selected_columns(
        config.input_path,
        [config.label_column, config.status_column, *config.text_columns],
        optional_columns=("publication_id", "openalex_id", "doi", "source_record_id"),
    )
    frame = pd.read_csv(
        config.input_path,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        nrows=config.max_rows,
    )
    input_rows = len(frame)
    if "publication_id" not in frame.columns:
        frame["publication_id"] = [
            publication_identifier(record, index) for index, record in frame.iterrows()
        ]

    label_set = set(config.labels)
    training_frame = pd.DataFrame(
        {
            "publication_id": frame["publication_id"].astype(str),
            "text": combined_text(frame, config.text_columns),
            "label": frame[config.label_column].astype(str).str.strip(),
            "status": frame[config.status_column].astype(str).str.strip(),
        },
        index=frame.index,
    )
    training_frame.index.name = "source_row"
    training_frame = training_frame[
        (training_frame["status"] == config.success_status)
        & training_frame["label"].isin(label_set)
        & (training_frame["text"] != "")
    ]

    label_counts = training_frame["label"].value_counts()
    eligible_labels = label_counts[label_counts >= config.min_class_count].index
    training_frame = training_frame[training_frame["label"].isin(eligible_labels)]
    label_counts = training_frame["label"].value_counts()

    if training_frame.empty:
        raise ValueError("No usable AI relevance training rows found.")
    if len(label_counts) < 2:
        raise ValueError("AI relevance SVM needs at least two labels.")
    return training_frame, input_rows, label_counts


def render_training_metrics(
    *,
    config: AIRelevanceSVMTrainingConfig,
    input_rows: int,
    usable_rows: int,
    train_rows: int,
    test_rows: int,
    calibration_rows: int,
    label_counts: pd.Series,
    best_c: float,
    best_cv_score: float,
    accuracy: float,
    macro_f1: float,
    weighted_f1: float,
    selected_calibrator: str,
    calibration_brier_score: float,
    calibration_ece: float,
    auto_ai_threshold: float,
    auto_non_ai_threshold: float,
    report: str,
) -> str:
    lines = [
        "AI relevance Linear SVM classifier",
        "",
        f"input_csv: {config.input_path}",
        f"label_column: {config.label_column}",
        f"status_column: {config.status_column}",
        f"labels_used: {', '.join(config.labels)}",
        f"text_columns: {', '.join(config.text_columns)}",
        f"input_rows: {input_rows}",
        f"usable_rows: {usable_rows}",
        f"train_rows: {train_rows}",
        f"test_rows: {test_rows}",
        f"calibration_rows: {calibration_rows}",
        f"class_count: {len(label_counts)}",
        f"best_C: {best_c}",
        f"cv_macro_f1: {best_cv_score:.4f}",
        f"accuracy: {accuracy:.4f}",
        f"macro_f1: {macro_f1:.4f}",
        f"weighted_f1: {weighted_f1:.4f}",
        f"selected_calibrator: {selected_calibrator}",
        f"calibration_brier_score: {calibration_brier_score:.6f}",
        f"calibration_ece: {calibration_ece:.6f}",
        f"auto_ai_threshold: {auto_ai_threshold:.6f}",
        f"auto_non_ai_threshold: {auto_non_ai_threshold:.6f}",
        "",
        "Class distribution:",
    ]
    lines.extend(f"{label}: {count}" for label, count in label_counts.items())
    lines.extend(["", "Classification report:", report])
    return "\n".join(lines).rstrip() + "\n"


def train_ai_relevance_svm(
    config: AIRelevanceSVMTrainingConfig = AIRelevanceSVMTrainingConfig(),
) -> AIRelevanceSVMTrainingResult:
    training_frame, input_rows, label_counts = load_ai_training_frame(config)
    min_count = int(label_counts.min())
    cv_folds = min(config.cv_folds, min_count)
    if cv_folds < 2:
        raise ValueError("Each class needs at least two rows for cross-validation.")
    if not 0.0 < config.test_size < 1.0:
        raise ValueError("test_size must be between 0 and 1.")
    if not 0.0 < config.calibration_size < 1.0:
        raise ValueError("calibration_size must be between 0 and 1.")
    unknown_methods = [
        method for method in config.calibration_methods if method not in CALIBRATION_METHODS
    ]
    if unknown_methods:
        raise ValueError(f"Unsupported calibration methods: {', '.join(unknown_methods)}")

    modeling_frame, calibration_frame = train_test_split(
        training_frame,
        test_size=config.calibration_size,
        random_state=config.random_state,
        stratify=training_frame["label"],
    )
    if calibration_frame["label"].nunique() < 2:
        raise ValueError("Calibration split must contain both AI and NON_AI labels.")

    train_text, test_text, train_labels, test_labels = train_test_split(
        modeling_frame["text"],
        modeling_frame["label"],
        test_size=config.test_size,
        random_state=config.random_state,
        stratify=modeling_frame["label"],
    )
    cv_folds = min(config.cv_folds, int(train_labels.value_counts().min()))
    if cv_folds < 2:
        raise ValueError("Each train class needs at least two rows for cross-validation.")
    grid_pipeline = build_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        random_state=config.random_state,
    )
    grid = GridSearchCV(
        estimator=grid_pipeline,
        param_grid={"svm__C": list(config.c_values)},
        cv=cv_folds,
        scoring=config.scoring,
        n_jobs=-1,
    )
    grid.fit(train_text, train_labels)
    best_c = float(grid.best_params_["svm__C"])
    test_predictions = grid.best_estimator_.predict(test_text)
    accuracy = accuracy_score(test_labels, test_predictions)
    macro_f1 = f1_score(test_labels, test_predictions, average="macro", zero_division=0)
    weighted_f1 = f1_score(
        test_labels, test_predictions, average="weighted", zero_division=0
    )
    report = classification_report(test_labels, test_predictions, zero_division=0)

    model = build_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        random_state=config.random_state,
        c_value=best_c,
    )
    model.fit(modeling_frame["text"], modeling_frame["label"])

    calibration_labels = _binary_ai_labels(calibration_frame["label"])
    calibration_raw_scores = _ai_probability_scores(model, calibration_frame["text"])
    method_reports: dict[str, Any] = {}
    calibrators: dict[str, Any] = {}
    for method in config.calibration_methods:
        calibrator = fit_probability_calibrator(
            method=method,
            raw_scores=calibration_raw_scores,
            labels=calibration_labels,
            source_model_path=config.model_output,
            label_column=config.label_column,
        )
        calibrated_scores = calibrator.predict(calibration_raw_scores)
        metrics = calibration_metrics(
            scores=calibrated_scores,
            labels=calibration_labels,
            bins=config.calibration_bins,
        )
        method_reports[method] = {
            **metrics,
            "reliability": reliability_table(
                scores=calibrated_scores,
                labels=calibration_labels,
                bins=config.calibration_bins,
            ).to_dict("records"),
        }
        calibrators[method] = calibrator

    selected_method = min(
        method_reports,
        key=lambda method: (
            method_reports[method]["brier_score"],
            method_reports[method]["expected_calibration_error"],
            0 if method == "sigmoid" else 1,
        ),
    )
    selected_calibrator = calibrators[selected_method]
    selected_scores = selected_calibrator.predict(calibration_raw_scores)
    selected_reliability = reliability_table(
        scores=selected_scores,
        labels=calibration_labels,
        bins=config.calibration_bins,
    )
    thresholds = choose_probability_thresholds(
        scores=selected_scores,
        labels=calibration_labels,
        target_auto_precision=config.target_auto_ai_precision,
        target_auto_non_ai_precision=config.target_auto_non_ai_precision,
    )
    auto_ai_threshold = float(thresholds["auto_ai_threshold"])
    auto_non_ai_threshold = float(thresholds["auto_non_ai_threshold"])
    calibration_report = {
        "calibration_schema_version": 1,
        "source": {
            "input_path": str(config.input_path),
            "label_column": config.label_column,
            "text_columns": list(config.text_columns),
            "calibration_rows": len(calibration_frame),
            "calibration_split": "stratified holdout excluded from base model fitting",
        },
        "raw_scores": calibration_metrics(
            scores=calibration_raw_scores,
            labels=calibration_labels,
            bins=config.calibration_bins,
        ),
        "methods": method_reports,
        "selected_calibrator": selected_method,
        "selection_rule": "lowest Brier score, then lowest ECE, sigmoid tie-break",
        "thresholds": {
            **thresholds,
            "labels": {
                "score_gte_auto_ai_threshold": "AUTO_AI",
                "between_thresholds": "REVIEW",
                "score_lte_auto_non_ai_threshold": "AUTO_NON_AI",
            },
        },
    }
    saved_calibrator = dump_joblib_artifact(config.calibrator_output, selected_calibrator)
    saved_report = write_json_artifact(config.calibration_report_output, calibration_report)
    write_calibration_curve_png(
        config.calibration_curve_output,
        reliability=selected_reliability,
    )
    saved_curve = describe_artifact(config.calibration_curve_output)

    metrics_text = render_training_metrics(
        config=config,
        input_rows=input_rows,
        usable_rows=len(training_frame),
        train_rows=len(train_text),
        test_rows=len(test_text),
        calibration_rows=len(calibration_frame),
        label_counts=label_counts,
        best_c=best_c,
        best_cv_score=float(grid.best_score_),
        accuracy=float(accuracy),
        macro_f1=float(macro_f1),
        weighted_f1=float(weighted_f1),
        selected_calibrator=selected_method,
        calibration_brier_score=float(method_reports[selected_method]["brier_score"]),
        calibration_ece=float(
            method_reports[selected_method]["expected_calibration_error"]
        ),
        auto_ai_threshold=auto_ai_threshold,
        auto_non_ai_threshold=auto_non_ai_threshold,
        report=report,
    )
    result = AIRelevanceSVMTrainingResult(
        model_output=config.model_output,
        metrics_output=config.metrics_output,
        label_counts_output=config.label_counts_output,
        predictions_output=config.predictions_output,
        manifest_output=config.manifest_output,
        calibrator_output=config.calibrator_output,
        calibration_report_output=config.calibration_report_output,
        calibration_curve_output=config.calibration_curve_output,
        input_rows=input_rows,
        usable_rows=len(training_frame),
        train_rows=len(train_text),
        test_rows=len(test_text),
        calibration_rows=len(calibration_frame),
        class_count=len(label_counts),
        best_c=best_c,
        best_cv_score=float(grid.best_score_),
        accuracy=float(accuracy),
        macro_f1=float(macro_f1),
        weighted_f1=float(weighted_f1),
        selected_calibrator=selected_method,
        calibration_brier_score=float(method_reports[selected_method]["brier_score"]),
        calibration_ece=float(
            method_reports[selected_method]["expected_calibration_error"]
        ),
        auto_ai_threshold=auto_ai_threshold,
        auto_non_ai_threshold=auto_non_ai_threshold,
    )
    saved = save_model_artifacts(
        model=model,
        model_output=config.model_output,
        metrics_text=metrics_text,
        metrics_output=config.metrics_output,
        label_counts=label_counts,
        label_counts_output=config.label_counts_output,
        predictions=prediction_rows(
            test_text=test_text,
            test_labels=test_labels,
            predictions=test_predictions,
        ),
        predictions_output=config.predictions_output,
        manifest_output=config.manifest_output,
        manifest_config=json_ready_dataclass(config),
        manifest_result=json_ready_dataclass(result),
        extra_artifacts={
            "calibrator": saved_calibrator,
            "calibration_report": saved_report,
            "calibration_curve": saved_curve,
        },
    )
    created_at = datetime.now(UTC).isoformat()
    final_result = AIRelevanceSVMTrainingResult(
        **{**asdict(result), "model_sha256": saved.model.sha256}
    )
    manifest_payload = {
        "artifact_schema_version": 1,
        "model_id": config.model_output.stem,
        "model_type": "linear_svm",
        "model_path": _relative_to_project(config.model_output),
        "features": list(config.text_columns),
        "calibrator": f"{selected_method}-v1",
        "calibrator_path": _relative_to_project(config.calibrator_output),
        "auto_ai_threshold": auto_ai_threshold,
        "auto_non_ai_threshold": auto_non_ai_threshold,
        "training_dataset": str(config.input_path),
        "created_at": created_at,
        "sha256": saved.model.sha256,
        "config": json_ready_dataclass(config),
        "result": json_ready_dataclass(final_result),
        "calibration": {
            "selected_calibrator": selected_method,
            "brier_score": method_reports[selected_method]["brier_score"],
            "expected_calibration_error": method_reports[selected_method][
                "expected_calibration_error"
            ],
            "report_path": _relative_to_project(config.calibration_report_output),
            "curve_path": _relative_to_project(config.calibration_curve_output),
        },
        "artifacts": {
            "model": saved.model.as_manifest_dict(),
            "metrics": saved.metrics.as_manifest_dict(),
            "label_counts": saved.label_counts.as_manifest_dict(),
            "predictions": saved.predictions.as_manifest_dict(),
            "calibrator": saved_calibrator.as_manifest_dict(),
            "calibration_report": saved_report.as_manifest_dict(),
            "calibration_curve": saved_curve.as_manifest_dict(),
            "manifest": {"path": str(config.manifest_output)},
        },
    }
    write_json_artifact(config.manifest_output, manifest_payload)
    return final_result


def _load_manifest_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    import json

    manifest = json.loads(path.read_text(encoding="utf-8"))
    model = manifest.get("artifacts", {}).get("model", {})
    sha256 = model.get("sha256")
    return sha256 if isinstance(sha256, str) else None


def _load_model(config: AIRelevanceSVMPredictionConfig) -> tuple[Any, str]:
    actual_sha256 = file_sha256(config.model_path)
    expected_sha256 = _load_manifest_sha256(config.model_manifest_path)
    if config.verify_checksum and expected_sha256 and actual_sha256 != expected_sha256:
        raise ValueError(
            "Saved model checksum does not match manifest. "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    return joblib.load(config.model_path), actual_sha256


def labelled_publication_ids(path: Path) -> set[str]:
    usecols = _selected_columns(
        path,
        [],
        optional_columns=("publication_id", "openalex_id", "doi", "source_record_id"),
    )
    frame = pd.read_csv(path, usecols=usecols, dtype=str, keep_default_na=False)
    if "publication_id" in frame.columns:
        return set(frame["publication_id"].astype(str))
    return {
        publication_identifier(record, index) for index, record in frame.iterrows()
    }


def _decision_margins(model: Any, text: pd.Series) -> list[float]:
    if len(text) == 0 or not hasattr(model, "decision_function"):
        return [0.0 for _ in range(len(text))]
    raw = model.decision_function(text)
    if getattr(raw, "ndim", 1) == 1:
        return [float(value) for value in raw]
    return [float(max(row, key=abs)) for row in raw]


def _binary_confidence_from_margin(margin: float) -> float:
    return 1.0 / (1.0 + math.exp(-abs(margin)))


def _prediction_rows(
    *,
    frame: pd.DataFrame,
    labels: Iterable[str],
    margins: Iterable[float],
    metadata_columns: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (_, record), label, margin in zip(
        frame.iterrows(), labels, margins, strict=True
    ):
        row: dict[str, Any] = {
            "source_row": int(record["source_row"]),
            "publication_id": record["publication_id"],
            "ai_svm_label": label,
            "ai_svm_confidence": f"{_binary_confidence_from_margin(margin):.6f}",
            "ai_svm_margin": f"{margin:.6f}",
        }
        for column in metadata_columns:
            row[column] = record[column]
        row["text"] = record["text"]
        rows.append(row)
    return rows


def predict_rest_with_ai_relevance_svm(
    config: AIRelevanceSVMPredictionConfig = AIRelevanceSVMPredictionConfig(),
) -> AIRelevanceSVMPredictionResult:
    model, model_sha256 = _load_model(config)
    existing = _read_existing_columns(config.input_path)
    missing_text = [column for column in config.text_columns if column not in existing]
    if missing_text:
        raise ValueError(f"Input CSV is missing text columns: {', '.join(missing_text)}")
    metadata_columns = [
        column for column in config.metadata_columns if column in existing
    ]
    id_columns = [
        column
        for column in ("publication_id", "record_number", "openalex_id", "doi", "source_record_id")
        if column in existing
    ]
    usecols = list(dict.fromkeys([*config.text_columns, *metadata_columns, *id_columns]))
    corpus = pd.read_csv(
        config.input_path,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        nrows=config.max_rows,
    )
    input_rows = len(corpus)
    corpus["source_row"] = corpus.index
    corpus["publication_id"] = [
        publication_identifier(record, index) for index, record in corpus.iterrows()
    ]
    excluded_ids = (
        labelled_publication_ids(config.labelled_input_path)
        if config.exclude_labelled
        else set()
    )
    prediction_frame = corpus[~corpus["publication_id"].isin(excluded_ids)].copy()
    excluded_rows = input_rows - len(prediction_frame)
    prediction_frame["text"] = combined_text(prediction_frame, config.text_columns)
    before_blank_filter = len(prediction_frame)
    prediction_frame = prediction_frame[prediction_frame["text"] != ""]
    skipped_blank_text_rows = before_blank_filter - len(prediction_frame)

    labels = model.predict(prediction_frame["text"]) if not prediction_frame.empty else []
    margins = _decision_margins(model, prediction_frame["text"])
    rows = _prediction_rows(
        frame=prediction_frame,
        labels=labels,
        margins=margins,
        metadata_columns=metadata_columns,
    )
    fieldnames = [
        "source_row",
        "publication_id",
        "ai_svm_label",
        "ai_svm_confidence",
        "ai_svm_margin",
        *metadata_columns,
        "text",
    ]
    predictions_artifact = write_csv_artifact(
        config.output_path,
        fieldnames=fieldnames,
        rows=rows,
    )
    label_counts = pd.Series([row["ai_svm_label"] for row in rows]).value_counts()
    result = AIRelevanceSVMPredictionResult(
        output_path=config.output_path,
        manifest_output=config.manifest_output,
        model_path=config.model_path,
        input_rows=input_rows,
        excluded_rows=excluded_rows,
        skipped_blank_text_rows=skipped_blank_text_rows,
        predicted_rows=len(rows),
        ai=int(label_counts.get("AI", 0)),
        non_ai=int(label_counts.get("NON_AI", 0)),
        model_sha256=model_sha256,
        predictions_sha256=predictions_artifact.sha256,
    )
    write_json_artifact(
        config.manifest_output,
        {
            "artifact_schema_version": 1,
            "config": json_ready_dataclass(config),
            "result": json_ready_dataclass(result),
            "artifacts": {
                "model": {"path": str(config.model_path), "sha256": model_sha256},
                "predictions": predictions_artifact.as_manifest_dict(),
                "manifest": {"path": str(config.manifest_output)},
            },
        },
    )
    return result


def parse_labels(value: str) -> tuple[str, ...]:
    labels = tuple(label.strip() for label in value.split(",") if label.strip())
    if len(labels) < 2:
        raise argparse.ArgumentTypeError("at least two labels are required")
    return labels


def parse_calibration_methods(value: str) -> tuple[str, ...]:
    methods = tuple(method.strip() for method in value.split(",") if method.strip())
    if not methods:
        raise argparse.ArgumentTypeError("at least one calibration method is required")
    unknown = [method for method in methods if method not in CALIBRATION_METHODS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unsupported calibration method(s): {', '.join(unknown)}"
        )
    return methods


def parse_train_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train AI relevance Linear SVM.")
    parser.add_argument("--input", type=Path, default=DEFAULT_LABELLED_INPUT)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_OUTPUT)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS_OUTPUT)
    parser.add_argument("--label-counts-output", type=Path, default=DEFAULT_LABEL_COUNTS_OUTPUT)
    parser.add_argument("--predictions-output", type=Path, default=DEFAULT_TEST_PREDICTIONS_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument("--calibrator-output", type=Path, default=DEFAULT_CALIBRATOR_OUTPUT)
    parser.add_argument(
        "--calibration-report-output",
        type=Path,
        default=DEFAULT_CALIBRATION_REPORT_OUTPUT,
    )
    parser.add_argument(
        "--calibration-curve-output",
        type=Path,
        default=DEFAULT_CALIBRATION_CURVE_OUTPUT,
    )
    parser.add_argument("--text-columns", type=parse_text_columns, default=list(DEFAULT_TEXT_COLUMNS))
    parser.add_argument("--labels", type=parse_labels, default=DEFAULT_LABELS)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--min-class-count", type=int, default=20)
    parser.add_argument("--max-features", type=int, default=50_000)
    parser.add_argument("--min-df", type=parse_document_frequency, default=2)
    parser.add_argument("--max-df", type=parse_document_frequency, default=0.95)
    parser.add_argument("--ngram-max", type=int, default=3)
    parser.add_argument("--c-values", type=parse_c_values, default=(0.1, 1.0, 10.0))
    parser.add_argument("--class-weight", type=parse_class_weight, default="balanced")
    parser.add_argument("--max-iter", type=int, default=5000)
    parser.add_argument("--cv-folds", type=int, default=3)
    parser.add_argument("--calibration-size", type=float, default=0.2)
    parser.add_argument("--calibration-bins", type=int, default=10)
    parser.add_argument(
        "--calibration-methods",
        type=parse_calibration_methods,
        default=CALIBRATION_METHODS,
        help="Comma-separated subset of sigmoid,isotonic.",
    )
    parser.add_argument("--target-auto-ai-precision", type=float, default=0.90)
    parser.add_argument("--target-auto-non-ai-precision", type=float, default=0.90)
    return parser.parse_args()


def parse_predict_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict AI relevance for the unlabelled/rest corpus."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_CORPUS_INPUT)
    parser.add_argument("--labelled-input", type=Path, default=DEFAULT_LABELLED_INPUT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_OUTPUT)
    parser.add_argument("--model-manifest", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REST_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_REST_MANIFEST_OUTPUT)
    parser.add_argument("--text-columns", type=parse_text_columns, default=list(DEFAULT_TEXT_COLUMNS))
    parser.add_argument("--metadata-columns", type=parse_text_columns, default=list(DEFAULT_METADATA_COLUMNS))
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--include-labelled", action="store_true")
    parser.add_argument("--skip-checksum", action="store_true")
    return parser.parse_args()


def train_main() -> None:
    args = parse_train_args()
    result = train_ai_relevance_svm(
        AIRelevanceSVMTrainingConfig(
            input_path=args.input,
            model_output=args.model_output,
            metrics_output=args.metrics_output,
            label_counts_output=args.label_counts_output,
            predictions_output=args.predictions_output,
            manifest_output=args.manifest_output,
            calibrator_output=args.calibrator_output,
            calibration_report_output=args.calibration_report_output,
            calibration_curve_output=args.calibration_curve_output,
            text_columns=tuple(args.text_columns),
            labels=tuple(args.labels),
            test_size=args.test_size,
            random_state=args.random_state,
            max_rows=args.max_rows,
            min_class_count=args.min_class_count,
            max_features=args.max_features,
            min_df=args.min_df,
            max_df=args.max_df,
            ngram_max=args.ngram_max,
            c_values=tuple(args.c_values),
            class_weight=args.class_weight,
            max_iter=args.max_iter,
            cv_folds=args.cv_folds,
            calibration_size=args.calibration_size,
            calibration_bins=args.calibration_bins,
            calibration_methods=tuple(args.calibration_methods),
            target_auto_ai_precision=args.target_auto_ai_precision,
            target_auto_non_ai_precision=args.target_auto_non_ai_precision,
        )
    )
    print(f"Trained AI relevance SVM on {result.usable_rows:,} rows.")
    print(f"Accuracy: {result.accuracy:.4f}")
    print(f"Macro F1: {result.macro_f1:.4f}")
    print(f"Model: {result.model_output}")
    print(f"Calibrator: {result.calibrator_output} ({result.selected_calibrator})")
    print(
        "Thresholds: "
        f"AUTO_NON_AI <= {result.auto_non_ai_threshold:.4f}, "
        f"AUTO_AI >= {result.auto_ai_threshold:.4f}"
    )
    print(f"Calibration report: {result.calibration_report_output}")
    print(f"Calibration curve: {result.calibration_curve_output}")
    print(f"Metrics: {result.metrics_output}")


def predict_main() -> None:
    args = parse_predict_args()
    result = predict_rest_with_ai_relevance_svm(
        AIRelevanceSVMPredictionConfig(
            input_path=args.input,
            labelled_input_path=args.labelled_input,
            model_path=args.model,
            model_manifest_path=args.model_manifest,
            output_path=args.output,
            manifest_output=args.manifest_output,
            text_columns=tuple(args.text_columns),
            metadata_columns=tuple(args.metadata_columns),
            max_rows=args.max_rows,
            exclude_labelled=not args.include_labelled,
            verify_checksum=not args.skip_checksum,
        )
    )
    print(f"Predicted {result.predicted_rows:,} unlabelled rows.")
    print(f"Excluded labelled rows: {result.excluded_rows:,}")
    print(f"AI: {result.ai:,}")
    print(f"NON_AI: {result.non_ai:,}")
    print(f"Predictions: {result.output_path}")
