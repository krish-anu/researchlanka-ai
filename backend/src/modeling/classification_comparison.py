"""Compare publication text classification model families.

Runs each supported flat classifier trainer against the same dataset and writes
a ranked metrics table plus a manifest that points back to each model's normal
training artifacts.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.modeling.artifacts import write_csv_artifact, write_json_artifact
from src.modeling.linear_svm_training import (
    LinearSVMTrainingConfig,
    train_linear_svm_classifier,
)
from src.modeling.training import (
    DEFAULT_INPUT,
    DEFAULT_LABEL_COLUMN,
    DEFAULT_MODEL_DIR,
    DEFAULT_TEXT_COLUMNS,
    TextTrainingConfig,
    parse_class_weight,
    parse_document_frequency,
    parse_text_columns,
    slugify,
    train_text_classifier,
)


DEFAULT_MODEL_FAMILIES = ("logistic_regression", "linear_svm")
DEFAULT_COMPARISON_DIR = DEFAULT_MODEL_DIR / "classification_comparison"
DEFAULT_COMPARISON_OUTPUT = DEFAULT_COMPARISON_DIR / "model_comparison.csv"
DEFAULT_COMPARISON_MANIFEST_OUTPUT = DEFAULT_COMPARISON_DIR / "model_comparison_manifest.json"


@dataclass(frozen=True)
class ClassificationComparisonConfig:
    """Configuration for one classifier model-family comparison."""

    input_path: Path = DEFAULT_INPUT
    label_column: str = DEFAULT_LABEL_COLUMN
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    model_families: tuple[str, ...] = DEFAULT_MODEL_FAMILIES
    output_dir: Path = DEFAULT_COMPARISON_DIR
    comparison_output: Path | None = None
    manifest_output: Path | None = None
    test_size: float = 0.2
    random_state: int = 42
    max_rows: int | None = None
    min_class_count: int = 20
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 2
    keep_stop_words: bool = False
    class_weight: str | None = "balanced"
    max_iter: int = 1000
    c_values: tuple[float, ...] = (0.1, 1.0, 10.0)
    cv_folds: int = 3
    scoring: str = "f1_macro"
    ranking_metric: str = "macro_f1"


@dataclass(frozen=True)
class ClassificationComparisonResult:
    """Paths and ranked rows produced by a model comparison run."""

    comparison_output: Path
    manifest_output: Path
    model_count: int
    best_model_family: str
    ranking_metric: str
    rows: tuple[dict[str, Any], ...]


def parse_model_families(value: str) -> tuple[str, ...]:
    families = tuple(item.strip() for item in value.split(",") if item.strip())
    if not families:
        raise argparse.ArgumentTypeError("at least one model family is required")
    unsupported = [family for family in families if family not in DEFAULT_MODEL_FAMILIES]
    if unsupported:
        raise argparse.ArgumentTypeError(
            "unsupported model family/families: "
            + ", ".join(unsupported)
            + f". Supported: {', '.join(DEFAULT_MODEL_FAMILIES)}"
        )
    return families


def parse_c_values(value: str) -> tuple[float, ...]:
    values = []
    for item in value.split(","):
        try:
            number = float(item)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid C value: {item}") from exc
        if number <= 0:
            raise argparse.ArgumentTypeError("C values must be positive")
        values.append(number)
    if not values:
        raise argparse.ArgumentTypeError("at least one C value is required")
    return tuple(values)


def resolved_config(config: ClassificationComparisonConfig) -> ClassificationComparisonConfig:
    return ClassificationComparisonConfig(
        input_path=config.input_path,
        label_column=config.label_column,
        text_columns=config.text_columns,
        model_families=config.model_families,
        output_dir=config.output_dir,
        comparison_output=config.comparison_output
        or config.output_dir
        / DEFAULT_COMPARISON_OUTPUT.name,
        manifest_output=config.manifest_output
        or config.output_dir
        / DEFAULT_COMPARISON_MANIFEST_OUTPUT.name,
        test_size=config.test_size,
        random_state=config.random_state,
        max_rows=config.max_rows,
        min_class_count=config.min_class_count,
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        keep_stop_words=config.keep_stop_words,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        c_values=config.c_values,
        cv_folds=config.cv_folds,
        scoring=config.scoring,
        ranking_metric=config.ranking_metric,
    )


def json_ready_dataclass(value: object) -> dict[str, object]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def artifact_path(
    *,
    output_dir: Path,
    model_family: str,
    label_column: str,
    kind: str,
) -> Path:
    stem = f"{slugify(model_family)}_{slugify(label_column)}"
    suffix_by_kind = {
        "model": ".joblib",
        "metrics": "_metrics.txt",
        "labels": "_labels.csv",
        "predictions": "_predictions.csv",
        "manifest": "_manifest.json",
    }
    return output_dir / f"{stem}{suffix_by_kind[kind]}"


def model_artifact_paths(
    output_dir: Path,
    model_family: str,
    label_column: str,
) -> dict[str, Path]:
    return {
        "model": artifact_path(
            output_dir=output_dir,
            model_family=model_family,
            label_column=label_column,
            kind="model",
        ),
        "metrics": artifact_path(
            output_dir=output_dir,
            model_family=model_family,
            label_column=label_column,
            kind="metrics",
        ),
        "labels": artifact_path(
            output_dir=output_dir,
            model_family=model_family,
            label_column=label_column,
            kind="labels",
        ),
        "predictions": artifact_path(
            output_dir=output_dir,
            model_family=model_family,
            label_column=label_column,
            kind="predictions",
        ),
        "manifest": artifact_path(
            output_dir=output_dir,
            model_family=model_family,
            label_column=label_column,
            kind="manifest",
        ),
    }


def validate_config(config: ClassificationComparisonConfig) -> None:
    if not config.model_families:
        raise ValueError("at least one model family is required")
    unsupported = [family for family in config.model_families if family not in DEFAULT_MODEL_FAMILIES]
    if unsupported:
        raise ValueError(
            "unsupported model family/families: "
            + ", ".join(unsupported)
            + f". Supported: {', '.join(DEFAULT_MODEL_FAMILIES)}"
        )
    if not 0 < config.test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    if config.min_class_count < 2:
        raise ValueError("min_class_count must be at least 2 for stratified splitting")
    if config.ngram_max < 1:
        raise ValueError("ngram_max must be at least 1")
    if not config.c_values:
        raise ValueError("at least one C value is required")
    if config.ranking_metric not in {"accuracy", "macro_f1", "weighted_f1"}:
        raise ValueError("ranking_metric must be accuracy, macro_f1, or weighted_f1")


def train_model_family(
    model_family: str,
    config: ClassificationComparisonConfig,
) -> Any:
    paths = model_artifact_paths(config.output_dir, model_family, config.label_column)
    if model_family == "logistic_regression":
        return train_text_classifier(
            TextTrainingConfig(
                input_path=config.input_path,
                label_column=config.label_column,
                text_columns=config.text_columns,
                model_output=paths["model"],
                metrics_output=paths["metrics"],
                label_counts_output=paths["labels"],
                predictions_output=paths["predictions"],
                manifest_output=paths["manifest"],
                test_size=config.test_size,
                random_state=config.random_state,
                max_rows=config.max_rows,
                min_class_count=config.min_class_count,
                max_features=config.max_features,
                min_df=config.min_df,
                max_df=config.max_df,
                ngram_max=config.ngram_max,
                keep_stop_words=config.keep_stop_words,
                class_weight=config.class_weight,
                max_iter=config.max_iter,
            )
        )
    if model_family == "linear_svm":
        return train_linear_svm_classifier(
            LinearSVMTrainingConfig(
                input_path=config.input_path,
                label_column=config.label_column,
                text_columns=config.text_columns,
                model_output=paths["model"],
                metrics_output=paths["metrics"],
                label_counts_output=paths["labels"],
                predictions_output=paths["predictions"],
                manifest_output=paths["manifest"],
                test_size=config.test_size,
                random_state=config.random_state,
                max_rows=config.max_rows,
                min_class_count=config.min_class_count,
                max_features=config.max_features,
                min_df=config.min_df,
                max_df=config.max_df,
                ngram_max=config.ngram_max,
                c_values=config.c_values,
                class_weight=config.class_weight,
                max_iter=config.max_iter,
                cv_folds=config.cv_folds,
                scoring=config.scoring,
            )
        )
    raise ValueError(f"Unsupported model family: {model_family}")


def comparison_row(model_family: str, result: Any) -> dict[str, Any]:
    row = {
        "model_family": model_family,
        "input_rows": result.input_rows,
        "usable_rows": result.usable_rows,
        "train_rows": result.train_rows,
        "test_rows": result.test_rows,
        "class_count": result.class_count,
        "accuracy": result.accuracy,
        "macro_f1": result.macro_f1,
        "weighted_f1": result.weighted_f1,
        "model_path": str(result.model_output),
        "metrics_path": str(result.metrics_output),
        "predictions_path": str(result.predictions_output),
        "manifest_path": str(result.manifest_output),
        "model_sha256": result.model_sha256,
    }
    if hasattr(result, "best_c"):
        row["best_c"] = result.best_c
    if hasattr(result, "best_cv_score"):
        row["best_cv_score"] = result.best_cv_score
    return row


def sorted_rows(rows: Iterable[dict[str, Any]], ranking_metric: str) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            float(row[ranking_metric]),
            float(row["weighted_f1"]),
            str(row["model_family"]),
        ),
        reverse=True,
    )


def write_comparison_manifest(
    path: Path,
    *,
    config: ClassificationComparisonConfig,
    rows: list[dict[str, Any]],
) -> None:
    write_json_artifact(
        path,
        {
            "config": json_ready_dataclass(config),
            "ranking_metric": config.ranking_metric,
            "best_model_family": rows[0]["model_family"] if rows else None,
            "models": rows,
        },
    )


def compare_classification_models(
    config: ClassificationComparisonConfig | None = None,
) -> ClassificationComparisonResult:
    """Train and rank all requested flat publication classifier families."""

    config = resolved_config(config or ClassificationComparisonConfig())
    validate_config(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        comparison_row(model_family, train_model_family(model_family, config))
        for model_family in config.model_families
    ]
    ranked_rows = sorted_rows(rows, config.ranking_metric)

    assert config.comparison_output is not None
    assert config.manifest_output is not None
    write_csv_artifact(
        config.comparison_output,
        fieldnames=[
            "rank",
            "model_family",
            "input_rows",
            "usable_rows",
            "train_rows",
            "test_rows",
            "class_count",
            "accuracy",
            "macro_f1",
            "weighted_f1",
            "best_c",
            "best_cv_score",
            "model_path",
            "metrics_path",
            "predictions_path",
            "manifest_path",
            "model_sha256",
        ],
        rows=[
            {"rank": rank, **row}
            for rank, row in enumerate(ranked_rows, start=1)
        ],
    )
    write_comparison_manifest(config.manifest_output, config=config, rows=ranked_rows)

    return ClassificationComparisonResult(
        comparison_output=config.comparison_output,
        manifest_output=config.manifest_output,
        model_count=len(ranked_rows),
        best_model_family=str(ranked_rows[0]["model_family"]),
        ranking_metric=config.ranking_metric,
        rows=tuple(ranked_rows),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train and compare all supported flat publication text classifiers "
            "on the same input data and write ranked metrics artifacts."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--label-column", default=DEFAULT_LABEL_COLUMN)
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns. Default: title,abstract,keywords",
    )
    parser.add_argument(
        "--model-families",
        type=parse_model_families,
        default=DEFAULT_MODEL_FAMILIES,
        help="Comma-separated model families. Default: logistic_regression,linear_svm",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_COMPARISON_DIR)
    parser.add_argument("--comparison-output", type=Path, default=None)
    parser.add_argument("--manifest-output", type=Path, default=None)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--min-class-count", type=int, default=20)
    parser.add_argument("--max-features", type=int, default=50_000)
    parser.add_argument("--min-df", type=parse_document_frequency, default=2)
    parser.add_argument("--max-df", type=parse_document_frequency, default=0.95)
    parser.add_argument("--ngram-max", type=int, default=2)
    parser.add_argument("--keep-stop-words", action="store_true")
    parser.add_argument("--class-weight", type=parse_class_weight, default="balanced")
    parser.add_argument("--max-iter", type=int, default=1000)
    parser.add_argument("--c-values", type=parse_c_values, default=(0.1, 1.0, 10.0))
    parser.add_argument("--cv-folds", type=int, default=3)
    parser.add_argument("--scoring", default="f1_macro")
    parser.add_argument(
        "--ranking-metric",
        choices=["accuracy", "macro_f1", "weighted_f1"],
        default="macro_f1",
    )
    return parser.parse_args()


def result_summary(result: ClassificationComparisonResult) -> str:
    lines = [
        f"Compared {result.model_count:,} classification model families.",
        f"Ranking metric: {result.ranking_metric}",
        f"Best model: {result.best_model_family}",
        f"Comparison: {result.comparison_output}",
        f"Manifest: {result.manifest_output}",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    result = compare_classification_models(
        ClassificationComparisonConfig(
            input_path=args.input,
            label_column=args.label_column,
            text_columns=tuple(args.text_columns),
            model_families=tuple(args.model_families),
            output_dir=args.output_dir,
            comparison_output=args.comparison_output,
            manifest_output=args.manifest_output,
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
            c_values=args.c_values,
            cv_folds=args.cv_folds,
            scoring=args.scoring,
            ranking_metric=args.ranking_metric,
        )
    )
    print(result_summary(result))


if __name__ == "__main__":
    main()
