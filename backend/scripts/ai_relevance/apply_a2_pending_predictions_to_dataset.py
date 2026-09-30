#!/usr/bin/env python3
"""Apply finished reviews and A2 binary pending predictions to the corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLASSIFIED = (
    PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_classified.csv"
)
DEFAULT_A2_PREDICTIONS = (
    PROJECT_ROOT / "data/processed/ai/model_predict_remaining_1207_a2_predictions.csv"
)
DEFAULT_HUMAN_REVIEWS = (
    PROJECT_ROOT / "data/Finished/manual_review_800 - manual_review_800.csv"
)
DEFAULT_GEMINI_REVIEWS = (
    PROJECT_ROOT / "data/Finished/gemini_review_1000_openrouter_predictions.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_classified_finished_and_a2_binary_resolved.csv"
)
DEFAULT_AI_ONLY = (
    PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_only_finished_and_a2_binary_resolved.csv"
)
DEFAULT_REVIEW = (
    PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_review_finished_and_a2_binary_resolved.csv"
)
DEFAULT_REJECTED = (
    PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_rejected_finished_and_a2_binary_resolved.csv"
)
DEFAULT_SUMMARY = (
    PROJECT_ROOT / "data/processed/ai/finished_and_a2_binary_dataset_update_summary.csv"
)


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
        ("publication_id", "source_record_id"),
    ):
        value = clean(row.get(column, ""))
        if value:
            for part in value.split(";"):
                part = clean(part)
                if part:
                    keys.add(f"{prefix}:{part.casefold()}")
    return keys


def build_base_lookup(classified: pd.DataFrame) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for index, row in classified.iterrows():
        for key in row_keys(row):
            lookup.setdefault(key, index)
        url = clean(row.get("url", ""))
        if url:
            lookup.setdefault(f"url:{url.casefold()}", index)
    return lookup


def normalize_label(value: str) -> str:
    text = clean(value).upper().replace("-", "_").replace(" ", "_")
    if text == "AI":
        return "AI"
    if text in {"NON_AI", "NONAI", "NOT_AI"}:
        return "non-AI"
    return "review"


def build_prediction_lookup(predictions: pd.DataFrame) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    fields = [
        "a2_production_decision",
        "a2_binary_prediction",
        "a2_ai_score",
        "a2_binary_threshold",
        "a2_auto_ai_threshold",
        "a2_auto_non_ai_threshold",
        "a2_model_path",
    ]
    for _, row in predictions.iterrows():
        payload = {field: clean(row.get(field, "")) for field in fields}
        for key in row_keys(row):
            lookup.setdefault(key, payload)
    return lookup


def label_from_decision(decision: str) -> str:
    if decision == "AUTO_AI":
        return "AI"
    if decision == "AUTO_NON_AI":
        return "non-AI"
    return "review"


def apply_labeled_file(
    *,
    updated: pd.DataFrame,
    base_lookup: dict[str, int],
    labels: pd.DataFrame,
    label_column: str,
    source_name: str,
    model_column: str = "",
    confidence_column: str = "",
    reason_column: str = "",
) -> tuple[int, int]:
    matched = 0
    changed_to_ai = 0
    for _, row in labels.iterrows():
        index: int | None = None
        for key in row_keys(row):
            if key in base_lookup:
                index = base_lookup[key]
                break
        if index is None:
            publication_url = clean(row.get("publication_url", ""))
            if publication_url:
                index = base_lookup.get(f"url:{publication_url.casefold()}")
        if index is None:
            continue

        label = normalize_label(row.get(label_column, ""))
        matched += 1
        if label == "AI" and updated.at[index, "ai_classification_label"] != "AI":
            changed_to_ai += 1

        updated.at[index, "ai_classification_label"] = label
        updated.at[index, "ai_classification_model"] = (
            clean(row.get(model_column, "")) if model_column else source_name
        )
        if confidence_column:
            updated.at[index, "ai_classification_confidence"] = clean(row.get(confidence_column, ""))
        updated.at[index, "ai_classification_reason"] = (
            clean(row.get(reason_column, "")) if reason_column else f"resolved_by_{source_name}"
        )
        updated.at[index, "final_resolution_source"] = source_name
    return matched, changed_to_ai


def reason_from_decision(row: dict[str, str]) -> str:
    decision = row["a2_production_decision"]
    score = row["a2_ai_score"]
    if decision == "AUTO_AI":
        return f"a2_title_abstract_keywords_score_gte_{row['a2_auto_ai_threshold']}; score={score}"
    if decision == "AUTO_NON_AI":
        return f"a2_title_abstract_keywords_score_lte_{row['a2_auto_non_ai_threshold']}; score={score}"
    return (
        "a2_title_abstract_keywords_between_auto_thresholds; "
        f"score={score}; review_range=({row['a2_auto_non_ai_threshold']}, {row['a2_auto_ai_threshold']})"
    )


def apply_predictions(
    *,
    classified_path: Path = DEFAULT_CLASSIFIED,
    human_reviews_path: Path = DEFAULT_HUMAN_REVIEWS,
    gemini_reviews_path: Path = DEFAULT_GEMINI_REVIEWS,
    predictions_path: Path = DEFAULT_A2_PREDICTIONS,
    output_path: Path = DEFAULT_OUTPUT,
    ai_only_path: Path = DEFAULT_AI_ONLY,
    review_path: Path = DEFAULT_REVIEW,
    rejected_path: Path = DEFAULT_REJECTED,
    summary_path: Path = DEFAULT_SUMMARY,
) -> pd.DataFrame:
    classified = pd.read_csv(classified_path, dtype=str, keep_default_na=False, low_memory=False)
    human_reviews = pd.read_csv(human_reviews_path, dtype=str, keep_default_na=False, low_memory=False)
    gemini_reviews = pd.read_csv(gemini_reviews_path, dtype=str, keep_default_na=False, low_memory=False)
    predictions = pd.read_csv(predictions_path, dtype=str, keep_default_na=False, low_memory=False)
    lookup = build_prediction_lookup(predictions)

    updated = classified.copy()
    base_lookup = build_base_lookup(updated)
    for column in (
        "final_resolution_source",
        "a2_pending_decision",
        "a2_pending_binary_prediction",
        "a2_pending_ai_score",
        "a2_pending_model_path",
    ):
        if column not in updated.columns:
            updated[column] = ""

    human_matched, human_added_ai = apply_labeled_file(
        updated=updated,
        base_lookup=base_lookup,
        labels=human_reviews,
        label_column="human_final_label",
        source_name="finished_human_review",
        confidence_column="normalized_ai_confidence",
        reason_column="reviewer_notes",
    )
    gemini_matched, gemini_added_ai = apply_labeled_file(
        updated=updated,
        base_lookup=base_lookup,
        labels=gemini_reviews,
        label_column="ai_llm_label",
        source_name="finished_gemini_review",
        model_column="ai_llm_model",
        confidence_column="ai_llm_confidence",
        reason_column="ai_llm_reason",
    )

    matched = 0
    pending_added_ai = 0
    for index, row in updated.iterrows():
        payload: dict[str, str] | None = None
        for key in row_keys(row):
            if key in lookup:
                payload = lookup[key]
                break
        if not payload:
            continue
        matched += 1
        updated.at[index, "a2_pending_decision"] = payload["a2_production_decision"]
        updated.at[index, "a2_pending_binary_prediction"] = payload["a2_binary_prediction"]
        updated.at[index, "a2_pending_ai_score"] = payload["a2_ai_score"]
        updated.at[index, "a2_pending_model_path"] = payload["a2_model_path"]
        label = normalize_label(payload["a2_binary_prediction"])
        if label == "AI" and updated.at[index, "ai_classification_label"] != "AI":
            pending_added_ai += 1
        updated.at[index, "ai_classification_label"] = label
        updated.at[index, "ai_classification_confidence"] = payload["a2_ai_score"]
        updated.at[index, "ai_classification_model"] = payload["a2_model_path"]
        updated.at[index, "ai_classification_reason"] = (
            f"a2_title_abstract_keywords_binary_threshold_{payload['a2_binary_threshold']}; "
            f"score={payload['a2_ai_score']}; production_decision={payload['a2_production_decision']}"
        )
        updated.at[index, "final_resolution_source"] = "a2_binary_pending_prediction"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(output_path, index=False)
    updated[updated["ai_classification_label"].eq("AI")].to_csv(ai_only_path, index=False)
    updated[updated["ai_classification_label"].eq("review")].to_csv(review_path, index=False)
    updated[updated["ai_classification_label"].eq("non-AI")].to_csv(rejected_path, index=False)

    rows = [
        {"metric": "classified_input_rows", "value": "", "count": len(classified)},
        {"metric": "finished_human_review_rows", "value": "", "count": len(human_reviews)},
        {"metric": "finished_human_review_matched_rows", "value": "", "count": human_matched},
        {"metric": "finished_human_review_added_ai_rows", "value": "", "count": human_added_ai},
        {"metric": "finished_gemini_review_rows", "value": "", "count": len(gemini_reviews)},
        {"metric": "finished_gemini_review_matched_rows", "value": "", "count": gemini_matched},
        {"metric": "finished_gemini_review_added_ai_rows", "value": "", "count": gemini_added_ai},
        {"metric": "a2_prediction_rows", "value": "", "count": len(predictions)},
        {"metric": "matched_rows_updated", "value": "", "count": matched},
        {"metric": "a2_pending_prediction_added_ai_rows", "value": "", "count": pending_added_ai},
    ]
    for value, count in updated["ai_classification_label"].value_counts().items():
        rows.append({"metric": "updated_ai_classification_label", "value": value, "count": int(count)})
    for value, count in predictions["a2_production_decision"].value_counts().items():
        rows.append({"metric": "pending_a2_decision", "value": value, "count": int(count)})
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(summary_path, index=False)
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classified", type=Path, default=DEFAULT_CLASSIFIED)
    parser.add_argument("--human-reviews", type=Path, default=DEFAULT_HUMAN_REVIEWS)
    parser.add_argument("--gemini-reviews", type=Path, default=DEFAULT_GEMINI_REVIEWS)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_A2_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ai-only", type=Path, default=DEFAULT_AI_ONLY)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    updated = apply_predictions(
        classified_path=args.classified,
        human_reviews_path=args.human_reviews,
        gemini_reviews_path=args.gemini_reviews,
        predictions_path=args.predictions,
        output_path=args.output,
        ai_only_path=args.ai_only,
        review_path=args.review,
        rejected_path=args.rejected,
        summary_path=args.summary,
    )
    print(f"Wrote updated classified dataset: {args.output}")
    print(updated["ai_classification_label"].value_counts().to_string())


if __name__ == "__main__":
    main()
