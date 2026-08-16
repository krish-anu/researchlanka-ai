"""Linear SVM training pipeline for publication text classification.

TF-IDF vectorization + LinearSVC (single label column), with grid search
over the C regularization parameter, evaluation, and artifact saving.

Run via: scripts/modeling/train_linear_svm_classifier.py
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from src.modeling.artifacts import save_model_artifacts

# ============================================================================
# PATH CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)

DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models"

# ============================================================================
# MODEL DEFAULTS
# ============================================================================

DEFAULT_MODEL_FAMILY = "linear_svm"
DEFAULT_LABEL_COLUMN = "primary_domain"
DEFAULT_TEXT_COLUMNS = ("title", "abstract", "topics", "keywords", "concepts")
DEFAULT_C_VALUES = (0.1, 1.0, 10.0)


# ============================================================================
# TRAINING CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class LinearSVMTrainingConfig:
    """Configuration for one Linear SVM training run."""

    input_path: Path = DEFAULT_INPUT
    label_column: str = DEFAULT_LABEL_COLUMN
    text_columns: tuple[str, ...] = DEFAULT_TEXT_COLUMNS
    model_family: str = DEFAULT_MODEL_FAMILY

    model_output: Path | None = None
    metrics_output: Path | None = None
    label_counts_output: Path | None = None
    predictions_output: Path | None = None
    manifest_output: Path | None = None

    # dataset split
    test_size: float = 0.15
    random_state: int = 42

    # filtering
    max_rows: int | None = None
    min_class_count: int = 20

    # TF-IDF
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 3

    # SVM parameters
    c_values: tuple[float, ...] = DEFAULT_C_VALUES
    class_weight: str | None = "balanced"
    max_iter: int = 5000

    # Grid search
    cv_folds: int = 3
    scoring: str = "f1_macro"


# ============================================================================
# CLI ARGUMENT HELPERS
# ============================================================================


def parse_text_columns(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("At least one text column is required.")
    return columns


def parse_c_values(value: str) -> tuple[float, ...]:
    values = []
    for item in value.split(","):
        try:
            number = float(item)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid C value: {item}") from exc
        if number <= 0:
            raise argparse.ArgumentTypeError("C values must be positive.")
        values.append(number)
    if not values:
        raise argparse.ArgumentTypeError("At least one C value is required.")
    return tuple(values)


def parse_document_frequency(value: str) -> int | float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid document frequency value: {value}"
        ) from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Document frequency must be positive.")
    if parsed < 1:
        return parsed
    if not parsed.is_integer():
        raise argparse.ArgumentTypeError("Values >= 1 must be integers.")
    return int(parsed)


def parse_class_weight(value: str) -> str | None:
    value = value.strip().lower()
    if value == "none":
        return None
    if value == "balanced":
        return "balanced"
    raise argparse.ArgumentTypeError("class_weight must be 'balanced' or 'none'")


# ============================================================================
# NAMING / ARTIFACT PATH HELPERS
# ============================================================================


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "artifact"


def artifact_stem(model_family: str, label_column: str) -> str:
    return f"{slugify(model_family)}_{slugify(label_column)}"


def default_model_output(
    label_column: str, model_family: str = DEFAULT_MODEL_FAMILY
) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, label_column)}.joblib"


def default_metrics_output(
    label_column: str, model_family: str = DEFAULT_MODEL_FAMILY
) -> Path:
    return (
        DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, label_column)}_metrics.txt"
    )


def default_label_counts_output(
    label_column: str, model_family: str = DEFAULT_MODEL_FAMILY
) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, label_column)}_labels.csv"


def default_predictions_output(
    label_column: str, model_family: str = DEFAULT_MODEL_FAMILY
) -> Path:
    return (
        DEFAULT_MODEL_DIR
        / f"{artifact_stem(model_family, label_column)}_predictions.csv"
    )


def default_manifest_output(
    label_column: str, model_family: str = DEFAULT_MODEL_FAMILY
) -> Path:
    return (
        DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, label_column)}_manifest.json"
    )


# ============================================================================
# DATA PROCESSING
# ============================================================================


def combined_text(frame: pd.DataFrame, text_columns: Iterable[str]) -> pd.Series:
    """Combine publication metadata columns into one training text."""
    text = frame[list(text_columns)].fillna("").astype(str).agg(" ".join, axis=1)
    return text.str.replace(r"\s+", " ", regex=True).str.strip()


def load_training_frame(
    input_path: Path,
    *,
    label_column: str,
    text_columns: Iterable[str],
    min_class_count: int,
    max_rows: int | None = None,
) -> tuple[pd.DataFrame, int, pd.Series]:
    """Load dataset and prepare a training dataframe with columns: text, label.

    Removes rows with empty text/labels and classes below ``min_class_count``.
    """
    required_columns = [*text_columns, label_column]

    frame = pd.read_csv(
        input_path,
        usecols=required_columns,
        dtype=str,
        keep_default_na=False,
        nrows=max_rows,
    )
    input_rows = len(frame)

    training_frame = pd.DataFrame(
        {
            "text": combined_text(frame, text_columns),
            "label": frame[label_column].astype(str).str.strip(),
        },
        index=frame.index,
    )
    training_frame.index.name = "source_row"

    training_frame = training_frame[
        (training_frame["text"] != "") & (training_frame["label"] != "")
    ]

    label_counts = training_frame["label"].value_counts()
    valid_labels = label_counts[label_counts >= min_class_count].index
    training_frame = training_frame[training_frame["label"].isin(valid_labels)]
    label_counts = training_frame["label"].value_counts()

    if training_frame.empty:
        raise ValueError("No usable training rows after filtering.")
    if len(label_counts) < 2:
        raise ValueError("Training requires at least two classes.")

    return training_frame, input_rows, label_counts


# ============================================================================
# PIPELINE CONSTRUCTION
# ============================================================================


def _tfidf_vectorizer(
    *, max_features: int, min_df: int | float, max_df: int | float, ngram_max: int
) -> TfidfVectorizer:
    if ngram_max < 1:
        raise ValueError("ngram_max must be >= 1")
    return TfidfVectorizer(
        lowercase=True,
        stop_words=None,
        strip_accents="unicode",
        ngram_range=(1, ngram_max),
        min_df=min_df,
        max_df=max_df,
        sublinear_tf=True,
        max_features=(None if max_features <= 0 else max_features),
    )


def build_grid_pipeline(
    *,
    max_features: int,
    min_df: int | float,
    max_df: int | float,
    ngram_max: int,
    class_weight: str | None,
    max_iter: int,
) -> Pipeline:
    """Pipeline used inside GridSearchCV. C is tuned separately."""
    return Pipeline(
        [
            (
                "tfidf",
                _tfidf_vectorizer(
                    max_features=max_features,
                    min_df=min_df,
                    max_df=max_df,
                    ngram_max=ngram_max,
                ),
            ),
            (
                "svm",
                LinearSVC(
                    class_weight=class_weight,
                    max_iter=max_iter,
                    random_state=42,
                    dual="auto",
                ),
            ),
        ]
    )


def build_final_pipeline(
    *,
    max_features: int,
    min_df: int | float,
    max_df: int | float,
    ngram_max: int,
    class_weight: str | None,
    max_iter: int,
    c_value: float,
) -> Pipeline:
    """Pipeline with a fixed C, used to retrain the production model."""
    return Pipeline(
        [
            (
                "tfidf",
                _tfidf_vectorizer(
                    max_features=max_features,
                    min_df=min_df,
                    max_df=max_df,
                    ngram_max=ngram_max,
                ),
            ),
            (
                "svm",
                LinearSVC(
                    C=c_value,
                    class_weight=class_weight,
                    max_iter=max_iter,
                    random_state=42,
                    dual="auto",
                ),
            ),
        ]
    )


# ============================================================================
# CONFIGURATION RESOLUTION
# ============================================================================


def resolved_config(config: LinearSVMTrainingConfig) -> LinearSVMTrainingConfig:
    """Fill missing artifact paths with defaults derived from label/model family."""
    return LinearSVMTrainingConfig(
        input_path=config.input_path,
        label_column=config.label_column,
        text_columns=config.text_columns,
        model_family=config.model_family,
        model_output=config.model_output
        or default_model_output(config.label_column, config.model_family),
        metrics_output=config.metrics_output
        or default_metrics_output(config.label_column, config.model_family),
        label_counts_output=config.label_counts_output
        or default_label_counts_output(config.label_column, config.model_family),
        predictions_output=config.predictions_output
        or default_predictions_output(config.label_column, config.model_family),
        manifest_output=config.manifest_output
        or default_manifest_output(config.label_column, config.model_family),
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


def validate_config(config: LinearSVMTrainingConfig) -> None:
    if config.model_family != DEFAULT_MODEL_FAMILY:
        raise ValueError(f"Unsupported model family: {config.model_family}")
    if not 0 < config.test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    if config.ngram_max < 1:
        raise ValueError("ngram_max must be >= 1")
    if not config.c_values:
        raise ValueError("At least one C value is required")


# ============================================================================
# PREDICTIONS / METRICS
# ============================================================================


def prediction_rows(
    *, test_text: pd.Series, test_labels: pd.Series, predictions: Iterable[str]
) -> list[dict[str, Any]]:
    rows = []
    for source_row, text, label, prediction in zip(
        test_text.index, test_text, test_labels, predictions, strict=True
    ):
        rows.append(
            {
                "source_row": source_row,
                "label": label,
                "prediction": prediction,
                "correct": label == prediction,
                "text": text,
            }
        )
    return rows


def render_metrics(
    *,
    config: LinearSVMTrainingConfig,
    input_rows: int,
    usable_rows: int,
    train_rows: int,
    test_rows: int,
    label_counts: pd.Series,
    best_c: float,
    best_cv_score: float,
    accuracy: float,
    macro_f1: float,
    weighted_f1: float,
    report: str,
) -> str:
    lines = [
        "Publication Linear SVM Classifier",
        "",
        f"model_family: {config.model_family}",
        f"input_csv: {config.input_path}",
        f"label_column: {config.label_column}",
        f"text_columns: {', '.join(config.text_columns)}",
        "",
        f"ngram_max: {config.ngram_max}",
        f"best_C: {best_c}",
        "",
        f"input_rows: {input_rows}",
        f"usable_rows: {usable_rows}",
        f"train_rows: {train_rows}",
        f"test_rows: {test_rows}",
        "",
        f"class_count: {len(label_counts)}",
        "",
        f"cv_macro_f1: {best_cv_score:.4f}",
        f"accuracy: {accuracy:.4f}",
        f"macro_f1: {macro_f1:.4f}",
        f"weighted_f1: {weighted_f1:.4f}",
        "",
        "Class Distribution:",
    ]
    lines.extend(f"{label}: {count}" for label, count in label_counts.items())
    lines.extend(["", "Classification Report:", report])
    return "\n".join(lines)


# ============================================================================
# MAIN TRAINING FUNCTION
# ============================================================================


def train_linear_svm_classifier(config: LinearSVMTrainingConfig) -> dict[str, Any]:
    """Complete Linear SVM training workflow.

    1. Load dataset            5. Evaluate on held-out test split
    2. Prepare text             6. Retrain best model on all data
    3. Split train/test         7. Save artifacts (model/metrics/predictions/manifest)
    4. Grid-search C            8. Return a result summary dict
    """
    config = resolved_config(config)
    validate_config(config)

    training_frame, input_rows, label_counts = load_training_frame(
        config.input_path,
        label_column=config.label_column,
        text_columns=config.text_columns,
        min_class_count=config.min_class_count,
        max_rows=config.max_rows,
    )

    X_train, X_test, y_train, y_test = train_test_split(
        training_frame["text"],
        training_frame["label"],
        test_size=config.test_size,
        random_state=config.random_state,
        stratify=training_frame["label"],
    )

    grid_pipeline = build_grid_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
    )

    grid = GridSearchCV(
        estimator=grid_pipeline,
        param_grid={"svm__C": list(config.c_values)},
        cv=config.cv_folds,
        scoring=config.scoring,
        n_jobs=-1,
    )
    grid.fit(X_train, y_train)

    best_c = grid.best_params_["svm__C"]
    predictions = grid.best_estimator_.predict(X_test)

    accuracy = accuracy_score(y_test, predictions)
    macro_f1 = f1_score(y_test, predictions, average="macro", zero_division=0)
    weighted_f1 = f1_score(y_test, predictions, average="weighted", zero_division=0)
    report = classification_report(y_test, predictions, zero_division=0)

    # Retrain the production model on ALL labelled data using the best C
    final_model = build_final_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        c_value=best_c,
    )
    final_model.fit(training_frame["text"], training_frame["label"])

    metrics_text = render_metrics(
        config=config,
        input_rows=input_rows,
        usable_rows=len(training_frame),
        train_rows=len(X_train),
        test_rows=len(X_test),
        label_counts=label_counts,
        best_c=best_c,
        best_cv_score=grid.best_score_,
        accuracy=accuracy,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        report=report,
    )
    rows = prediction_rows(
        test_text=X_test, test_labels=y_test, predictions=predictions
    )

    assert config.model_output is not None
    assert config.metrics_output is not None
    assert config.label_counts_output is not None
    assert config.predictions_output is not None
    assert config.manifest_output is not None
    config.model_output.parent.mkdir(parents=True, exist_ok=True)

    artifacts = save_model_artifacts(
        model=final_model,
        model_output=config.model_output,
        metrics_text=metrics_text,
        metrics_output=config.metrics_output,
        label_counts=label_counts,
        label_counts_output=config.label_counts_output,
        predictions=rows,
        predictions_output=config.predictions_output,
        manifest_output=config.manifest_output,
        manifest_config={
            "model_family": config.model_family,
            "label_column": config.label_column,
            "ngram_max": config.ngram_max,
            "best_C": best_c,
            "class_weight": config.class_weight,
            "max_features": config.max_features,
            "min_df": config.min_df,
            "max_df": config.max_df,
        },
        manifest_result={
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "weighted_f1": weighted_f1,
            "rows": len(training_frame),
        },
    )

    return {
        "input_rows": input_rows,
        "usable_rows": len(training_frame),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "class_count": len(label_counts),
        "best_c": best_c,
        "best_cv_score": grid.best_score_,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "report": report,
        "artifacts": artifacts,
    }


# ============================================================================
# CLI
# ============================================================================


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train TF-IDF + LinearSVC publication classifier with configurable n-gram features."
    )
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT, help="Input publication CSV"
    )
    parser.add_argument(
        "--label-column",
        default=DEFAULT_LABEL_COLUMN,
        help="Target column to predict, e.g. primary_field, primary_subfield",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=list(DEFAULT_TEXT_COLUMNS),
        help="Comma separated text fields. Default: title,abstract,topics,keywords,concepts",
    )
    parser.add_argument("--ngram-max", type=int, default=3, help="Maximum ngram size")
    parser.add_argument(
        "--c-values",
        type=parse_c_values,
        default=DEFAULT_C_VALUES,
        help="Comma separated LinearSVC C candidates to grid-search, e.g. 0.1,1,10",
    )
    parser.add_argument(
        "--test-size", type=float, default=0.15, help="Test split ratio"
    )
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--max-features",
        type=int,
        default=50_000,
        help="Maximum TF-IDF vocabulary size",
    )
    parser.add_argument("--min-df", type=parse_document_frequency, default=2)
    parser.add_argument("--max-df", type=parse_document_frequency, default=0.95)
    parser.add_argument(
        "--class-weight",
        type=parse_class_weight,
        default="balanced",
        help="'balanced' or 'none'",
    )
    parser.add_argument(
        "--min-class-count",
        type=int,
        default=20,
        help="Remove classes with fewer samples",
    )
    parser.add_argument("--max-iter", type=int, default=5000)
    parser.add_argument("--cv-folds", type=int, default=3)
    parser.add_argument("--scoring", default="f1_macro")
    parser.add_argument("--model-output", type=Path, default=None)
    parser.add_argument("--metrics-output", type=Path, default=None)
    parser.add_argument("--label-counts-output", type=Path, default=None)
    parser.add_argument("--predictions-output", type=Path, default=None)
    parser.add_argument("--manifest-output", type=Path, default=None)
    return parser.parse_args(argv)


def result_summary(result: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("LINEAR SVM TRAINING COMPLETED")
    print("=" * 60)
    print(f"Best C        : {result['best_c']}")
    print(f"CV macro F1   : {result['best_cv_score']:.4f}")
    print(f"Accuracy      : {result['accuracy']:.4f}")
    print(f"Macro F1      : {result['macro_f1']:.4f}")
    print(f"Weighted F1   : {result['weighted_f1']:.4f}")

    artifacts = result["artifacts"]
    print("\nArtifacts:")
    print(f"Model         : {artifacts.model.path}")
    print(f"Metrics       : {artifacts.metrics.path}")
    print(f"Predictions   : {artifacts.predictions.path}")
    print(f"Manifest      : {artifacts.manifest.path}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    config = LinearSVMTrainingConfig(
        input_path=args.input,
        label_column=args.label_column,
        text_columns=tuple(args.text_columns),
        ngram_max=args.ngram_max,
        c_values=args.c_values,
        test_size=args.test_size,
        random_state=args.random_state,
        max_features=args.max_features,
        min_df=args.min_df,
        max_df=args.max_df,
        class_weight=args.class_weight,
        min_class_count=args.min_class_count,
        max_iter=args.max_iter,
        cv_folds=args.cv_folds,
        scoring=args.scoring,
        model_output=args.model_output,
        metrics_output=args.metrics_output,
        label_counts_output=args.label_counts_output,
        predictions_output=args.predictions_output,
        manifest_output=args.manifest_output,
    )

    result = train_linear_svm_classifier(config)
    result_summary(result)


if __name__ == "__main__":
    main()
