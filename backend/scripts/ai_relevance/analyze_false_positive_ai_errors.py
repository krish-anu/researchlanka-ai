#!/usr/bin/env python3
"""Create a manual-review package for false-positive AI predictions."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = PROJECT_ROOT / "data/models/ai_relevance/validated_human_selection_xgboost_fast"
DEFAULT_PREDICTIONS = DEFAULT_RUN_DIR / "selected_model_frozen_test_predictions.csv"
DEFAULT_TEST_SET = DEFAULT_RUN_DIR / "frozen_human_test_set.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN_DIR / "false_positive_analysis"


CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "iot_or_smart_system_without_clear_ai": (
        r"\biot\b",
        r"internet of things",
        r"\bsmart\b",
        r"embedded",
        r"sensor",
        r"wireless",
        r"automation",
        r"automated",
    ),
    "optimization_or_operations_research": (
        r"optimis",
        r"optimiz",
        r"optimal",
        r"linear programming",
        r"scheduling",
        r"routing",
        r"allocation",
        r"heuristic",
        r"metaheuristic",
    ),
    "statistical_prediction_or_forecasting": (
        r"forecast",
        r"predict",
        r"prediction",
        r"regression",
        r"time series",
        r"statistical",
        r"econometric",
    ),
    "signal_or_image_processing_without_clear_ai": (
        r"signal processing",
        r"image processing",
        r"filtering",
        r"segmentation",
        r"feature extraction",
        r"wavelet",
        r"fourier",
    ),
    "control_fuzzy_pid_or_mechatronics": (
        r"\bpid\b",
        r"fuzzy",
        r"controller",
        r"control system",
        r"model predictive control",
        r"mechatronic",
        r"robotic",
    ),
    "generic_intelligent_or_algorithmic_wording": (
        r"intelligent",
        r"algorithm",
        r"computational",
        r"decision support",
        r"expert system",
        r"knowledge based",
    ),
    "education_or_assessment_automation": (
        r"education",
        r"student",
        r"learning environment",
        r"assessment",
        r"answers",
        r"algebra",
        r"exam",
    ),
    "weak_or_missing_abstract": (
        r"^.{0,120}$",
    ),
}


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def combined_review_text(row: pd.Series) -> str:
    fields = [
        "title",
        "abstract",
        "keywords",
        "topics",
        "concepts",
        "primary_topic",
        "primary_subfield",
        "primary_field",
        "primary_domain",
        "text",
    ]
    return " ".join(clean(row.get(field, "")) for field in fields).strip()


def matched_terms(text: str, patterns: tuple[str, ...]) -> list[str]:
    lowered = text.casefold()
    terms: list[str] = []
    for pattern in patterns:
        if re.search(pattern, lowered):
            terms.append(pattern)
    return terms


def categorize(row: pd.Series) -> tuple[str, str]:
    text = combined_review_text(row)
    matches: list[str] = []
    for category, patterns in CATEGORY_PATTERNS.items():
        terms = matched_terms(text, patterns)
        if terms:
            matches.append(f"{category}({'; '.join(terms[:4])})")
    if not matches:
        return "needs_manual_pattern_review", ""
    primary = matches[0].split("(", 1)[0]
    return primary, " | ".join(matches)


def text_excerpt(row: pd.Series, limit: int = 500) -> str:
    text = combined_review_text(row)
    return text[:limit].rstrip()


def load_joined(predictions_path: Path, test_set_path: Path) -> pd.DataFrame:
    predictions = pd.read_csv(
        predictions_path, dtype=str, keep_default_na=False, low_memory=False
    )
    if not test_set_path.exists():
        return predictions
    test = pd.read_csv(test_set_path, dtype=str, keep_default_na=False, low_memory=False)
    metadata_columns = [
        column
        for column in (
            "record_key",
            "openalex_id",
            "source_record_id",
            "publication_date",
            "abstract",
            "keywords",
            "topics",
            "concepts",
            "primary_topic",
            "primary_subfield",
            "primary_field",
            "primary_domain",
            "source_dataset",
            "source_institution_id",
        )
        if column in test.columns and column not in predictions.columns
    ]
    if not metadata_columns:
        return predictions
    return predictions.merge(
        test[["record_key", *metadata_columns]],
        on="record_key",
        how="left",
        validate="one_to_one",
    )


def analyze_false_positives(
    *,
    predictions_path: Path = DEFAULT_PREDICTIONS,
    test_set_path: Path = DEFAULT_TEST_SET,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    joined = load_joined(predictions_path, test_set_path)
    false_positive = joined[
        (joined["label"] == "NON_AI") & (joined["prediction"] == "AI")
    ].copy()
    categories: list[str] = []
    evidence: list[str] = []
    excerpts: list[str] = []
    for _, row in false_positive.iterrows():
        category, matched = categorize(row)
        categories.append(category)
        evidence.append(matched)
        excerpts.append(text_excerpt(row))
    false_positive.insert(0, "error_category_auto", categories)
    false_positive.insert(1, "category_evidence_auto", evidence)
    false_positive.insert(2, "manual_error_category", "")
    false_positive.insert(3, "manual_notes", "")
    false_positive["text_excerpt"] = excerpts

    preferred_columns = [
        "error_category_auto",
        "category_evidence_auto",
        "manual_error_category",
        "manual_notes",
        "label",
        "prediction",
        "ai_score",
        "threshold",
        "title",
        "doi",
        "openalex_id",
        "source_record_id",
        "publication_date",
        "abstract",
        "keywords",
        "topics",
        "concepts",
        "primary_topic",
        "primary_subfield",
        "primary_field",
        "primary_domain",
        "text_excerpt",
        "record_key",
    ]
    columns = [column for column in preferred_columns if column in false_positive.columns]
    review = false_positive[columns].sort_values(
        ["error_category_auto", "ai_score"], ascending=[True, False]
    )
    cases_path = output_dir / "false_positive_ai_cases.csv"
    review.to_csv(cases_path, index=False)

    counts = Counter(review["error_category_auto"])
    summary = pd.DataFrame(
        [{"error_category_auto": key, "count": value} for key, value in counts.most_common()]
    )
    summary_path = output_dir / "false_positive_category_summary.csv"
    summary.to_csv(summary_path, index=False)

    markdown = [
        "# False-Positive AI Error Analysis",
        "",
        f"False-positive rows: {len(review)}",
        "",
        "## Auto Category Counts",
        "",
    ]
    for _, row in summary.iterrows():
        markdown.append(f"- {row['error_category_auto']}: {row['count']}")
    markdown.extend(
        [
            "",
            "## Files",
            "",
            f"- Cases: `{cases_path}`",
            f"- Summary: `{summary_path}`",
            "",
            "Auto categories are heuristic starting points. Fill "
            "`manual_error_category` and `manual_notes` during review.",
        ]
    )
    (output_dir / "false_positive_analysis.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
    return review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--test-set", type=Path, default=DEFAULT_TEST_SET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    review = analyze_false_positives(
        predictions_path=args.predictions,
        test_set_path=args.test_set,
        output_dir=args.output_dir,
    )
    print(f"False-positive AI rows: {len(review)}")
    print(review["error_category_auto"].value_counts().to_string())
    print(f"Output: {args.output_dir}")


if __name__ == "__main__":
    main()
