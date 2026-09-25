#!/usr/bin/env python3
"""Train an updated AI relevance model from finished reviews and compare old/new.

The flow is:

1. Load the original 5k LLM-labelled training set.
2. Add finished manual-review labels and finished Gemini labels.
3. Deduplicate with label-source priority: human > Gemini > original.
4. Train a new TF-IDF + LinearSVC model.
5. Evaluate the old and new models on the same hidden test split.
6. Predict the remaining pending-review rows with the new model.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV, train_test_split


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.artifacts import file_sha256  # noqa: E402
from src.modeling.linear_svm_training import build_pipeline, combined_text  # noqa: E402


DEFAULT_ORIGINAL_LABELS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_5000_predictions_openrouter_gemini_3_8_flash.csv"
)
DEFAULT_MANUAL_REVIEWS = (
    PROJECT_ROOT / "data" / "Finished" / "manual_review_800 - manual_review_800.csv"
)
DEFAULT_GEMINI_REVIEWS = (
    PROJECT_ROOT / "data" / "Finished" / "gemini_review_1000_openrouter_predictions.csv"
)
DEFAULT_REMAINING = (
    PROJECT_ROOT / "data" / "pending-review-split" / "model_predict_remaining_1207.csv"
)
DEFAULT_CORPUS = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_OLD_MODEL = (
    PROJECT_ROOT / "data" / "models" / "ai_relevance" / "ai_relevance_linear_svm.joblib"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "models" / "ai_relevance" / "updated_with_reviews"
DEFAULT_REMAINING_OUTPUT = (
    PROJECT_ROOT / "data" / "processed" / "ai" / "model_predict_remaining_1207_updated_model_predictions.csv"
)
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
LABELS = ("AI", "NON_AI")


@dataclass(frozen=True)
class Config:
    original_labels: Path = DEFAULT_ORIGINAL_LABELS
    manual_reviews: Path = DEFAULT_MANUAL_REVIEWS
    gemini_reviews: Path = DEFAULT_GEMINI_REVIEWS
    remaining_pending: Path = DEFAULT_REMAINING
    corpus: Path = DEFAULT_CORPUS
    old_model: Path = DEFAULT_OLD_MODEL
    output_dir: Path = DEFAULT_OUTPUT_DIR
    remaining_output: Path = DEFAULT_REMAINING_OUTPUT
    random_state: int = 42
    test_size: float = 0.2
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 3
    c_values: tuple[float, ...] = (0.1, 1.0, 10.0)
    class_weight: str | None = "balanced"
    max_iter: int = 5000
    cv_folds: int = 3
    scoring: str = "f1_macro"


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalize_label(value: Any) -> str:
    label = clean_text(value).upper().replace("-", "_").replace(" ", "_")
    if label in {"AI", "NON_AI", "REVIEW"}:
        return label
    return ""


def key_from_record(record: pd.Series) -> str:
    for column, prefix in (
        ("publication_id", "publication_id"),
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("source_record_id", "source_record_id"),
    ):
        if column in record:
            value = clean_text(record[column])
            if value:
                return f"{prefix}:{value.casefold()}"
    title = clean_text(record.get("title", "")).casefold()
    year = clean_text(record.get("publication_year", ""))
    if title:
        return f"title_year:{' '.join(title.split())}:{year}"
    return ""


def row_keys(record: pd.Series) -> set[str]:
    keys: set[str] = set()
    for column, prefix in (
        ("publication_id", "publication_id"),
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("source_record_id", "source_record_id"),
    ):
        value = clean_text(record.get(column, ""))
        if value:
            keys.add(f"{prefix}:{value.casefold()}")
    title = clean_text(record.get("title", "")).casefold()
    year = clean_text(record.get("publication_year", ""))
    if title:
        keys.add(f"title_year:{' '.join(title.split())}:{year}")
    return keys


def normalize_review_key(value: Any) -> str:
    text = clean_text(value)
    if ":" not in text:
        return text.casefold()
    prefix, suffix = text.split(":", 1)
    return f"{prefix.strip().casefold()}:{suffix.strip().casefold()}"


def load_corpus_metadata(path: Path) -> pd.DataFrame:
    corpus = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    corpus["record_key"] = [key_from_record(record) for _, record in corpus.iterrows()]
    return corpus


def build_metadata_lookup(corpus: pd.DataFrame) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    selected_columns = [
        column
        for column in (
            "openalex_id",
            "doi",
            "title",
            "abstract",
            "keywords",
            "topics",
            "concepts",
            "primary_topic",
            "primary_subfield",
            "primary_field",
            "primary_domain",
            "publication_year",
            "source_dataset",
            "source_institution_id",
            "source_record_id",
        )
        if column in corpus.columns
    ]
    for _, record in corpus.iterrows():
        payload = {column: clean_text(record.get(column, "")) for column in selected_columns}
        payload["record_key"] = clean_text(record.get("record_key", ""))
        for key in row_keys(record):
            lookup.setdefault(key, payload)
    return lookup


def attach_text(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    for column in TEXT_COLUMNS:
        if column not in prepared.columns:
            prepared[column] = ""
    prepared["text"] = combined_text(prepared.fillna(""), TEXT_COLUMNS)
    return prepared


def load_original_labels(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["ai_llm_label"].map(normalize_label)
    frame = frame[
        (frame["ai_llm_status"].astype(str).str.strip() == "success")
        & frame["label"].isin(LABELS)
    ].copy()
    frame["label_source"] = "original_llm_5k"
    frame["source_priority"] = 1
    frame["record_key"] = [key_from_record(record) for _, record in frame.iterrows()]
    return attach_text(frame)


def load_gemini_reviews(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["ai_llm_label"].map(normalize_label)
    frame = frame[
        (frame["ai_llm_status"].astype(str).str.strip() == "success")
        & frame["label"].isin(LABELS)
    ].copy()
    frame["label_source"] = "gemini_finished_1000"
    frame["source_priority"] = 2
    frame["record_key"] = [key_from_record(record) for _, record in frame.iterrows()]
    return attach_text(frame)


def load_manual_reviews(path: Path, metadata_lookup: dict[str, dict[str, str]]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["human_review"].map(normalize_label)
    frame = frame[frame["label"].isin(LABELS)].copy()
    metadata_rows: list[dict[str, str]] = []
    for _, record in frame.iterrows():
        key = normalize_review_key(record.get("publication_key", ""))
        metadata = dict(metadata_lookup.get(key, {}))
        metadata["record_key"] = metadata.get("record_key") or key
        metadata_rows.append(metadata)
    metadata_frame = pd.DataFrame(metadata_rows, index=frame.index)
    merged = frame.copy()
    for column in metadata_frame.columns:
        if column in merged.columns and column != "record_key":
            continue
        merged[column] = metadata_frame[column]
    merged["label_source"] = "human_finished_800"
    merged["source_priority"] = 3
    return attach_text(merged)


def deduplicate_training_rows(parts: Iterable[pd.DataFrame]) -> pd.DataFrame:
    frame = pd.concat(list(parts), ignore_index=True, sort=False)
    frame = frame[(frame["record_key"] != "") & (frame["text"] != "")].copy()
    frame = frame.sort_values(["record_key", "source_priority"], ascending=[True, False])
    return frame.drop_duplicates("record_key", keep="first").reset_index(drop=True)


def evaluate_predictions(y_true: pd.Series, y_pred: Iterable[str]) -> dict[str, Any]:
    predictions = list(y_pred)
    return {
        "accuracy": float(accuracy_score(y_true, predictions)),
        "macro_f1": float(f1_score(y_true, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(y_true, predictions, average="weighted", zero_division=0)
        ),
        "classification_report": classification_report(
            y_true, predictions, labels=list(LABELS), zero_division=0, output_dict=True
        ),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=list(LABELS)).tolist(),
    }


def evaluate_by_source(
    frame: pd.DataFrame,
    *,
    old_predictions: Iterable[str],
    new_predictions: Iterable[str],
) -> dict[str, Any]:
    scored = frame[["label_source", "label"]].copy()
    scored["old_prediction"] = list(old_predictions)
    scored["new_prediction"] = list(new_predictions)
    metrics: dict[str, Any] = {}
    for source, group in scored.groupby("label_source"):
        metrics[str(source)] = {
            "rows": int(len(group)),
            "old_model": evaluate_predictions(group["label"], group["old_prediction"]),
            "new_model": evaluate_predictions(group["label"], group["new_prediction"]),
        }
    new_review = scored[scored["label_source"] != "original_llm_5k"]
    if not new_review.empty:
        metrics["finished_reviews_only"] = {
            "rows": int(len(new_review)),
            "old_model": evaluate_predictions(
                new_review["label"], new_review["old_prediction"]
            ),
            "new_model": evaluate_predictions(
                new_review["label"], new_review["new_prediction"]
            ),
        }
    return metrics


def ai_scores(model: Any, text: pd.Series) -> list[float]:
    if text.empty:
        return []
    classes = list(getattr(model, "classes_", ()))
    try:
        ai_index = classes.index("AI")
    except ValueError as exc:
        raise ValueError("Model classes do not include AI.") from exc
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(text)
        return [float(row[ai_index]) for row in probabilities]
    margins = model.decision_function(text)
    scores_for_second_class = [1.0 / (1.0 + math.exp(-float(margin))) for margin in margins]
    if ai_index == 1:
        return scores_for_second_class
    return [1.0 - score for score in scores_for_second_class]


def train_and_compare(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.remaining_output.parent.mkdir(parents=True, exist_ok=True)

    corpus = load_corpus_metadata(config.corpus)
    metadata_lookup = build_metadata_lookup(corpus)
    original = load_original_labels(config.original_labels)
    manual = load_manual_reviews(config.manual_reviews, metadata_lookup)
    gemini = load_gemini_reviews(config.gemini_reviews)
    training = deduplicate_training_rows([original, gemini, manual])

    train_frame, test_frame = train_test_split(
        training,
        test_size=config.test_size,
        random_state=config.random_state,
        stratify=training["label"],
    )

    cv_folds = min(config.cv_folds, int(train_frame["label"].value_counts().min()))
    pipeline = build_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        random_state=config.random_state,
    )
    grid = GridSearchCV(
        pipeline,
        param_grid={"svm__C": list(config.c_values)},
        cv=cv_folds,
        scoring=config.scoring,
        n_jobs=-1,
    )
    grid.fit(train_frame["text"], train_frame["label"])

    new_test_pred = grid.best_estimator_.predict(test_frame["text"])
    old_model = joblib.load(config.old_model)
    old_test_pred = old_model.predict(test_frame["text"])

    final_model = build_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        random_state=config.random_state,
        c_value=float(grid.best_params_["svm__C"]),
    )
    final_model.fit(training["text"], training["label"])

    model_path = config.output_dir / "ai_relevance_linear_svm_updated_with_reviews.joblib"
    joblib.dump(final_model, model_path)

    comparison_rows = test_frame[
        ["record_key", "label", "label_source", "text"]
    ].copy()
    comparison_rows["old_model_prediction"] = old_test_pred
    comparison_rows["new_model_prediction"] = new_test_pred
    comparison_rows["old_model_correct"] = comparison_rows["label"].eq(
        comparison_rows["old_model_prediction"]
    )
    comparison_rows["new_model_correct"] = comparison_rows["label"].eq(
        comparison_rows["new_model_prediction"]
    )
    comparison_path = config.output_dir / "old_vs_updated_model_test_predictions.csv"
    comparison_rows.to_csv(comparison_path, index=False)

    remaining_raw = pd.read_csv(
        config.remaining_pending, dtype=str, keep_default_na=False, low_memory=False
    )
    remaining_rows: list[dict[str, Any]] = []
    for index, record in remaining_raw.iterrows():
        key = normalize_review_key(record.get("publication_key", ""))
        metadata = dict(metadata_lookup.get(key, {}))
        metadata["record_key"] = metadata.get("record_key") or key
        metadata["publication_key"] = clean_text(record.get("publication_key", ""))
        metadata["source_row"] = index
        metadata["original_ai_label"] = clean_text(record.get("original_ai_label", ""))
        metadata["original_ai_confidence"] = clean_text(record.get("original_ai_confidence", ""))
        remaining_rows.append(metadata)
    remaining = attach_text(pd.DataFrame(remaining_rows))
    remaining["updated_model_prediction"] = final_model.predict(remaining["text"])
    remaining["updated_model_ai_score"] = [
        f"{score:.6f}" for score in ai_scores(final_model, remaining["text"])
    ]
    remaining["updated_model_path"] = str(model_path)
    remaining["label_source"] = "updated_model_predicted"
    output_columns = [
        "source_row",
        "record_key",
        "publication_key",
        "updated_model_prediction",
        "updated_model_ai_score",
        "updated_model_path",
        "label_source",
        "original_ai_label",
        "original_ai_confidence",
        *[column for column in TEXT_COLUMNS if column in remaining.columns],
        "publication_year",
        "source_dataset",
        "source_institution_id",
        "source_record_id",
        "openalex_id",
        "doi",
    ]
    output_columns = list(dict.fromkeys(column for column in output_columns if column in remaining.columns))
    remaining[output_columns].to_csv(config.remaining_output, index=False)

    updated_training_path = config.output_dir / "updated_training_dataset.csv"
    training.drop(columns=["source_priority"], errors="ignore").to_csv(
        updated_training_path, index=False
    )

    old_metrics = evaluate_predictions(test_frame["label"], old_test_pred)
    new_metrics = evaluate_predictions(test_frame["label"], new_test_pred)
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {key: str(value) if isinstance(value, Path) else value for key, value in asdict(config).items()},
        "input_counts": {
            "original_binary_rows": int(len(original)),
            "gemini_binary_rows": int(len(gemini)),
            "manual_binary_rows": int(len(manual)),
            "updated_training_rows_after_dedup": int(len(training)),
            "train_rows": int(len(train_frame)),
            "test_rows": int(len(test_frame)),
            "remaining_predicted_rows": int(len(remaining)),
        },
        "label_counts": {
            "updated_training": {
                str(label): int(count) for label, count in training["label"].value_counts().items()
            },
            "test": {
                str(label): int(count) for label, count in test_frame["label"].value_counts().items()
            },
            "remaining_predictions": {
                str(label): int(count)
                for label, count in remaining["updated_model_prediction"].value_counts().items()
            },
        },
        "new_model": {
            "path": str(model_path),
            "sha256": file_sha256(model_path),
            "best_c": float(grid.best_params_["svm__C"]),
            "best_cv_macro_f1": float(grid.best_score_),
            "test_metrics": new_metrics,
        },
        "old_model": {
            "path": str(config.old_model),
            "sha256": file_sha256(config.old_model),
            "test_metrics_on_same_split": old_metrics,
        },
        "old_vs_new_by_label_source": evaluate_by_source(
            test_frame,
            old_predictions=old_test_pred,
            new_predictions=new_test_pred,
        ),
        "comparison_note": (
            "The mixed same-split comparison includes original_llm_5k rows. "
            "Those rows are from the old model's training source, so the "
            "finished_reviews_only and per-source metrics are the fairer evidence "
            "for newly reviewed labels."
        ),
        "artifacts": {
            "updated_training_dataset": str(updated_training_path),
            "old_vs_updated_test_predictions": str(comparison_path),
            "remaining_predictions": str(config.remaining_output),
            "summary": str(config.output_dir / "updated_model_comparison_summary.json"),
        },
    }
    summary_path = config.output_dir / "updated_model_comparison_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metrics_path = config.output_dir / "updated_model_metrics.txt"
    metrics_path.write_text(render_metrics_text(summary), encoding="utf-8")
    return summary


def render_metrics_text(summary: dict[str, Any]) -> str:
    old = summary["old_model"]["test_metrics_on_same_split"]
    new = summary["new_model"]["test_metrics"]
    lines = [
        "Updated AI relevance model with finished reviews",
        "",
        f"updated_training_rows_after_dedup: {summary['input_counts']['updated_training_rows_after_dedup']}",
        f"train_rows: {summary['input_counts']['train_rows']}",
        f"test_rows: {summary['input_counts']['test_rows']}",
        f"remaining_predicted_rows: {summary['input_counts']['remaining_predicted_rows']}",
        f"best_C: {summary['new_model']['best_c']}",
        f"best_cv_macro_f1: {summary['new_model']['best_cv_macro_f1']:.4f}",
        "",
        "Same hidden test split comparison:",
        f"old_accuracy: {old['accuracy']:.4f}",
        f"old_macro_f1: {old['macro_f1']:.4f}",
        f"new_accuracy: {new['accuracy']:.4f}",
        f"new_macro_f1: {new['macro_f1']:.4f}",
        "",
        "Finished reviews only comparison:",
        (
            "old_accuracy: "
            f"{summary['old_vs_new_by_label_source']['finished_reviews_only']['old_model']['accuracy']:.4f}"
        ),
        (
            "old_macro_f1: "
            f"{summary['old_vs_new_by_label_source']['finished_reviews_only']['old_model']['macro_f1']:.4f}"
        ),
        (
            "new_accuracy: "
            f"{summary['old_vs_new_by_label_source']['finished_reviews_only']['new_model']['accuracy']:.4f}"
        ),
        (
            "new_macro_f1: "
            f"{summary['old_vs_new_by_label_source']['finished_reviews_only']['new_model']['macro_f1']:.4f}"
        ),
        "",
        "Note: mixed comparison includes original_llm_5k rows from the old model training source.",
        "",
        f"new_model_path: {summary['new_model']['path']}",
        f"remaining_predictions: {summary['artifacts']['remaining_predictions']}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train updated AI relevance model from finished review data."
    )
    parser.add_argument("--original-labels", type=Path, default=DEFAULT_ORIGINAL_LABELS)
    parser.add_argument("--manual-reviews", type=Path, default=DEFAULT_MANUAL_REVIEWS)
    parser.add_argument("--gemini-reviews", type=Path, default=DEFAULT_GEMINI_REVIEWS)
    parser.add_argument("--remaining-pending", type=Path, default=DEFAULT_REMAINING)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--old-model", type=Path, default=DEFAULT_OLD_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--remaining-output", type=Path, default=DEFAULT_REMAINING_OUTPUT)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = train_and_compare(
        Config(
            original_labels=args.original_labels,
            manual_reviews=args.manual_reviews,
            gemini_reviews=args.gemini_reviews,
            remaining_pending=args.remaining_pending,
            corpus=args.corpus,
            old_model=args.old_model,
            output_dir=args.output_dir,
            remaining_output=args.remaining_output,
            test_size=args.test_size,
            random_state=args.random_state,
        )
    )
    print(render_metrics_text(summary), end="")


if __name__ == "__main__":
    main()
