"""Hard-negative training examples from human-rejected model false positives."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from src.ai_relevance.borderline import borderline_false_positive_assessment
from src.modeling.linear_svm_training import combined_text


TEXT_COLUMNS = (
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
)

OUTPUT_COLUMNS = (
    "record_key",
    "label",
    "label_source",
    "hard_negative",
    "hard_negative_category",
    "hard_negative_evidence",
    *TEXT_COLUMNS,
    "doi",
    "openalex_id",
    "source_record_id",
    "publication_key",
)


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalize_ai_label(value: Any) -> str:
    label = clean(value).casefold().replace("_", "-").replace(" ", "-")
    if label in {"ai", "artificial-intelligence", "yes", "true", "1"}:
        return "AI"
    if label in {"non-ai", "nonai", "not-ai", "no", "false", "0"}:
        return "NON_AI"
    if label in {"review", "uncertain", "unknown"}:
        return "REVIEW"
    return ""


def is_model_ai_human_non_ai(record: Mapping[str, Any]) -> bool:
    model_label = normalize_ai_label(
        record.get("original_ai_label")
        or record.get("classifier_decision")
        or record.get("ai_classification_label")
        or record.get("reported_classifier_decision")
    )
    human_status = clean(record.get("review_status")).casefold()
    human_label = normalize_ai_label(
        record.get("human_label")
        or record.get("human_review")
        or record.get("final_human_label")
    )
    return model_label == "AI" and (
        human_status == "human_rejected" or human_label == "NON_AI"
    )


def hard_negative_record_key(record: Mapping[str, Any], fallback: int | str) -> str:
    for column, prefix in (
        ("publication_key", "publication"),
        ("record_key", "record"),
        ("doi", "doi"),
        ("openalex_id", "openalex"),
        ("source_record_id", "source"),
    ):
        value = clean(record.get(column))
        if value:
            return f"{prefix}:{value.casefold()}"
    title = clean(record.get("title")).casefold()
    year = clean(record.get("publication_year"))
    if title:
        return f"title_year:{' '.join(title.split())}:{year}"
    return f"hard_negative_row:{fallback}"


def hard_negative_row(record: Mapping[str, Any], fallback: int | str) -> dict[str, Any]:
    assessment = borderline_false_positive_assessment(record)
    return {
        "record_key": hard_negative_record_key(record, fallback),
        "label": "NON_AI",
        "label_source": clean(record.get("label_source"))
        or "human_rejected_false_positive",
        "hard_negative": True,
        "hard_negative_category": clean(record.get("hard_negative_category"))
        or clean(record.get("manual_error_category"))
        or clean(record.get("error_category"))
        or assessment.risk_category
        or "human_rejected_model_ai",
        "hard_negative_evidence": clean(record.get("hard_negative_evidence"))
        or clean(record.get("reviewer_notes"))
        or clean(record.get("resolution_note"))
        or clean(record.get("feedback_detail"))
        or "; ".join(assessment.risk_patterns),
        **{column: clean(record.get(column)) for column in TEXT_COLUMNS},
        "doi": clean(record.get("doi")),
        "openalex_id": clean(record.get("openalex_id")),
        "source_record_id": clean(record.get("source_record_id")),
        "publication_key": clean(record.get("publication_key")),
    }


def build_hard_negative_frame(records: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows = [
        hard_negative_row(record, index)
        for index, record in enumerate(records)
        if is_model_ai_human_non_ai(record) or clean(record.get("hard_negative")).casefold() in {"true", "1", "yes"}
    ]
    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    return frame.drop_duplicates("record_key", keep="first").reset_index(drop=True)


def load_hard_negative_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    if "record_key" not in frame.columns:
        frame["record_key"] = [
            hard_negative_record_key(record, index)
            for index, record in enumerate(frame.to_dict("records"))
        ]
    if "label" in frame.columns:
        frame = frame[frame["label"].map(normalize_ai_label).eq("NON_AI")].copy()
    else:
        frame["label"] = "NON_AI"
    if "hard_negative" not in frame.columns:
        frame["hard_negative"] = True
    if "label_source" not in frame.columns:
        frame["label_source"] = "human_rejected_false_positive"
    for column in TEXT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["text"] = combined_text(frame.fillna(""), TEXT_COLUMNS)
    frame = frame[frame["text"] != ""].copy()
    frame["label"] = "NON_AI"
    return frame
