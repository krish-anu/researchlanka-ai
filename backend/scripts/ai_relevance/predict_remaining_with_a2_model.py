#!/usr/bin/env python3
"""Predict remaining pending-review rows with the selected A2 AI model."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.preprocessing.text_cleaning import clean_text_series


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = PROJECT_ROOT / "data/models/ai_relevance/metadata_ablation/A2_title_abstract_keywords.joblib"
DEFAULT_PENDING = PROJECT_ROOT / "data/pending-review-split/model_predict_remaining_1207.csv"
DEFAULT_CORPUS = PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_classified.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/processed/ai/model_predict_remaining_1207_a2_predictions.csv"
DEFAULT_SUMMARY = PROJECT_ROOT / "data/processed/ai/model_predict_remaining_1207_a2_prediction_summary.csv"


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def row_keys(row: pd.Series) -> set[str]:
    keys: set[str] = set()
    publication_key = clean(row.get("publication_key", ""))
    if publication_key:
        keys.add(publication_key.casefold())
    for column, prefix in (
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("source_record_id", "source_record_id"),
    ):
        value = clean(row.get(column, ""))
        if value:
            for part in value.split(";"):
                part = clean(part)
                if part:
                    keys.add(f"{prefix}:{part.casefold()}")
    return keys


def build_lookup(corpus: pd.DataFrame) -> dict[str, dict[str, str]]:
    columns = [
        column
        for column in (
            "source_dataset",
            "source_institution_id",
            "source_record_id",
            "openalex_id",
            "doi",
            "url",
            "title",
            "abstract",
            "keywords",
            "publication_date",
            "type",
            "authors",
            "institutions",
            "primary_topic",
            "primary_field",
            "primary_subfield",
            "primary_domain",
            "ai_classification_label",
            "ai_classification_confidence",
        )
        if column in corpus.columns
    ]
    lookup: dict[str, dict[str, str]] = {}
    for _, row in corpus.iterrows():
        payload = {column: clean(row.get(column, "")) for column in columns}
        for key in row_keys(row):
            lookup.setdefault(key, payload)
    return lookup


def prefixed_a2_text(frame: pd.DataFrame) -> pd.Series:
    parts = []
    for column in ("title", "abstract", "keywords"):
        values = frame[column].fillna("").astype(str) if column in frame.columns else ""
        parts.append(column.upper() + ": " + values)
    text = pd.concat(parts, axis=1).agg(" ".join, axis=1)
    text = text.str.replace(r"\s+", " ", regex=True).str.strip()
    return clean_text_series(text)


def classify_three_way(score: float, *, ai_threshold: float, non_ai_threshold: float) -> str:
    if score >= ai_threshold:
        return "AUTO_AI"
    if score <= non_ai_threshold:
        return "AUTO_NON_AI"
    return "REVIEW"


def predict_remaining(
    *,
    model_path: Path = DEFAULT_MODEL,
    pending_path: Path = DEFAULT_PENDING,
    corpus_path: Path = DEFAULT_CORPUS,
    output_path: Path = DEFAULT_OUTPUT,
    summary_path: Path = DEFAULT_SUMMARY,
    binary_threshold: float = 0.35,
    auto_ai_threshold: float = 0.70,
    auto_non_ai_threshold: float = 0.20,
) -> pd.DataFrame:
    pending = pd.read_csv(pending_path, dtype=str, keep_default_na=False, low_memory=False)
    corpus = pd.read_csv(corpus_path, dtype=str, keep_default_na=False, low_memory=False)
    lookup = build_lookup(corpus)
    metadata_rows = []
    for _, row in pending.iterrows():
        metadata: dict[str, str] = {}
        for key in row_keys(row):
            if key in lookup:
                metadata = dict(lookup[key])
                break
        metadata_rows.append(metadata)
    metadata = pd.DataFrame(metadata_rows)
    joined = pd.concat([pending.reset_index(drop=True), metadata.reset_index(drop=True)], axis=1)
    model = joblib.load(model_path)
    text = prefixed_a2_text(joined)
    probabilities = model.predict_proba(text)
    scores = [float(row[1]) for row in probabilities]
    joined["a2_ai_score"] = [f"{score:.6f}" for score in scores]
    joined["a2_binary_prediction"] = [
        "AI" if score >= binary_threshold else "NON_AI" for score in scores
    ]
    joined["a2_binary_threshold"] = f"{binary_threshold:.2f}"
    joined["a2_production_decision"] = [
        classify_three_way(
            score,
            ai_threshold=auto_ai_threshold,
            non_ai_threshold=auto_non_ai_threshold,
        )
        for score in scores
    ]
    joined["a2_auto_ai_threshold"] = f"{auto_ai_threshold:.2f}"
    joined["a2_auto_non_ai_threshold"] = f"{auto_non_ai_threshold:.2f}"
    joined["a2_model_path"] = str(model_path)
    joined["metadata_joined"] = joined["title"].fillna("").astype(str).str.strip().ne("")

    preferred = [
        "publication_key",
        "publication_url",
        "a2_production_decision",
        "a2_binary_prediction",
        "a2_ai_score",
        "a2_binary_threshold",
        "a2_auto_ai_threshold",
        "a2_auto_non_ai_threshold",
        "metadata_joined",
        "title",
        "abstract",
        "keywords",
        "doi",
        "openalex_id",
        "source_record_id",
        "publication_date",
        "type",
        "authors",
        "institutions",
        "primary_topic",
        "primary_field",
        "primary_subfield",
        "primary_domain",
        "original_ai_label",
        "original_ai_confidence",
        "original_ai_model",
        "a2_model_path",
    ]
    output_columns = [column for column in preferred if column in joined.columns]
    result = joined[output_columns].copy()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    summary_rows = []
    for column in ("a2_production_decision", "a2_binary_prediction", "metadata_joined"):
        counts = result[column].value_counts(dropna=False)
        for value, count in counts.items():
            summary_rows.append({"metric": column, "value": value, "count": int(count)})
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--binary-threshold", type=float, default=0.35)
    parser.add_argument("--auto-ai-threshold", type=float, default=0.70)
    parser.add_argument("--auto-non-ai-threshold", type=float, default=0.20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = predict_remaining(
        model_path=args.model,
        pending_path=args.pending,
        corpus_path=args.corpus,
        output_path=args.output,
        summary_path=args.summary,
        binary_threshold=args.binary_threshold,
        auto_ai_threshold=args.auto_ai_threshold,
        auto_non_ai_threshold=args.auto_non_ai_threshold,
    )
    print(f"Wrote {len(result)} rows to {args.output}")
    print(result["a2_production_decision"].value_counts().to_string())
    print(result["a2_binary_prediction"].value_counts().to_string())


if __name__ == "__main__":
    main()
