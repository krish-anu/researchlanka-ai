"""Probability calibration helpers for AI relevance scores."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def configured_calibrator_path(value: str | Path | None = None) -> Path | None:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_AI_CALIBRATOR_PATH")
    if raw_value in (None, ""):
        return None
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


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
