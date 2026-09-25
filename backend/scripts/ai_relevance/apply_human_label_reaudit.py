#!/usr/bin/env python3
"""Apply explicit human re-audit status columns to human-labelled AI data."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EARLY_HUMAN = (
    PROJECT_ROOT
    / "data/final_ai_corpus_human_audit_sample_stratified - final_ai_corpus_human_audit_sample_stratified (1).csv"
)
LATE_HUMAN = PROJECT_ROOT / "data/Finished/manual_review_800 - manual_review_800.csv"


CONFIRMED_AI_DOIS = {
    "10.1109/icac54203.2021.9671125": "Re-reviewed: AI-powered chatbot/OCR/prediction/recommendation evidence.",
    "10.1109/icarc64760.2025.10963140": "Re-reviewed: object detection, pose detection, and voice recognition are central.",
    "10.1038/s41597-025-05906-9": "Re-reviewed: dataset created for machine-learning/AI dental radiograph analysis.",
    "10.1109/icter.2016.7829904": "Re-reviewed: AI/computer-vision relevance in note identification support system.",
    "10.1109/mercon.2019.8818878": "Re-reviewed: rule-based recommendation system treated as AI-related.",
}


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalize_label(value: Any) -> str:
    label = clean(value).upper().replace("-", "_").replace(" ", "_")
    if label in {"AI", "NON_AI", "REVIEW"}:
        return label
    if label in {"NULL", ""}:
        return "REVIEW"
    return "REVIEW"


def row_has_doi(row: pd.Series, doi: str) -> bool:
    doi_l = doi.casefold()
    for column in ("doi", "doi_url", "publication_key", "record_key"):
        if column in row.index and doi_l in clean(row[column]).casefold():
            return True
    return False


def apply_reaudit(path: Path, label_column: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    if "human_final_label" not in frame.columns:
        frame["human_final_label"] = frame[label_column].map(normalize_label)
    if "human_review_status" not in frame.columns:
        frame["human_review_status"] = frame["human_final_label"].map(
            {
                "AI": "CONFIRMED_AI",
                "NON_AI": "CONFIRMED_NON_AI",
                "REVIEW": "AMBIGUOUS_REVIEW",
            }
        )
    if "human_reaudit_notes" not in frame.columns:
        frame["human_reaudit_notes"] = ""

    for doi, note in CONFIRMED_AI_DOIS.items():
        mask = frame.apply(lambda row: row_has_doi(row, doi), axis=1)
        if mask.any():
            frame.loc[mask, label_column] = "AI"
            frame.loc[mask, "human_final_label"] = "AI"
            frame.loc[mask, "human_review_status"] = "CONFIRMED_AI"
            frame.loc[mask, "human_reaudit_notes"] = note

    ambiguous_mask = frame["human_final_label"].eq("REVIEW")
    frame.loc[ambiguous_mask, "human_review_status"] = "AMBIGUOUS_REVIEW"
    frame.to_csv(path, index=False)
    return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--early-human", type=Path, default=EARLY_HUMAN)
    parser.add_argument("--late-human", type=Path, default=LATE_HUMAN)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    early = apply_reaudit(args.early_human, "human_ai_label")
    late = apply_reaudit(args.late_human, "human_review")
    for name, frame in (("early", early), ("late", late)):
        print(name)
        print(frame["human_review_status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
