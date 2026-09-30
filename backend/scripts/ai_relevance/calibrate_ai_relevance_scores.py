"""Fit probability calibration for AI relevance scores.

The calibration CSV is used for fitting Platt/sigmoid or isotonic mapping.
The optional frozen test CSV is evaluation-only and must stay out of fitting.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.calibration import ProbabilityCalibrator, reliability_table
from src.modeling.training import combined_text, parse_text_columns
from src.pipeline.classify_ai_relevance_dataset import (
    DEFAULT_TEXT_COLUMNS,
    ai_probability_scores,
)
from src.pipeline.refresh_policy import (
    DEFAULT_AUTO_AI_THRESHOLD,
    DEFAULT_AUTO_NON_AI_THRESHOLD,
    configured_model_path,
)


DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "models" / "ai_relevance" / "calibration"
)


@dataclass(frozen=True)
class EvaluationResult:
    records: int
    positives: int
    negatives: int
    brier_score: float
    roc_auc: float | None
    auto_ai_threshold: float
    auto_non_ai_threshold: float
    ai_precision_at_auto_ai: float
    ai_recall_at_auto_ai: float
    ai_f1_at_auto_ai: float
    auto_ai_true_positive: int
    auto_ai_false_positive: int
    auto_ai_true_negative: int
    auto_ai_false_negative: int
    review_band_records: int
    auto_non_ai_records: int


def normalize_label(value: Any) -> int | None:
    text = str(value or "").strip().casefold().replace("_", "-").replace(" ", "-")
    if text in {"ai", "artificial-intelligence", "positive", "1", "true"}:
        return 1
    if text in {"non-ai", "not-ai", "nonai", "negative", "0", "false"}:
        return 0
    return None


def load_labelled_frame(path: Path, *, label_column: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype="object", low_memory=False)
    if label_column not in frame.columns:
        raise ValueError(f"{path} is missing label column: {label_column}")
    labels = frame[label_column].map(normalize_label)
    labelled = frame.loc[labels.notna()].copy()
    labelled["_ai_label"] = labels.loc[labels.notna()].astype(int)
    if labelled.empty:
        raise ValueError(f"{path} has no AI/NON_AI labels in {label_column}.")
    if labelled["_ai_label"].nunique() < 2:
        raise ValueError(f"{path} must contain both AI and NON_AI examples.")
    return labelled


def score_frame(
    *,
    model: Any,
    frame: pd.DataFrame,
    text_columns: Iterable[str],
) -> list[float]:
    selected_columns = tuple(column for column in text_columns if column in frame.columns)
    if not selected_columns:
        raise ValueError("Input CSV has no configured model text columns.")
    text = combined_text(frame.fillna(""), selected_columns)
    return ai_probability_scores(model, text)


def fit_calibrator(
    *,
    method: str,
    raw_scores: list[float],
    labels: list[int],
    model_path: Path,
    label_column: str,
) -> ProbabilityCalibrator:
    if method == "sigmoid":
        estimator = LogisticRegression(solver="lbfgs")
        estimator.fit(pd.Series(raw_scores).to_numpy().reshape(-1, 1), labels)
    elif method == "isotonic":
        estimator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        estimator.fit(raw_scores, labels)
    else:
        raise ValueError(f"Unsupported calibration method: {method}")
    return ProbabilityCalibrator(
        method=method,
        estimator=estimator,
        source_model_path=str(model_path),
        label_column=label_column,
    )


def evaluate_scores(
    *,
    labels: list[int],
    scores: list[float],
    auto_ai_threshold: float,
    auto_non_ai_threshold: float,
) -> EvaluationResult:
    binary_predictions = [
        1 if score >= auto_ai_threshold else 0 for score in scores
    ]
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels,
        binary_predictions,
        pos_label=1,
        average="binary",
        zero_division=0,
    )
    tn, fp, fn, tp = confusion_matrix(labels, binary_predictions, labels=[0, 1]).ravel()
    try:
        roc_auc = float(roc_auc_score(labels, scores))
    except ValueError:
        roc_auc = None
    return EvaluationResult(
        records=len(labels),
        positives=int(sum(labels)),
        negatives=int(len(labels) - sum(labels)),
        brier_score=float(brier_score_loss(labels, scores)),
        roc_auc=roc_auc,
        auto_ai_threshold=auto_ai_threshold,
        auto_non_ai_threshold=auto_non_ai_threshold,
        ai_precision_at_auto_ai=float(precision),
        ai_recall_at_auto_ai=float(recall),
        ai_f1_at_auto_ai=float(f1),
        auto_ai_true_positive=int(tp),
        auto_ai_false_positive=int(fp),
        auto_ai_true_negative=int(tn),
        auto_ai_false_negative=int(fn),
        review_band_records=int(
            sum(auto_non_ai_threshold < score < auto_ai_threshold for score in scores)
        ),
        auto_non_ai_records=int(sum(score <= auto_non_ai_threshold for score in scores)),
    )


def write_method_outputs(
    *,
    method: str,
    calibrator: ProbabilityCalibrator,
    output_dir: Path,
    calibration_labels: list[int],
    calibration_raw_scores: list[float],
    frozen_labels: list[int] | None,
    frozen_raw_scores: list[float] | None,
    auto_ai_threshold: float,
    auto_non_ai_threshold: float,
    bins: int,
) -> dict[str, Any]:
    calibrated_scores = calibrator.predict(calibration_raw_scores)
    metrics: dict[str, Any] = {
        "method": method,
        "calibration": asdict(
            evaluate_scores(
                labels=calibration_labels,
                scores=calibrated_scores,
                auto_ai_threshold=auto_ai_threshold,
                auto_non_ai_threshold=auto_non_ai_threshold,
            )
        ),
    }
    reliability_table(
        scores=calibrated_scores,
        labels=calibration_labels,
        bins=bins,
    ).to_csv(output_dir / f"reliability_calibration_{method}.csv", index=False)

    if frozen_labels is not None and frozen_raw_scores is not None:
        frozen_calibrated = calibrator.predict(frozen_raw_scores)
        metrics["frozen_test"] = asdict(
            evaluate_scores(
                labels=frozen_labels,
                scores=frozen_calibrated,
                auto_ai_threshold=auto_ai_threshold,
                auto_non_ai_threshold=auto_non_ai_threshold,
            )
        )
        reliability_table(
            scores=frozen_calibrated,
            labels=frozen_labels,
            bins=bins,
        ).to_csv(output_dir / f"reliability_frozen_test_{method}.csv", index=False)

    artifact_path = output_dir / f"probability_calibrator_{method}.joblib"
    joblib.dump(calibrator, artifact_path)
    metrics["artifact"] = str(artifact_path)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit and evaluate AI relevance probability calibration."
    )
    parser.add_argument("--model", type=Path, default=configured_model_path())
    parser.add_argument("--calibration-csv", type=Path, required=True)
    parser.add_argument("--frozen-test-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--method",
        choices=("sigmoid", "isotonic", "both"),
        default="sigmoid",
        help="Use sigmoid/Platt by default; run isotonic only as a comparison.",
    )
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--text-columns", type=parse_text_columns, default=list(DEFAULT_TEXT_COLUMNS))
    parser.add_argument("--auto-ai-threshold", type=float, default=DEFAULT_AUTO_AI_THRESHOLD)
    parser.add_argument("--auto-non-ai-threshold", type=float, default=DEFAULT_AUTO_NON_AI_THRESHOLD)
    parser.add_argument("--bins", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = configured_model_path(args.model)
    if model_path is None or not model_path.is_file():
        raise FileNotFoundError(f"AI relevance model was not found: {model_path}")
    if not 0 <= args.auto_non_ai_threshold < args.auto_ai_threshold <= 1:
        raise ValueError("Thresholds must satisfy 0 <= non-AI < AI <= 1.")

    model = joblib.load(model_path)
    calibration = load_labelled_frame(args.calibration_csv, label_column=args.label_column)
    calibration_labels = calibration["_ai_label"].astype(int).tolist()
    calibration_raw_scores = score_frame(
        model=model,
        frame=calibration,
        text_columns=tuple(args.text_columns),
    )

    frozen_labels: list[int] | None = None
    frozen_raw_scores: list[float] | None = None
    if args.frozen_test_csv is not None:
        frozen = load_labelled_frame(args.frozen_test_csv, label_column=args.label_column)
        frozen_labels = frozen["_ai_label"].astype(int).tolist()
        frozen_raw_scores = score_frame(
            model=model,
            frame=frozen,
            text_columns=tuple(args.text_columns),
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    methods = ("sigmoid", "isotonic") if args.method == "both" else (args.method,)
    report = {
        "model_path": str(model_path),
        "calibration_csv": str(args.calibration_csv),
        "frozen_test_csv": str(args.frozen_test_csv) if args.frozen_test_csv else None,
        "text_columns": list(args.text_columns),
        "label_column": args.label_column,
        "methods": {},
    }
    for method in methods:
        calibrator = fit_calibrator(
            method=method,
            raw_scores=calibration_raw_scores,
            labels=calibration_labels,
            model_path=model_path,
            label_column=args.label_column,
        )
        report["methods"][method] = write_method_outputs(
            method=method,
            calibrator=calibrator,
            output_dir=args.output_dir,
            calibration_labels=calibration_labels,
            calibration_raw_scores=calibration_raw_scores,
            frozen_labels=frozen_labels,
            frozen_raw_scores=frozen_raw_scores,
            auto_ai_threshold=args.auto_ai_threshold,
            auto_non_ai_threshold=args.auto_non_ai_threshold,
            bins=args.bins,
        )

    metrics_path = args.output_dir / "calibration_metrics.json"
    metrics_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"metrics": str(metrics_path), "methods": list(methods)}, indent=2))


if __name__ == "__main__":
    main()
