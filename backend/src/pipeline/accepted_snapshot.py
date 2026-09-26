"""Accepted-publication snapshot contract for public artifacts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACCEPTED_SNAPSHOT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "researchlanka_ai_accepted_snapshot.csv"
)
ACCEPTED_REVIEW_STATUSES = {"auto_accepted", "human_accepted"}
VERIFIED_OWNERSHIP_CONFIDENCES = {"HIGH", "MEDIUM"}


def accepted_snapshot_path(value: str | Path | None = None) -> Path:
    if value is None:
        return DEFAULT_ACCEPTED_SNAPSHOT_PATH
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _normalized(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def validate_accepted_snapshot_frame(frame: pd.DataFrame, *, source: Path | str) -> None:
    """Fail fast if a public artifact builder is pointed at a broad corpus."""

    if "final_ai_decision" in frame.columns:
        invalid = _normalized(frame["final_ai_decision"]).str.casefold() != "ai"
        if bool(invalid.any()):
            raise ValueError(
                f"{source} is not an accepted AI snapshot: final_ai_decision "
                "must be AI for every row."
            )
        return

    if "review_status" in frame.columns:
        statuses = _normalized(frame["review_status"]).str.casefold()
        invalid = ~statuses.isin(ACCEPTED_REVIEW_STATUSES)
        if bool(invalid.any()):
            raise ValueError(
                f"{source} is not an accepted AI snapshot: review_status must be "
                "auto_accepted or human_accepted for every row."
            )
        return

    required = {
        "ai_classification_label",
        "ownership_decision",
        "ownership_confidence",
        "needs_manual_review",
    }
    if required.issubset(frame.columns):
        labels = _normalized(frame["ai_classification_label"]).str.casefold()
        ownership = _normalized(frame["ownership_decision"]).str.upper()
        confidence = _normalized(frame["ownership_confidence"]).str.upper()
        needs_review = _normalized(frame["needs_manual_review"]).str.casefold()
        invalid = (
            (labels != "ai")
            | (ownership != "INCLUDE")
            | ~confidence.isin(VERIFIED_OWNERSHIP_CONFIDENCES)
            | needs_review.isin({"true", "1", "yes", "y"})
        )
        if bool(invalid.any()):
            raise ValueError(
                f"{source} is not an accepted AI snapshot: rows must be AI-labelled "
                "and pass verified Sri Lanka ownership."
            )
        return

    raise ValueError(
        f"{source} is missing accepted-snapshot markers. Export from the accepted "
        "review dataset or pass the explicit development opt-out flag."
    )
