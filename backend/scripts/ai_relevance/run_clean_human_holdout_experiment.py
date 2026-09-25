#!/usr/bin/env python3
"""Run a clean old-vs-new AI relevance experiment with a human holdout set."""

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


ORIGINAL_LABELS = (
    PROJECT_ROOT / "data/processed/ai/ai_llm_5000_predictions_openrouter_gemini_3_8_flash.csv"
)
GEMINI_1000 = PROJECT_ROOT / "data/Finished/gemini_review_1000_openrouter_predictions.csv"
HUMAN_800 = PROJECT_ROOT / "data/Finished/manual_review_800 - manual_review_800.csv"
HUMAN_500 = (
    PROJECT_ROOT
    / "data/final_ai_corpus_human_audit_sample_stratified - final_ai_corpus_human_audit_sample_stratified (1).csv"
)
CORPUS = PROJECT_ROOT / "data/processed/common/common_publications_final_2016_2026_ai_classified.csv"
OUTPUT_DIR = PROJECT_ROOT / "data/models/ai_relevance/clean_human_holdout"
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
    original_labels: Path = ORIGINAL_LABELS
    gemini_1000: Path = GEMINI_1000
    human_800: Path = HUMAN_800
    human_500: Path = HUMAN_500
    corpus: Path = CORPUS
    output_dir: Path = OUTPUT_DIR
    human_test_size: int = 500
    random_state: int = 42
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 3
    c_values: tuple[float, ...] = (0.1, 1.0, 10.0)
    class_weight: str | None = "balanced"
    max_iter: int = 5000
    cv_folds: int = 3
    scoring: str = "f1_macro"


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalize_label(value: Any) -> str:
    label = clean(value).upper().replace("-", "_").replace(" ", "_")
    return label if label in LABELS else ""


def norm_title(value: Any) -> str:
    return " ".join(clean(value).casefold().split())


def row_keys(record: pd.Series) -> set[str]:
    keys: set[str] = set()
    publication_key = clean(record.get("publication_key", ""))
    if publication_key:
        keys.add(publication_key.casefold())
    for column, prefix in (
        ("publication_id", "publication_id"),
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("source_record_id", "source_record_id"),
    ):
        value = clean(record.get(column, ""))
        if value:
            keys.add(f"{prefix}:{value.casefold()}")
    title = norm_title(record.get("title", ""))
    year = clean(record.get("publication_year", "")) or clean(record.get("publication_date", ""))[:4]
    if title:
        keys.add(f"title_year:{title}:{year}")
    return keys


def canonical_key(record: pd.Series) -> str:
    keys = sorted(row_keys(record))
    return keys[0] if keys else ""


def keyset(frame: pd.DataFrame) -> set[str]:
    keys: set[str] = set()
    for _, record in frame.iterrows():
        keys.update(row_keys(record))
    return keys


def build_lookup(corpus: pd.DataFrame) -> dict[str, dict[str, str]]:
    columns = [
        column
        for column in (
            "publication_id",
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
            "publication_date",
            "source_dataset",
            "source_institution_id",
            "source_record_id",
        )
        if column in corpus.columns
    ]
    lookup: dict[str, dict[str, str]] = {}
    for _, record in corpus.iterrows():
        payload = {column: clean(record.get(column, "")) for column in columns}
        for key in row_keys(record):
            lookup.setdefault(key, payload)
    return lookup


def attach_text(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in TEXT_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    out["text"] = combined_text(out.fillna(""), TEXT_COLUMNS)
    out["record_key"] = [canonical_key(record) for _, record in out.iterrows()]
    return out


def load_early_human(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["human_ai_label"].map(normalize_label)
    frame = frame[frame["label"].isin(LABELS)].copy()
    frame["label_source"] = "early_human_500"
    frame["source_priority"] = 2
    return attach_text(frame)


def load_late_human(path: Path, lookup: dict[str, dict[str, str]]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["human_review"].map(normalize_label)
    frame = frame[frame["label"].isin(LABELS)].copy()
    rows: list[dict[str, str]] = []
    for _, record in frame.iterrows():
        publication_key = clean(record.get("publication_key", "")).casefold()
        metadata = dict(lookup.get(publication_key, {}))
        metadata["publication_key"] = clean(record.get("publication_key", ""))
        rows.append(metadata)
    meta = pd.DataFrame(rows, index=frame.index)
    merged = frame.copy()
    for column in meta.columns:
        if column in merged.columns:
            continue
        merged[column] = meta[column]
    merged["label_source"] = "late_human_800"
    merged["source_priority"] = 1
    return attach_text(merged)


def deduplicate(frame: pd.DataFrame) -> pd.DataFrame:
    usable = frame[(frame["record_key"] != "") & (frame["text"] != "")].copy()
    usable = usable.sort_values(["record_key", "source_priority"], ascending=[True, False])
    return usable.drop_duplicates("record_key", keep="first").reset_index(drop=True)


def select_human_holdout(human_pool: pd.DataFrame, size: int, random_state: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(human_pool) < size:
        raise ValueError(f"Need {size} human rows, found {len(human_pool)}")
    test, train = train_test_split(
        human_pool,
        train_size=size,
        random_state=random_state,
        stratify=human_pool["label"],
    )
    return test.reset_index(drop=True), train.reset_index(drop=True)


def load_llm_labels(path: Path, source: str, priority: int) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    frame["label"] = frame["ai_llm_label"].map(normalize_label)
    frame = frame[
        (frame["ai_llm_status"].astype(str).str.strip() == "success")
        & frame["label"].isin(LABELS)
    ].copy()
    frame["label_source"] = source
    frame["source_priority"] = priority
    return attach_text(frame)


def remove_overlaps(frame: pd.DataFrame, forbidden_keys: set[str]) -> pd.DataFrame:
    keep = [not bool(row_keys(record) & forbidden_keys) for _, record in frame.iterrows()]
    return frame[keep].copy().reset_index(drop=True)


def train_model(frame: pd.DataFrame, config: Config) -> tuple[Any, dict[str, Any]]:
    cv_folds = min(config.cv_folds, int(frame["label"].value_counts().min()))
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
        {"svm__C": list(config.c_values)},
        cv=cv_folds,
        scoring=config.scoring,
        n_jobs=-1,
    )
    grid.fit(frame["text"], frame["label"])
    return grid.best_estimator_, {
        "rows": int(len(frame)),
        "label_counts": {k: int(v) for k, v in frame["label"].value_counts().items()},
        "source_counts": {k: int(v) for k, v in frame["label_source"].value_counts().items()},
        "best_c": float(grid.best_params_["svm__C"]),
        "best_cv_macro_f1": float(grid.best_score_),
    }


def ai_scores(model: Any, text: pd.Series) -> list[float]:
    classes = list(getattr(model, "classes_", ()))
    ai_index = classes.index("AI")
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(text)
        return [float(row[ai_index]) for row in probs]
    margins = model.decision_function(text)
    second = [1.0 / (1.0 + math.exp(-float(margin))) for margin in margins]
    return second if ai_index == 1 else [1.0 - score for score in second]


def evaluate(y_true: pd.Series, y_pred: Iterable[str]) -> dict[str, Any]:
    predictions = list(y_pred)
    return {
        "accuracy": float(accuracy_score(y_true, predictions)),
        "macro_f1": float(f1_score(y_true, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, predictions, average="weighted", zero_division=0)),
        "classification_report": classification_report(
            y_true, predictions, labels=list(LABELS), zero_division=0, output_dict=True
        ),
        "confusion_matrix_labels": list(LABELS),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=list(LABELS)).tolist(),
    }


def run(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    corpus = pd.read_csv(config.corpus, dtype=str, keep_default_na=False, low_memory=False)
    lookup = build_lookup(corpus)

    early_human = load_early_human(config.human_500)
    late_human = load_late_human(config.human_800, lookup)
    human_pool = deduplicate(pd.concat([early_human, late_human], ignore_index=True, sort=False))
    human_test, human_train = select_human_holdout(
        human_pool, config.human_test_size, config.random_state
    )
    hidden_keys = keyset(human_test)

    original = remove_overlaps(
        load_llm_labels(config.original_labels, "original_llm_5k", 1),
        hidden_keys,
    )
    gemini = remove_overlaps(
        load_llm_labels(config.gemini_1000, "gemini_finished_1000", 2),
        hidden_keys,
    )
    human_train_clean = remove_overlaps(human_train, hidden_keys)

    old_training = deduplicate(original)
    new_training = deduplicate(
        pd.concat([original, gemini, human_train_clean], ignore_index=True, sort=False)
    )

    old_model, old_train_summary = train_model(old_training, config)
    new_model, new_train_summary = train_model(new_training, config)

    old_path = config.output_dir / "clean_old_model.joblib"
    new_path = config.output_dir / "clean_new_model.joblib"
    joblib.dump(old_model, old_path)
    joblib.dump(new_model, new_path)

    old_pred = old_model.predict(human_test["text"])
    new_pred = new_model.predict(human_test["text"])
    predictions = human_test[
        [
            "record_key",
            "label",
            "label_source",
            "title",
            "doi",
            "openalex_id",
            "source_record_id",
            "text",
        ]
    ].copy()
    predictions["old_prediction"] = old_pred
    predictions["old_ai_score"] = [f"{score:.6f}" for score in ai_scores(old_model, human_test["text"])]
    predictions["new_prediction"] = new_pred
    predictions["new_ai_score"] = [f"{score:.6f}" for score in ai_scores(new_model, human_test["text"])]
    predictions["old_correct"] = predictions["label"].eq(predictions["old_prediction"])
    predictions["new_correct"] = predictions["label"].eq(predictions["new_prediction"])

    human_test_path = config.output_dir / "locked_human_test_set.csv"
    human_train_path = config.output_dir / "human_training_remainder.csv"
    old_training_path = config.output_dir / "clean_old_training_dataset.csv"
    new_training_path = config.output_dir / "clean_new_training_dataset.csv"
    predictions_path = config.output_dir / "clean_old_vs_new_human_test_predictions.csv"
    human_test.to_csv(human_test_path, index=False)
    human_train_clean.to_csv(human_train_path, index=False)
    old_training.to_csv(old_training_path, index=False)
    new_training.to_csv(new_training_path, index=False)
    predictions.to_csv(predictions_path, index=False)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
        "human_pool": {
            "early_human_rows": int(len(early_human)),
            "late_human_rows": int(len(late_human)),
            "deduplicated_human_pool_rows": int(len(human_pool)),
            "hidden_test_rows": int(len(human_test)),
            "human_training_remainder_rows": int(len(human_train_clean)),
            "hidden_test_label_counts": {
                k: int(v) for k, v in human_test["label"].value_counts().items()
            },
        },
        "old_model": {
            "path": str(old_path),
            "sha256": file_sha256(old_path),
            "training": old_train_summary,
            "human_test_metrics": evaluate(human_test["label"], old_pred),
        },
        "new_model": {
            "path": str(new_path),
            "sha256": file_sha256(new_path),
            "training": new_train_summary,
            "human_test_metrics": evaluate(human_test["label"], new_pred),
        },
        "artifacts": {
            "locked_human_test_set": str(human_test_path),
            "human_training_remainder": str(human_train_path),
            "clean_old_training_dataset": str(old_training_path),
            "clean_new_training_dataset": str(new_training_path),
            "predictions": str(predictions_path),
        },
    }
    summary_path = config.output_dir / "clean_human_holdout_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metrics_path = config.output_dir / "clean_human_holdout_metrics.txt"
    metrics_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def render_text(summary: dict[str, Any]) -> str:
    old = summary["old_model"]["human_test_metrics"]
    new = summary["new_model"]["human_test_metrics"]
    return "\n".join(
        [
            "Clean human-holdout old vs new AI relevance experiment",
            "",
            f"human_pool_rows: {summary['human_pool']['deduplicated_human_pool_rows']}",
            f"hidden_test_rows: {summary['human_pool']['hidden_test_rows']}",
            f"human_training_remainder_rows: {summary['human_pool']['human_training_remainder_rows']}",
            f"hidden_test_label_counts: {summary['human_pool']['hidden_test_label_counts']}",
            "",
            f"old_training_rows: {summary['old_model']['training']['rows']}",
            f"old_training_label_counts: {summary['old_model']['training']['label_counts']}",
            f"old_best_C: {summary['old_model']['training']['best_c']}",
            f"old_cv_macro_f1: {summary['old_model']['training']['best_cv_macro_f1']:.4f}",
            f"old_human_test_accuracy: {old['accuracy']:.4f}",
            f"old_human_test_macro_f1: {old['macro_f1']:.4f}",
            "",
            f"new_training_rows: {summary['new_model']['training']['rows']}",
            f"new_training_label_counts: {summary['new_model']['training']['label_counts']}",
            f"new_training_source_counts: {summary['new_model']['training']['source_counts']}",
            f"new_best_C: {summary['new_model']['training']['best_c']}",
            f"new_cv_macro_f1: {summary['new_model']['training']['best_cv_macro_f1']:.4f}",
            f"new_human_test_accuracy: {new['accuracy']:.4f}",
            f"new_human_test_macro_f1: {new['macro_f1']:.4f}",
            "",
            f"old_confusion_matrix_AI_NON_AI: {old['confusion_matrix']}",
            f"new_confusion_matrix_AI_NON_AI: {new['confusion_matrix']}",
            "",
            f"old_model_path: {summary['old_model']['path']}",
            f"new_model_path: {summary['new_model']['path']}",
            f"predictions: {summary['artifacts']['predictions']}",
        ]
    ) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--human-test-size", type=int, default=500)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run(
        Config(
            output_dir=args.output_dir,
            human_test_size=args.human_test_size,
            random_state=args.random_state,
        )
    )
    print(render_text(summary), end="")


if __name__ == "__main__":
    main()
