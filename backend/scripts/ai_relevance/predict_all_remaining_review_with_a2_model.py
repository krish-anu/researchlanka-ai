#!/usr/bin/env python3
"""Resolve all remaining review rows with the selected A2 binary model."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

from src.preprocessing.text_cleaning import clean_text_series


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = PROJECT_ROOT / "data/models/ai_relevance/metadata_ablation/A2_title_abstract_keywords.joblib"
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data/processed/common/common_publications_final_2016_2026_ai_classified_finished_and_a2_binary_resolved.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data/processed/common/common_publications_final_2016_2026_ai_classified_all_review_binary_resolved.csv"
)
DEFAULT_AI_ONLY = (
    PROJECT_ROOT
    / "data/processed/common/common_publications_final_2016_2026_ai_only_all_review_binary_resolved.csv"
)
DEFAULT_REJECTED = (
    PROJECT_ROOT
    / "data/processed/common/common_publications_final_2016_2026_non_ai_all_review_binary_resolved.csv"
)
DEFAULT_PREDICTIONS = (
    PROJECT_ROOT / "data/processed/ai/all_remaining_review_1480_a2_predictions.csv"
)
DEFAULT_SUMMARY = (
    PROJECT_ROOT / "data/processed/ai/all_remaining_review_a2_binary_resolution_summary.csv"
)


def prefixed_a2_text(frame: pd.DataFrame) -> pd.Series:
    parts = []
    for column in ("title", "abstract", "keywords"):
        values = frame[column].fillna("").astype(str) if column in frame.columns else ""
        parts.append(column.upper() + ": " + values)
    text = pd.concat(parts, axis=1).agg(" ".join, axis=1)
    text = text.str.replace(r"\s+", " ", regex=True).str.strip()
    return clean_text_series(text)


def resolve_review_rows(
    *,
    input_path: Path = DEFAULT_INPUT,
    model_path: Path = DEFAULT_MODEL,
    output_path: Path = DEFAULT_OUTPUT,
    ai_only_path: Path = DEFAULT_AI_ONLY,
    rejected_path: Path = DEFAULT_REJECTED,
    predictions_path: Path = DEFAULT_PREDICTIONS,
    summary_path: Path = DEFAULT_SUMMARY,
    binary_threshold: float = 0.35,
) -> pd.DataFrame:
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False, low_memory=False)
    review_mask = frame["ai_classification_label"].eq("review")
    review_rows = frame.loc[review_mask].copy()

    model = joblib.load(model_path)
    scores = [float(row[1]) for row in model.predict_proba(prefixed_a2_text(review_rows))]
    labels = ["AI" if score >= binary_threshold else "non-AI" for score in scores]

    frame.loc[review_mask, "ai_classification_label"] = labels
    frame.loc[review_mask, "ai_classification_confidence"] = [f"{score:.6f}" for score in scores]
    frame.loc[review_mask, "ai_classification_model"] = str(model_path)
    frame.loc[review_mask, "ai_classification_reason"] = [
        f"a2_all_remaining_review_binary_threshold_{binary_threshold:.2f}; score={score:.6f}"
        for score in scores
    ]
    if "final_resolution_source" not in frame.columns:
        frame["final_resolution_source"] = ""
    frame.loc[review_mask, "final_resolution_source"] = "a2_all_remaining_review_prediction"

    predictions = review_rows.copy()
    predictions["a2_ai_score"] = [f"{score:.6f}" for score in scores]
    predictions["a2_binary_prediction"] = labels
    predictions["a2_binary_threshold"] = f"{binary_threshold:.2f}"
    predictions["a2_model_path"] = str(model_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    frame[frame["ai_classification_label"].eq("AI")].to_csv(ai_only_path, index=False)
    frame[frame["ai_classification_label"].eq("non-AI")].to_csv(rejected_path, index=False)
    predictions.to_csv(predictions_path, index=False)

    rows = [
        {"metric": "input_rows", "value": "", "count": len(frame)},
        {"metric": "review_rows_predicted", "value": "", "count": len(review_rows)},
    ]
    for value, count in pd.Series(labels).value_counts().items():
        rows.append({"metric": "remaining_review_prediction", "value": value, "count": int(count)})
    for value, count in frame["ai_classification_label"].value_counts().items():
        rows.append({"metric": "final_ai_classification_label", "value": value, "count": int(count)})
    pd.DataFrame(rows).to_csv(summary_path, index=False)
    return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ai-only", type=Path, default=DEFAULT_AI_ONLY)
    parser.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--binary-threshold", type=float, default=0.35)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = resolve_review_rows(
        input_path=args.input,
        model_path=args.model,
        output_path=args.output,
        ai_only_path=args.ai_only,
        rejected_path=args.rejected,
        predictions_path=args.predictions,
        summary_path=args.summary,
        binary_threshold=args.binary_threshold,
    )
    print(f"Wrote resolved dataset: {args.output}")
    print(frame["ai_classification_label"].value_counts().to_string())


if __name__ == "__main__":
    main()
