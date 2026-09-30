"""Probability calibration helpers for AI relevance scores."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from src.pipeline.refresh_policy import configured_calibrator_path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


CALIBRATION_METHODS = ("sigmoid", "isotonic")


@dataclass(frozen=True)
class ProbabilityCalibrator:
    """Map raw model scores to calibrated P(AI)."""

    method: str
    estimator: Any
    source_model_path: str | None = None
    label_column: str = "label"

    def predict(self, scores: Iterable[float]) -> list[float]:
        values = np.asarray(list(scores), dtype=float)
        if values.size == 0:
            return []
        if self.method == "sigmoid":
            calibrated = self.estimator.predict_proba(values.reshape(-1, 1))[:, 1]
        elif self.method == "isotonic":
            calibrated = self.estimator.predict(values)
        else:
            raise ValueError(f"Unsupported probability calibration method: {self.method}")
        return [float(min(1.0, max(0.0, score))) for score in calibrated]


def load_probability_calibrator(path: str | Path) -> ProbabilityCalibrator:
    calibrator = joblib.load(path)
    if not hasattr(calibrator, "predict"):
        raise ValueError(f"Probability calibrator does not expose predict(): {path}")
    return calibrator


def calibrate_scores(
    scores: Iterable[float],
    *,
    calibrator_path: str | Path | None = None,
) -> list[float]:
    selected_path = configured_calibrator_path(calibrator_path)
    raw_scores = [float(score) for score in scores]
    if selected_path is None:
        return raw_scores
    calibrator = load_probability_calibrator(selected_path)
    return calibrator.predict(raw_scores)


def fit_probability_calibrator(
    *,
    method: str,
    raw_scores: Iterable[float],
    labels: Iterable[int],
    source_model_path: str | Path | None = None,
    label_column: str = "label",
) -> ProbabilityCalibrator:
    scores = np.asarray(list(raw_scores), dtype=float)
    binary_labels = np.asarray(list(labels), dtype=int)
    if scores.size == 0:
        raise ValueError("Calibration needs at least one score.")
    if scores.size != binary_labels.size:
        raise ValueError("Calibration scores and labels must have the same length.")
    if len(np.unique(binary_labels)) < 2:
        raise ValueError("Calibration split must contain both AI and NON_AI labels.")

    if method == "sigmoid":
        estimator = LogisticRegression(solver="lbfgs")
        estimator.fit(scores.reshape(-1, 1), binary_labels)
    elif method == "isotonic":
        estimator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        estimator.fit(scores, binary_labels)
    else:
        raise ValueError(f"Unsupported calibration method: {method}")

    return ProbabilityCalibrator(
        method=method,
        estimator=estimator,
        source_model_path=str(source_model_path) if source_model_path else None,
        label_column=label_column,
    )


def expected_calibration_error(
    *,
    scores: Iterable[float],
    labels: Iterable[int],
    bins: int = 10,
) -> float:
    table = reliability_table(scores=scores, labels=labels, bins=bins)
    total = int(table["records"].sum()) if not table.empty else 0
    if total == 0:
        return 0.0
    ece = 0.0
    for row in table.to_dict("records"):
        if not row["records"]:
            continue
        predicted = row["mean_predicted_probability"]
        observed = row["observed_ai_rate"]
        if predicted is None or observed is None:
            continue
        ece += (int(row["records"]) / total) * abs(float(predicted) - float(observed))
    return float(ece)


def calibration_metrics(
    *,
    scores: Iterable[float],
    labels: Iterable[int],
    bins: int = 10,
) -> dict[str, Any]:
    score_values = [float(min(1.0, max(0.0, score))) for score in scores]
    label_values = [int(label) for label in labels]
    if len(score_values) != len(label_values):
        raise ValueError("Calibration scores and labels must have the same length.")
    try:
        roc_auc = float(roc_auc_score(label_values, score_values))
    except ValueError:
        roc_auc = None
    return {
        "records": len(label_values),
        "positives": int(sum(label_values)),
        "negatives": int(len(label_values) - sum(label_values)),
        "brier_score": float(brier_score_loss(label_values, score_values)),
        "expected_calibration_error": expected_calibration_error(
            scores=score_values,
            labels=label_values,
            bins=bins,
        ),
        "roc_auc": roc_auc,
    }


def choose_probability_thresholds(
    *,
    scores: Iterable[float],
    labels: Iterable[int],
    target_auto_precision: float = 0.90,
    target_auto_non_ai_precision: float = 0.90,
) -> dict[str, Any]:
    rows = sorted(
        zip(
            [float(min(1.0, max(0.0, score))) for score in scores],
            [int(label) for label in labels],
            strict=True,
        ),
        key=lambda item: item[0],
    )
    if not rows:
        raise ValueError("Threshold selection needs at least one labelled score.")

    unique_scores = sorted({score for score, _label in rows})
    auto_ai_candidates: list[dict[str, Any]] = []
    auto_non_ai_candidates: list[dict[str, Any]] = []
    for threshold in unique_scores:
        high = [(score, label) for score, label in rows if score >= threshold]
        if high:
            precision = sum(label for _score, label in high) / len(high)
            auto_ai_candidates.append(
                {
                    "threshold": threshold,
                    "precision": float(precision),
                    "records": len(high),
                    "ai_records": int(sum(label for _score, label in high)),
                }
            )
        low = [(score, label) for score, label in rows if score <= threshold]
        if low:
            non_ai_precision = sum(1 - label for _score, label in low) / len(low)
            auto_non_ai_candidates.append(
                {
                    "threshold": threshold,
                    "precision": float(non_ai_precision),
                    "records": len(low),
                    "non_ai_records": int(sum(1 - label for _score, label in low)),
                }
            )

    valid_ai = [
        candidate
        for candidate in auto_ai_candidates
        if candidate["precision"] >= target_auto_precision
    ]
    valid_non_ai = [
        candidate
        for candidate in auto_non_ai_candidates
        if candidate["precision"] >= target_auto_non_ai_precision
    ]
    selected_ai = (
        min(valid_ai, key=lambda item: (item["threshold"], -item["records"]))
        if valid_ai
        else max(auto_ai_candidates, key=lambda item: (item["precision"], item["records"]))
    )
    selected_non_ai = (
        max(valid_non_ai, key=lambda item: (item["threshold"], item["records"]))
        if valid_non_ai
        else max(
            auto_non_ai_candidates,
            key=lambda item: (item["precision"], item["records"]),
        )
    )

    auto_ai_threshold = float(selected_ai["threshold"])
    auto_non_ai_threshold = float(selected_non_ai["threshold"])
    if auto_non_ai_threshold >= auto_ai_threshold:
        midpoint = (auto_non_ai_threshold + auto_ai_threshold) / 2
        auto_non_ai_threshold = max(0.0, midpoint - 0.01)
        auto_ai_threshold = min(1.0, midpoint + 0.01)

    decision_counts = {
        "AUTO_AI": int(sum(score >= auto_ai_threshold for score, _label in rows)),
        "REVIEW": int(
            sum(auto_non_ai_threshold < score < auto_ai_threshold for score, _label in rows)
        ),
        "AUTO_NON_AI": int(sum(score <= auto_non_ai_threshold for score, _label in rows)),
    }
    return {
        "auto_ai_threshold": auto_ai_threshold,
        "auto_non_ai_threshold": auto_non_ai_threshold,
        "target_auto_ai_precision": target_auto_precision,
        "target_auto_non_ai_precision": target_auto_non_ai_precision,
        "selected_auto_ai": selected_ai,
        "selected_auto_non_ai": selected_non_ai,
        "decision_counts": decision_counts,
    }


def reliability_table(
    *,
    scores: Iterable[float],
    labels: Iterable[int],
    bins: int = 10,
) -> pd.DataFrame:
    values = pd.DataFrame(
        {
            "score": pd.to_numeric(pd.Series(list(scores)), errors="coerce"),
            "label": pd.to_numeric(pd.Series(list(labels)), errors="coerce"),
        }
    ).dropna()
    if values.empty:
        return pd.DataFrame(
            columns=[
                "bin_start",
                "bin_end",
                "records",
                "mean_predicted_probability",
                "observed_ai_rate",
            ]
        )

    edges = np.linspace(0.0, 1.0, bins + 1)
    values["bucket"] = pd.cut(
        values["score"].clip(0.0, 1.0),
        bins=edges,
        include_lowest=True,
        right=True,
    )
    grouped = values.groupby("bucket", observed=False)
    rows: list[dict[str, Any]] = []
    for bucket, group in grouped:
        left = float(bucket.left)
        right = float(bucket.right)
        rows.append(
            {
                "bin_start": max(0.0, left),
                "bin_end": min(1.0, right),
                "records": int(len(group)),
                "mean_predicted_probability": float(group["score"].mean())
                if len(group)
                else None,
                "observed_ai_rate": float(group["label"].mean()) if len(group) else None,
            }
        )
    return pd.DataFrame(rows)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _draw_line(
    pixels: bytearray,
    *,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        if 0 <= x0 < width and 0 <= y0 < height:
            offset = (y0 * width + x0) * 3
            pixels[offset : offset + 3] = bytes(color)
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def write_calibration_curve_png(
    path: str | Path,
    *,
    reliability: pd.DataFrame,
    width: int = 800,
    height: int = 520,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixels = bytearray([255] * width * height * 3)
    margin_left, margin_right, margin_top, margin_bottom = 72, 32, 32, 72
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def point(x_value: float, y_value: float) -> tuple[int, int]:
        x = margin_left + round(max(0.0, min(1.0, x_value)) * plot_width)
        y = margin_top + round((1.0 - max(0.0, min(1.0, y_value))) * plot_height)
        return x, y

    grid_color = (226, 232, 240)
    axis_color = (30, 41, 59)
    ideal_color = (148, 163, 184)
    curve_color = (14, 116, 144)
    for tick in range(11):
        value = tick / 10
        x, _ = point(value, 0)
        _, y = point(0, value)
        _draw_line(
            pixels,
            width=width,
            height=height,
            start=(x, margin_top),
            end=(x, margin_top + plot_height),
            color=grid_color,
        )
        _draw_line(
            pixels,
            width=width,
            height=height,
            start=(margin_left, y),
            end=(margin_left + plot_width, y),
            color=grid_color,
        )

    _draw_line(
        pixels,
        width=width,
        height=height,
        start=(margin_left, margin_top + plot_height),
        end=(margin_left + plot_width, margin_top + plot_height),
        color=axis_color,
    )
    _draw_line(
        pixels,
        width=width,
        height=height,
        start=(margin_left, margin_top),
        end=(margin_left, margin_top + plot_height),
        color=axis_color,
    )
    _draw_line(
        pixels,
        width=width,
        height=height,
        start=point(0.0, 0.0),
        end=point(1.0, 1.0),
        color=ideal_color,
    )

    valid = reliability[
        reliability["records"].astype(int).gt(0)
        & reliability["mean_predicted_probability"].notna()
        & reliability["observed_ai_rate"].notna()
    ]
    points = [
        point(float(row["mean_predicted_probability"]), float(row["observed_ai_rate"]))
        for row in valid.to_dict("records")
    ]
    for first, second in zip(points, points[1:]):
        _draw_line(
            pixels,
            width=width,
            height=height,
            start=first,
            end=second,
            color=curve_color,
        )
    for x, y in points:
        for yy in range(y - 3, y + 4):
            for xx in range(x - 3, x + 4):
                if 0 <= xx < width and 0 <= yy < height:
                    offset = (yy * width + xx) * 3
                    pixels[offset : offset + 3] = bytes(curve_color)

    scanlines = b"".join(
        b"\x00" + bytes(pixels[row * width * 3 : (row + 1) * width * 3])
        for row in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _png_chunk(b"IEND", b"")
    )
    output_path.write_bytes(png)
