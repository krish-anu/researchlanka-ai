"""Common evaluation pipeline for publication classifiers.

One place where predictions turn into numbers, whichever model family produced
them. Every training run routes through :func:`evaluate_predictions`, so a
Logistic Regression run and a Multinomial Naive Bayes run are scored the same
way and their artifacts line up column for column -- which is the only way a
baseline comparison means anything.

Three things come out of an evaluation, alongside the headline metrics:

* a **confusion matrix** in wide form, one row per true label and one column per
  predicted label, plus that row's support and accuracy;
* **per-class results** -- precision, recall, F1 and support for every class,
  each with the label it is most often confused with, which is what turns a low
  F1 into something actionable;
* a machine-readable summary for tracking runs over time.

The pipeline can start from either end: a predictions CSV that a training run
already wrote, or a saved model plus the dataset to score. Both paths produce
identical artifacts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from src.modeling.artifacts import write_csv_artifact, write_json_artifact


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVALUATION_DIR = PROJECT_ROOT / "data" / "models"

PER_CLASS_FIELDNAMES = [
    "label",
    "support",
    "predicted",
    "correct",
    "precision",
    "recall",
    "f1",
    "most_confused_with",
    "most_confused_count",
]

COMPARISON_FIELDNAMES = [
    "run",
    "rows",
    "class_count",
    "accuracy",
    "balanced_accuracy",
    "macro_precision",
    "macro_recall",
    "macro_f1",
    "weighted_f1",
    "worst_class",
    "worst_class_f1",
]

# The label column pair written by every training run.
PREDICTION_LABEL_COLUMN = "label"
PREDICTION_PREDICTION_COLUMN = "prediction"


@dataclass(frozen=True)
class ClassMetrics:
    """Per-class results, including where the class leaks to."""

    label: str
    support: int
    predicted: int
    correct: int
    precision: float
    recall: float
    f1: float
    most_confused_with: str | None
    most_confused_count: int

    def as_row(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "support": self.support,
            "predicted": self.predicted,
            "correct": self.correct,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "most_confused_with": self.most_confused_with or "",
            "most_confused_count": self.most_confused_count,
        }


@dataclass(frozen=True)
class ConfusionMatrix:
    """Counts of true label against predicted label."""

    labels: tuple[str, ...]
    counts: tuple[tuple[int, ...], ...]

    @property
    def fieldnames(self) -> list[str]:
        return ["true_label", "support", "correct", "accuracy", *self.labels]

    def rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, label in enumerate(self.labels):
            row_counts = self.counts[index]
            support = sum(row_counts)
            correct = row_counts[index]
            row: dict[str, Any] = {
                "true_label": label,
                "support": support,
                "correct": correct,
                "accuracy": round(correct / support, 4) if support else 0.0,
            }
            row.update(
                {
                    predicted: row_counts[position]
                    for position, predicted in enumerate(self.labels)
                }
            )
            rows.append(row)
        return rows

    def off_diagonal(self) -> list[tuple[str, str, int]]:
        """Every confusion that actually happened, heaviest first."""

        pairs = [
            (self.labels[row], self.labels[column], self.counts[row][column])
            for row in range(len(self.labels))
            for column in range(len(self.labels))
            if row != column and self.counts[row][column]
        ]
        pairs.sort(key=lambda item: (-item[2], item[0], item[1]))
        return pairs


@dataclass(frozen=True)
class EvaluationResult:
    """Everything one scored run is worth recording."""

    run_name: str
    rows: int
    class_count: int
    accuracy: float
    balanced_accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_f1: float
    per_class: tuple[ClassMetrics, ...]
    confusion: ConfusionMatrix
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def worst_class(self) -> ClassMetrics | None:
        """The class a reader should look at first."""

        return min(self.per_class, key=lambda item: (item.f1, -item.support), default=None)

    def summary(self) -> dict[str, Any]:
        worst = self.worst_class
        return {
            "run": self.run_name,
            "rows": self.rows,
            "class_count": self.class_count,
            "accuracy": round(self.accuracy, 4),
            "balanced_accuracy": round(self.balanced_accuracy, 4),
            "macro_precision": round(self.macro_precision, 4),
            "macro_recall": round(self.macro_recall, 4),
            "macro_f1": round(self.macro_f1, 4),
            "weighted_f1": round(self.weighted_f1, 4),
            "worst_class": worst.label if worst else "",
            "worst_class_f1": round(worst.f1, 4) if worst else "",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "metadata": self.metadata,
            "per_class": [metrics.as_row() for metrics in self.per_class],
            "confusion_matrix": {
                "labels": list(self.confusion.labels),
                "counts": [list(row) for row in self.confusion.counts],
            },
            "top_confusions": [
                {"true_label": true, "predicted_label": predicted, "count": count}
                for true, predicted, count in self.confusion.off_diagonal()[:20]
            ],
        }


def evaluate_predictions(
    true_labels: Iterable[Any],
    predicted_labels: Iterable[Any],
    *,
    run_name: str = "evaluation",
    labels: Sequence[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Score one set of predictions.

    ``labels`` fixes the class order; without it the union of true and predicted
    labels is used, sorted, so a class the model never predicts still gets a row
    rather than disappearing from the matrix.
    """

    true_values = [str(value) for value in true_labels]
    predicted_values = [str(value) for value in predicted_labels]
    if len(true_values) != len(predicted_values):
        raise ValueError("true and predicted label sequences must be the same length")
    if not true_values:
        raise ValueError("cannot evaluate an empty prediction set")

    class_labels = (
        [str(label) for label in labels]
        if labels is not None
        else sorted(set(true_values) | set(predicted_values))
    )

    matrix = confusion_matrix(true_values, predicted_values, labels=class_labels)
    precision, recall, f1, support = precision_recall_fscore_support(
        true_values,
        predicted_values,
        labels=class_labels,
        zero_division=0,
    )
    predicted_counts = matrix.sum(axis=0)

    per_class: list[ClassMetrics] = []
    for index, label in enumerate(class_labels):
        row = matrix[index]
        confusions = [
            (class_labels[position], int(count))
            for position, count in enumerate(row)
            if position != index and count
        ]
        confusions.sort(key=lambda item: (-item[1], item[0]))
        per_class.append(
            ClassMetrics(
                label=label,
                support=int(support[index]),
                predicted=int(predicted_counts[index]),
                correct=int(row[index]),
                precision=float(precision[index]),
                recall=float(recall[index]),
                f1=float(f1[index]),
                most_confused_with=confusions[0][0] if confusions else None,
                most_confused_count=confusions[0][1] if confusions else 0,
            )
        )

    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        true_values, predicted_values, labels=class_labels, average="macro", zero_division=0
    )
    _, _, weighted_f1, _ = precision_recall_fscore_support(
        true_values, predicted_values, labels=class_labels, average="weighted", zero_division=0
    )

    return EvaluationResult(
        run_name=run_name,
        rows=len(true_values),
        class_count=len(class_labels),
        accuracy=float(accuracy_score(true_values, predicted_values)),
        balanced_accuracy=float(balanced_accuracy_score(true_values, predicted_values)),
        macro_precision=float(macro_precision),
        macro_recall=float(macro_recall),
        macro_f1=float(macro_f1),
        weighted_f1=float(weighted_f1),
        per_class=tuple(per_class),
        confusion=ConfusionMatrix(
            labels=tuple(class_labels),
            counts=tuple(tuple(int(value) for value in row) for row in matrix),
        ),
        metadata=dict(metadata or {}),
    )


def evaluate_predictions_csv(
    predictions_csv: Path,
    *,
    run_name: str | None = None,
    label_column: str = PREDICTION_LABEL_COLUMN,
    prediction_column: str = PREDICTION_PREDICTION_COLUMN,
) -> EvaluationResult:
    """Score a predictions artifact written by a training run."""

    frame = pd.read_csv(predictions_csv, dtype="object", keep_default_na=False)
    for column in (label_column, prediction_column):
        if column not in frame.columns:
            raise ValueError(f"{predictions_csv} has no '{column}' column")

    return evaluate_predictions(
        frame[label_column],
        frame[prediction_column],
        run_name=run_name or run_name_from_path(predictions_csv),
        metadata={"predictions_csv": str(predictions_csv)},
    )


def evaluate_model_file(
    model_path: Path,
    input_csv: Path,
    *,
    label_column: str,
    text_columns: Sequence[str],
    run_name: str | None = None,
    max_rows: int | None = None,
) -> EvaluationResult:
    """Score a saved model against a dataset it has not been scored on yet."""

    import joblib

    # Imported here rather than at module load: training imports this module, so
    # a top-level import would close the cycle.
    from src.modeling.training import combined_text

    frame = pd.read_csv(input_csv, dtype="object", keep_default_na=False)
    if label_column not in frame.columns:
        raise ValueError(f"{input_csv} has no '{label_column}' column")
    missing = [column for column in text_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{input_csv} is missing text columns: {', '.join(missing)}")

    frame = frame[frame[label_column].astype(str).str.strip() != ""]
    text = combined_text(frame, text_columns)
    frame = frame[text.str.strip() != ""]
    text = text[text.str.strip() != ""]
    if max_rows is not None:
        frame = frame.head(max_rows)
        text = text.head(max_rows)
    if frame.empty:
        raise ValueError(f"{input_csv} has no rows with both a label and text")

    model = joblib.load(model_path)
    predictions = model.predict(text)
    return evaluate_predictions(
        frame[label_column],
        predictions,
        run_name=run_name or run_name_from_path(model_path),
        metadata={"model": str(model_path), "input_csv": str(input_csv)},
    )


def run_name_from_path(path: Path) -> str:
    """Derive a run name from an artifact path, dropping the artifact suffix."""

    stem = path.stem
    for suffix in ("_predictions", "_metrics", "_manifest", "_evaluation"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def confusion_matrix_output(run_name: str, directory: Path = DEFAULT_EVALUATION_DIR) -> Path:
    return directory / f"{run_name}_confusion_matrix.csv"


def per_class_output(run_name: str, directory: Path = DEFAULT_EVALUATION_DIR) -> Path:
    return directory / f"{run_name}_per_class.csv"


def evaluation_output(run_name: str, directory: Path = DEFAULT_EVALUATION_DIR) -> Path:
    return directory / f"{run_name}_evaluation.json"


def confusion_matrix_rows(result: EvaluationResult) -> list[dict[str, Any]]:
    return result.confusion.rows()


def per_class_rows(result: EvaluationResult) -> list[dict[str, Any]]:
    return [metrics.as_row() for metrics in result.per_class]


def write_confusion_matrix(path: Path, result: EvaluationResult) -> Path:
    write_csv_artifact(
        path,
        fieldnames=result.confusion.fieldnames,
        rows=confusion_matrix_rows(result),
    )
    return path


def write_per_class_report(path: Path, result: EvaluationResult) -> Path:
    write_csv_artifact(path, fieldnames=PER_CLASS_FIELDNAMES, rows=per_class_rows(result))
    return path


def write_evaluation_json(path: Path, result: EvaluationResult) -> Path:
    write_json_artifact(path, result.as_dict())
    return path


def write_evaluation_artifacts(
    result: EvaluationResult, *, directory: Path = DEFAULT_EVALUATION_DIR
) -> dict[str, Path]:
    """Write the confusion matrix, per-class results and JSON summary."""

    return {
        "confusion_matrix": write_confusion_matrix(
            confusion_matrix_output(result.run_name, directory), result
        ),
        "per_class": write_per_class_report(
            per_class_output(result.run_name, directory), result
        ),
        "evaluation": write_evaluation_json(
            evaluation_output(result.run_name, directory), result
        ),
    }


def write_comparison(path: Path, results: Sequence[EvaluationResult]) -> Path:
    """Write one row per run, so families can be read side by side."""

    write_csv_artifact(
        path,
        fieldnames=COMPARISON_FIELDNAMES,
        rows=[result.summary() for result in results],
    )
    return path


def render_evaluation(result: EvaluationResult, *, top_confusions: int = 10) -> str:
    """Human-readable evaluation, for the metrics artifact and the terminal."""

    lines = [
        f"Evaluation: {result.run_name}",
        "",
        f"rows: {result.rows}",
        f"class_count: {result.class_count}",
        f"accuracy: {result.accuracy:.4f}",
        f"balanced_accuracy: {result.balanced_accuracy:.4f}",
        f"macro_precision: {result.macro_precision:.4f}",
        f"macro_recall: {result.macro_recall:.4f}",
        f"macro_f1: {result.macro_f1:.4f}",
        f"weighted_f1: {result.weighted_f1:.4f}",
        "",
        "Per-class results:",
        f"{'label':<28}{'support':>8}{'prec':>8}{'recall':>8}{'f1':>8}  most confused with",
    ]
    for metrics in sorted(result.per_class, key=lambda item: -item.support):
        confused = (
            f"{metrics.most_confused_with} ({metrics.most_confused_count})"
            if metrics.most_confused_with
            else "-"
        )
        lines.append(
            f"{metrics.label[:27]:<28}{metrics.support:>8}"
            f"{metrics.precision:>8.3f}{metrics.recall:>8.3f}{metrics.f1:>8.3f}  {confused}"
        )

    confusions = result.confusion.off_diagonal()[:top_confusions]
    if confusions:
        lines.extend(["", f"Top {len(confusions)} confusions:"])
        lines.extend(
            f"  {true} -> {predicted}: {count}" for true, predicted, count in confusions
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_text_columns(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("at least one text column is required")
    return columns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score classifier predictions and write confusion-matrix, per-class "
            "and JSON evaluation artifacts."
        )
    )
    parser.add_argument(
        "--predictions-csv",
        type=Path,
        action="append",
        default=None,
        help="Predictions artifact to score. Repeat to compare several runs.",
    )
    parser.add_argument("--model", type=Path, help="Saved model to score instead.")
    parser.add_argument("--input-csv", type=Path, help="Dataset to score the model against.")
    parser.add_argument("--label-column", default="primary_domain")
    parser.add_argument("--text-columns", type=parse_text_columns, default=["title", "abstract", "keywords"])
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVALUATION_DIR)
    parser.add_argument(
        "--comparison-csv",
        type=Path,
        default=None,
        help="Where to write the side-by-side comparison (default: <output-dir>/model_comparison.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.predictions_csv and not args.model:
        raise SystemExit("Pass --predictions-csv (repeatable) or --model with --input-csv.")
    if args.model and not args.input_csv:
        raise SystemExit("--model needs --input-csv to score against.")

    results: list[EvaluationResult] = []
    for predictions_csv in args.predictions_csv or []:
        results.append(evaluate_predictions_csv(predictions_csv, run_name=args.run_name))
    if args.model:
        results.append(
            evaluate_model_file(
                args.model,
                args.input_csv,
                label_column=args.label_column,
                text_columns=args.text_columns,
                run_name=args.run_name,
                max_rows=args.max_rows,
            )
        )

    for result in results:
        written = write_evaluation_artifacts(result, directory=args.output_dir)
        print(render_evaluation(result))
        for name, path in written.items():
            print(f"  {name}: {path}")
        print()

    if len(results) > 1:
        comparison_csv = args.comparison_csv or (args.output_dir / "model_comparison.csv")
        write_comparison(comparison_csv, results)
        print("Comparison:")
        print(json.dumps([result.summary() for result in results], indent=2))
        print(f"  comparison: {comparison_csv}")


if __name__ == "__main__":
    main()
