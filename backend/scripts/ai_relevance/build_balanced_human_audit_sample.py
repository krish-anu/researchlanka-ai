#!/usr/bin/env python3
"""Build a balanced hidden human-audit sample from the full classified corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_ai_classified.csv"
)
DEFAULT_PREVIOUS_AUDIT = (
    PROJECT_ROOT
    / "data"
    / "final_ai_corpus_human_audit_sample_stratified - final_ai_corpus_human_audit_sample_stratified (1).csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "full_corpus_balanced_human_audit_sample_600.csv"
)
DEFAULT_SUMMARY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "full_corpus_balanced_human_audit_sample_600_summary.csv"
)


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalized_title(value: Any) -> str:
    return " ".join(clean_text(value).casefold().split())


def record_keys(record: pd.Series) -> set[str]:
    keys: set[str] = set()
    for column, prefix in (
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("source_record_id", "source_record_id"),
    ):
        value = clean_text(record.get(column, ""))
        if value:
            keys.add(f"{prefix}:{value.casefold()}")
    title = normalized_title(record.get("title", ""))
    year = clean_text(record.get("publication_year", ""))
    if not year:
        year = clean_text(record.get("publication_date", ""))[:4]
    if title:
        keys.add(f"title_year:{title}:{year}")
    return keys


def previous_audit_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    keys: set[str] = set()
    for _, record in frame.iterrows():
        keys.update(record_keys(record))
    return keys


def has_previous_overlap(record: pd.Series, previous_keys: set[str]) -> bool:
    return bool(record_keys(record) & previous_keys)


def sample_group(
    frame: pd.DataFrame,
    *,
    group_name: str,
    sample_size: int,
    random_state: int,
) -> pd.DataFrame:
    if len(frame) < sample_size:
        raise ValueError(
            f"Not enough rows for {group_name}: need {sample_size}, found {len(frame)}"
        )
    sampled = frame.sample(n=sample_size, random_state=random_state).copy()
    sampled.insert(0, "audit_group", group_name)
    return sampled


def doi_url(row: pd.Series) -> str:
    doi = clean_text(row.get("doi", ""))
    return f"https://doi.org/{doi}" if doi else ""


def build_sample(
    *,
    input_path: Path = DEFAULT_INPUT,
    previous_audit_path: Path = DEFAULT_PREVIOUS_AUDIT,
    output_path: Path = DEFAULT_OUTPUT,
    summary_path: Path = DEFAULT_SUMMARY,
    sample_size_per_group: int = 200,
    random_state: int = 42,
) -> pd.DataFrame:
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False, low_memory=False)
    confidence = pd.to_numeric(frame["ai_classification_confidence"], errors="coerce")
    frame = frame.assign(_ai_confidence_numeric=confidence)

    previous_keys = previous_audit_keys(previous_audit_path)
    if previous_keys:
        overlap_mask = frame.apply(
            lambda row: has_previous_overlap(row, previous_keys), axis=1
        )
        frame = frame[~overlap_mask].copy()

    label = frame["ai_classification_label"].astype(str).str.strip().str.casefold()
    high_confidence = frame[(label == "ai") & (frame["_ai_confidence_numeric"] >= 0.85)]
    borderline = frame[
        (frame["_ai_confidence_numeric"] >= 0.40)
        & (frame["_ai_confidence_numeric"] < 0.85)
    ]
    predicted_non_ai = frame[
        (label == "non-ai") | (frame["_ai_confidence_numeric"] < 0.40)
    ]

    sampled = pd.concat(
        [
            sample_group(
                high_confidence,
                group_name="High-confidence AI",
                sample_size=sample_size_per_group,
                random_state=random_state,
            ),
            sample_group(
                borderline,
                group_name="Borderline AI / review",
                sample_size=sample_size_per_group,
                random_state=random_state + 1,
            ),
            sample_group(
                predicted_non_ai,
                group_name="Predicted NON_AI",
                sample_size=sample_size_per_group,
                random_state=random_state + 2,
            ),
        ],
        ignore_index=True,
        sort=False,
    )

    sampled.insert(1, "human_ai_label", "")
    sampled.insert(2, "human_lk_relevance_label", "")
    sampled.insert(3, "human_notes", "")
    if "doi_url" not in sampled.columns:
        sampled.insert(4, "doi_url", [doi_url(row) for _, row in sampled.iterrows()])

    preferred_columns = [
        "audit_group",
        "human_ai_label",
        "human_lk_relevance_label",
        "human_notes",
        "doi_url",
        "openalex_id",
        "url",
        "source_record_id",
        "doi",
        "title",
        "abstract",
        "keywords",
        "topics",
        "concepts",
        "publication_date",
        "type",
        "authors",
        "author_affiliations",
        "sri_lankan_authors",
        "institutions",
        "sri_lankan_institutions",
        "countries",
        "ownership_decision",
        "ownership_confidence",
        "ownership_reason",
        "ownership_evidence",
        "source_dataset",
        "source_institution_id",
        "ai_classification_label",
        "ai_classification_confidence",
        "ai_classification_model",
        "ai_classification_reason",
        "primary_topic",
        "primary_subfield",
        "primary_field",
        "primary_domain",
        "license",
        "license_url",
        "oa_status",
    ]
    output_columns = [
        column for column in preferred_columns if column in sampled.columns
    ]
    output_frame = sampled[output_columns].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_frame.to_csv(output_path, index=False)

    summary = pd.DataFrame(
        [
            {
                "metric": "input_rows",
                "value": len(pd.read_csv(input_path, usecols=["ai_classification_label"])),
            },
            {"metric": "previous_audit_key_count", "value": len(previous_keys)},
            {"metric": "eligible_high_confidence_ai", "value": len(high_confidence)},
            {"metric": "eligible_borderline_ai_review", "value": len(borderline)},
            {"metric": "eligible_predicted_non_ai", "value": len(predicted_non_ai)},
            {"metric": "sampled_rows", "value": len(output_frame)},
        ]
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False)
    return output_frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a balanced 600-row human audit sample."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--previous-audit", type=Path, default=DEFAULT_PREVIOUS_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--sample-size-per-group", type=int, default=200)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = build_sample(
        input_path=args.input,
        previous_audit_path=args.previous_audit,
        output_path=args.output,
        summary_path=args.summary,
        sample_size_per_group=args.sample_size_per_group,
        random_state=args.random_state,
    )
    print(f"Wrote {len(output)} rows to {args.output}")
    print(output["audit_group"].value_counts().to_string())


if __name__ == "__main__":
    main()
