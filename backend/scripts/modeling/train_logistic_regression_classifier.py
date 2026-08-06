#!/usr/bin/env python3
"""Train a Logistic Regression classifier for publication metadata text.

Run from the backend folder:

    python scripts/modeling/train_logistic_regression_classifier.py

By default this trains a classifier that predicts ``primary_domain`` from the
publication title, abstract, and keywords in ``common_publications_final.csv``.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models"
DEFAULT_LABEL_COLUMN = "primary_domain"
DEFAULT_TEXT_COLUMNS = ["title", "abstract", "keywords"]


@dataclass(frozen=True)
class TrainingResult:
    model_output: Path
    metrics_output: Path
    input_rows: int
    usable_rows: int
    train_rows: int
    test_rows: int
    class_count: int
    accuracy: float


def parse_text_columns(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("at least one text column is required")
    return columns


def parse_document_frequency(value: str) -> int | float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid document frequency value: {value}") from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError("document frequency thresholds must be positive")
    if parsed < 1 or ("." in value and parsed == 1):
        return parsed
    if not parsed.is_integer():
        raise argparse.ArgumentTypeError(
            "document frequency values above 1 must be whole numbers"
        )
    return int(parsed)


def parse_class_weight(value: str) -> str | None:
    normalized = value.strip().casefold()
    if normalized == "none":
        return None
    if normalized == "balanced":
        return "balanced"
    raise argparse.ArgumentTypeError("class weight must be 'balanced' or 'none'")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "label"


def default_model_output(label_column: str) -> Path:
    return DEFAULT_MODEL_DIR / f"logistic_regression_{slugify(label_column)}.joblib"


def default_metrics_output(label_column: str) -> Path:
    return DEFAULT_MODEL_DIR / f"logistic_regression_{slugify(label_column)}_metrics.txt"


def combined_text(frame: pd.DataFrame, text_columns: Iterable[str]) -> pd.Series:
    text = frame[list(text_columns)].astype(str).agg(" ".join, axis=1)
    return text.str.replace(r"\s+", " ", regex=True).str.strip()


def load_training_frame(
    input_path: Path,
    *,
    label_column: str,
    text_columns: list[str],
    min_class_count: int,
    max_rows: int | None,
) -> tuple[pd.DataFrame, int, pd.Series]:
    usecols = [*text_columns, label_column]
    frame = pd.read_csv(
        input_path,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        nrows=max_rows,
    )
    input_rows = len(frame)

    training_frame = pd.DataFrame(
        {
            "text": combined_text(frame, text_columns),
            "label": frame[label_column].astype(str).str.strip(),
        }
    )
    training_frame = training_frame[
        (training_frame["text"] != "") & (training_frame["label"] != "")
    ]

    label_counts = training_frame["label"].value_counts()
    eligible_labels = label_counts[label_counts >= min_class_count].index
    training_frame = training_frame[training_frame["label"].isin(eligible_labels)]
    label_counts = training_frame["label"].value_counts()

    if training_frame.empty:
        raise ValueError(
            "No usable training rows found after dropping blank text/labels and "
            "small classes."
        )
    if len(label_counts) < 2:
        raise ValueError(
            "Logistic Regression needs at least two classes. Lower "
            "--min-class-count or choose another --label-column."
        )

    return training_frame, input_rows, label_counts


def build_pipeline(
    *,
    max_features: int,
    min_df: int | float,
    max_df: int | float,
    ngram_max: int,
    keep_stop_words: bool,
    class_weight: str | None,
    max_iter: int,
    random_state: int,
) -> Pipeline:
    if ngram_max < 1:
        raise ValueError("ngram_max must be at least 1")

    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    stop_words=None if keep_stop_words else "english",
                    strip_accents="unicode",
                    lowercase=True,
                    ngram_range=(1, ngram_max),
                    min_df=min_df,
                    max_df=max_df,
                    max_features=None if max_features <= 0 else max_features,
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    solver="saga",
                    max_iter=max_iter,
                    class_weight=class_weight,
                    random_state=random_state,
                ),
            ),
        ]
    )


def render_metrics(
    *,
    input_path: Path,
    label_column: str,
    text_columns: list[str],
    input_rows: int,
    usable_rows: int,
    train_rows: int,
    test_rows: int,
    label_counts: pd.Series,
    accuracy: float,
    report: str,
) -> str:
    lines = [
        "Logistic Regression publication classifier",
        "",
        f"input_csv: {input_path}",
        f"label_column: {label_column}",
        f"text_columns: {', '.join(text_columns)}",
        f"input_rows: {input_rows}",
        f"usable_rows: {usable_rows}",
        f"train_rows: {train_rows}",
        f"test_rows: {test_rows}",
        f"class_count: {len(label_counts)}",
        f"accuracy: {accuracy:.4f}",
        "",
        "Class distribution:",
    ]
    lines.extend(f"{label}: {count}" for label, count in label_counts.items())
    lines.extend(["", "Classification report:", report])
    return "\n".join(lines).rstrip() + "\n"


def write_label_counts(path: Path, label_counts: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["label", "count"])
        writer.writeheader()
        for label, count in label_counts.items():
            writer.writerow({"label": label, "count": int(count)})


def train_logistic_regression_classifier(
    *,
    input_path: Path = DEFAULT_INPUT,
    label_column: str = DEFAULT_LABEL_COLUMN,
    text_columns: list[str] | None = None,
    model_output: Path | None = None,
    metrics_output: Path | None = None,
    label_counts_output: Path | None = None,
    test_size: float = 0.2,
    random_state: int = 42,
    max_rows: int | None = None,
    min_class_count: int = 20,
    max_features: int = 50_000,
    min_df: int | float = 2,
    max_df: int | float = 0.95,
    ngram_max: int = 2,
    keep_stop_words: bool = False,
    class_weight: str | None = "balanced",
    max_iter: int = 1000,
) -> TrainingResult:
    text_columns = text_columns or DEFAULT_TEXT_COLUMNS
    model_output = model_output or default_model_output(label_column)
    metrics_output = metrics_output or default_metrics_output(label_column)
    label_counts_output = (
        label_counts_output
        or DEFAULT_MODEL_DIR / f"logistic_regression_{slugify(label_column)}_labels.csv"
    )

    if not 0 < test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    if min_class_count < 2:
        raise ValueError("min_class_count must be at least 2 for stratified splitting")

    training_frame, input_rows, label_counts = load_training_frame(
        input_path,
        label_column=label_column,
        text_columns=text_columns,
        min_class_count=min_class_count,
        max_rows=max_rows,
    )

    train_text, test_text, train_labels, test_labels = train_test_split(
        training_frame["text"],
        training_frame["label"],
        test_size=test_size,
        random_state=random_state,
        stratify=training_frame["label"],
    )

    pipeline = build_pipeline(
        max_features=max_features,
        min_df=min_df,
        max_df=max_df,
        ngram_max=ngram_max,
        keep_stop_words=keep_stop_words,
        class_weight=class_weight,
        max_iter=max_iter,
        random_state=random_state,
    )
    pipeline.fit(train_text, train_labels)

    predictions = pipeline.predict(test_text)
    accuracy = accuracy_score(test_labels, predictions)
    report = classification_report(test_labels, predictions, zero_division=0)

    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_output)

    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(
        render_metrics(
            input_path=input_path,
            label_column=label_column,
            text_columns=text_columns,
            input_rows=input_rows,
            usable_rows=len(training_frame),
            train_rows=len(train_text),
            test_rows=len(test_text),
            label_counts=label_counts,
            accuracy=accuracy,
            report=report,
        ),
        encoding="utf-8",
    )
    write_label_counts(label_counts_output, label_counts)

    return TrainingResult(
        model_output=model_output,
        metrics_output=metrics_output,
        input_rows=input_rows,
        usable_rows=len(training_frame),
        train_rows=len(train_text),
        test_rows=len(test_text),
        class_count=len(label_counts),
        accuracy=accuracy,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train a TF-IDF + Logistic Regression classifier from publication "
            "title, abstract, and keyword text."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input publication CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--label-column",
        default=DEFAULT_LABEL_COLUMN,
        help="Target label column to predict. Default: primary_domain",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns to combine. Default: title,abstract,keywords",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=None,
        help="Output .joblib model path. Default: data/models/logistic_regression_<label>.joblib",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Output metrics report path. Default: data/models/logistic_regression_<label>_metrics.txt",
    )
    parser.add_argument(
        "--label-counts-output",
        type=Path,
        default=None,
        help="Output label count CSV path. Default: data/models/logistic_regression_<label>_labels.csv",
    )
    parser.add_argument("--test-size", type=float, default=0.2, help="Held-out test fraction.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional row limit for quick experiments. Default: use all rows.",
    )
    parser.add_argument(
        "--min-class-count",
        type=int,
        default=20,
        help="Drop labels with fewer training examples. Default: 20",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=50_000,
        help="Maximum TF-IDF vocabulary size. Use 0 for no cap.",
    )
    parser.add_argument(
        "--min-df",
        type=parse_document_frequency,
        default=2,
        help="Minimum document frequency as a count or proportion. Default: 2",
    )
    parser.add_argument(
        "--max-df",
        type=parse_document_frequency,
        default=0.95,
        help="Maximum document frequency as a count or proportion. Default: 0.95",
    )
    parser.add_argument(
        "--ngram-max",
        type=int,
        default=2,
        help="Largest n-gram size to include. Default: 2",
    )
    parser.add_argument(
        "--keep-stop-words",
        action="store_true",
        help="Keep common English stop words instead of removing them.",
    )
    parser.add_argument(
        "--class-weight",
        type=parse_class_weight,
        default="balanced",
        help="Use 'balanced' or 'none'. Default: balanced",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=1000,
        help="Maximum Logistic Regression optimization iterations. Default: 1000",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = train_logistic_regression_classifier(
        input_path=args.input,
        label_column=args.label_column,
        text_columns=args.text_columns,
        model_output=args.model_output,
        metrics_output=args.metrics_output,
        label_counts_output=args.label_counts_output,
        test_size=args.test_size,
        random_state=args.random_state,
        max_rows=args.max_rows,
        min_class_count=args.min_class_count,
        max_features=args.max_features,
        min_df=args.min_df,
        max_df=args.max_df,
        ngram_max=args.ngram_max,
        keep_stop_words=args.keep_stop_words,
        class_weight=args.class_weight,
        max_iter=args.max_iter,
    )
    print(f"Trained Logistic Regression classifier on {result.usable_rows:,} rows.")
    print(f"Classes: {result.class_count:,}")
    print(f"Accuracy: {result.accuracy:.4f}")
    print(f"Model: {result.model_output}")
    print(f"Metrics: {result.metrics_output}")


if __name__ == "__main__":
    main()
