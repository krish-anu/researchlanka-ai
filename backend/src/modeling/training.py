"""Reusable training pipeline for publication text classifiers.

The defaults preserve the original TF-IDF + Logistic Regression classifier used
for publication metadata, while the dataclass-based configuration and structured
artifacts make each training run reproducible from scripts, tests, or notebooks.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from src.modeling.artifacts import (
    CsvArtifactSpec,
    SavedArtifact,
    SavedModelArtifacts,
    file_sha256,
    save_model_artifacts,
    write_csv_artifact,
    write_json_artifact,
)
from src.modeling.evaluation import (
    EvaluationResult,
    PER_CLASS_FIELDNAMES,
    confusion_matrix_output,
    confusion_matrix_rows,
    evaluate_predictions,
    per_class_output,
    per_class_rows,
    render_evaluation,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models"

DEFAULT_LABEL_COLUMN = "primary_field"
DEFAULT_TEXT_COLUMNS = ["title", "abstract", "topics", "keywords", "concepts"]
DEFAULT_MODEL_FAMILY = "logistic_regression"
# Best Logistic Regression defaults (aligned text cols with Linear SVM)
DEFAULT_NGRAM_MAX = 2
DEFAULT_TEST_SIZE = 0.15
DEFAULT_CLASS_WEIGHT: str | None = "balanced"
DEFAULT_MAX_ITER = 1000


MODEL_FAMILY_LOGISTIC_REGRESSION = "logistic_regression"
MODEL_FAMILY_MULTINOMIAL_NB = "multinomial_nb"
SUPPORTED_MODEL_FAMILIES = (
    MODEL_FAMILY_LOGISTIC_REGRESSION,
    MODEL_FAMILY_MULTINOMIAL_NB,
)
DEFAULT_MODEL_FAMILY = MODEL_FAMILY_LOGISTIC_REGRESSION


@dataclass(frozen=True)
class TextTrainingConfig:
    """Configuration for one reusable publication text-classifier run."""

    input_path: Path = DEFAULT_INPUT
    label_column: str = DEFAULT_LABEL_COLUMN
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    model_family: str = DEFAULT_MODEL_FAMILY
    model_output: Path | None = None
    metrics_output: Path | None = None
    label_counts_output: Path | None = None
    predictions_output: Path | None = None
    manifest_output: Path | None = None

    test_size: float = DEFAULT_TEST_SIZE

    confusion_matrix_output: Path | None = None
    per_class_output: Path | None = None

    random_state: int = 42
    max_rows: int | None = None
    min_class_count: int = 20
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = DEFAULT_NGRAM_MAX
    keep_stop_words: bool = False

    class_weight: str | None = DEFAULT_CLASS_WEIGHT
    max_iter: int = DEFAULT_MAX_ITER

    # Logistic Regression only.

    max_iter: int = 1000
    # Multinomial Naive Bayes only: additive smoothing, and whether the class
    # prior is learned from the data or left uniform. A uniform prior is the
    # closest this family has to balanced class weighting.
    alpha: float = 1.0
    fit_prior: bool = True


@dataclass(frozen=True)
class TrainingResult:
    """Paths and evaluation stats produced by one training run."""

    model_output: Path
    metrics_output: Path
    label_counts_output: Path
    predictions_output: Path
    manifest_output: Path
    input_rows: int
    usable_rows: int
    train_rows: int
    test_rows: int
    class_count: int
    accuracy: float
    macro_f1: float
    weighted_f1: float
    model_sha256: str = ""
    confusion_matrix_output: Path | None = None
    per_class_output: Path | None = None
    balanced_accuracy: float = 0.0


def parse_text_columns(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("at least one text column is required")
    return columns


def parse_document_frequency(value: str) -> int | float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid document frequency value: {value}"
        ) from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "document frequency thresholds must be positive"
        )
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
    label_column: str,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, label_column)}_labels.csv"


def default_predictions_output(
    label_column: str,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    return (
        DEFAULT_MODEL_DIR
        / f"{artifact_stem(model_family, label_column)}_predictions.csv"
    )


def default_confusion_matrix_output(
    label_column: str,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    return confusion_matrix_output(
        artifact_stem(model_family, label_column), DEFAULT_MODEL_DIR
    )


def default_per_class_output(
    label_column: str,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    return per_class_output(
        artifact_stem(model_family, label_column), DEFAULT_MODEL_DIR
    )


def default_manifest_output(
    label_column: str,
    model_family: str = DEFAULT_MODEL_FAMILY,
) -> Path:
    return (
        DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, label_column)}_manifest.json"
    )


def combined_text(frame: pd.DataFrame, text_columns: Iterable[str]) -> pd.Series:
    text = frame[list(text_columns)].astype(str).agg(" ".join, axis=1)
    return text.str.replace(r"\s+", " ", regex=True).str.strip()


def load_training_frame(
    input_path: Path,
    *,
    label_column: str,
    text_columns: list[str] | tuple[str, ...],
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
        },
        index=frame.index,
    )
    training_frame.index.name = "source_row"
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


def build_classifier(
    model_family: str,
    *,
    class_weight: str | None,
    max_iter: int,
    random_state: int,
    alpha: float,
    fit_prior: bool,
) -> Any:
    """Build the classifier stage for one model family."""

    if model_family == MODEL_FAMILY_LOGISTIC_REGRESSION:
        return LogisticRegression(
            solver="saga",
            max_iter=max_iter,
            class_weight=class_weight,
            random_state=random_state,
        )
    if model_family == MODEL_FAMILY_MULTINOMIAL_NB:
        # Naive Bayes has no class_weight and nothing to iterate: smoothing and
        # the class prior are its only knobs, and it is deterministic, so
        # random_state does not apply either.
        return MultinomialNB(alpha=alpha, fit_prior=fit_prior)
    raise ValueError(
        f"Unsupported model_family: {model_family}. "
        f"Supported values: {', '.join(SUPPORTED_MODEL_FAMILIES)}."
    )


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
    model_family: str = DEFAULT_MODEL_FAMILY,
    alpha: float = 1.0,
    fit_prior: bool = True,
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
                    # TF-IDF weights stay non-negative, which is what
                    # MultinomialNB requires of its features.
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                build_classifier(
                    model_family,
                    class_weight=class_weight,
                    max_iter=max_iter,
                    random_state=random_state,
                    alpha=alpha,
                    fit_prior=fit_prior,
                ),
            ),
        ]
    )


def render_metrics(
    *,
    input_path: Path,
    label_column: str,
    text_columns: list[str],
    model_family: str,
    input_rows: int,
    usable_rows: int,
    train_rows: int,
    test_rows: int,
    label_counts: pd.Series,
    accuracy: float,
    macro_f1: float,
    weighted_f1: float,
    report: str,
    hyperparameters: dict[str, Any] | None = None,
    evaluation: EvaluationResult | None = None,
) -> str:
    lines = [
        "Publication text classifier",
        "",
        f"model_family: {model_family}",
        f"input_csv: {input_path}",
        f"label_column: {label_column}",
        f"text_columns: {', '.join(text_columns)}",
        f"input_rows: {input_rows}",
        f"usable_rows: {usable_rows}",
        f"train_rows: {train_rows}",
        f"test_rows: {test_rows}",
        f"class_count: {len(label_counts)}",
        f"accuracy: {accuracy:.4f}",
        f"macro_f1: {macro_f1:.4f}",
        f"weighted_f1: {weighted_f1:.4f}",
    ]
    if hyperparameters:
        lines.extend(["", "Hyperparameters:"])
        lines.extend(f"{name}: {value}" for name, value in hyperparameters.items())
    lines.extend(["", "Class distribution:"])
    lines.extend(f"{label}: {count}" for label, count in label_counts.items())
    lines.extend(["", "Classification report:", report])
    if evaluation is not None:
        lines.extend(["", render_evaluation(evaluation)])
    return "\n".join(lines).rstrip() + "\n"


def family_hyperparameters(config: TextTrainingConfig) -> dict[str, Any]:
    """The knobs that actually applied to this run, and only those."""

    shared: dict[str, Any] = {
        "max_features": config.max_features,
        "min_df": config.min_df,
        "max_df": config.max_df,
        "ngram_max": config.ngram_max,
        "keep_stop_words": config.keep_stop_words,
    }
    if config.model_family == MODEL_FAMILY_MULTINOMIAL_NB:
        return {**shared, "alpha": config.alpha, "fit_prior": config.fit_prior}
    return {**shared, "class_weight": config.class_weight, "max_iter": config.max_iter}


def write_label_counts(path: Path, label_counts: pd.Series) -> None:
    rows = [
        {"label": label, "count": int(count)} for label, count in label_counts.items()
    ]
    write_csv_artifact(path, fieldnames=["label", "count"], rows=rows)


def write_predictions(
    path: Path,
    *,
    test_text: pd.Series,
    test_labels: pd.Series,
    predictions: Iterable[str],
) -> None:
    write_csv_artifact(
        path,
        fieldnames=["source_row", "label", "prediction", "correct", "text"],
        rows=prediction_rows(
            test_text=test_text,
            test_labels=test_labels,
            predictions=predictions,
        ),
    )


def prediction_rows(
    *,
    test_text: pd.Series,
    test_labels: pd.Series,
    predictions: Iterable[str],
) -> list[dict[str, Any]]:
    return [
        {
            "source_row": source_row,
            "label": label,
            "prediction": prediction,
            "correct": label == prediction,
            "text": text,
        }
        for source_row, text, label, prediction in zip(
            test_text.index,
            test_text,
            test_labels,
            predictions,
            strict=True,
        )
    ]


def resolved_config(config: TextTrainingConfig) -> TextTrainingConfig:
    return TextTrainingConfig(
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
        confusion_matrix_output=config.confusion_matrix_output
        or default_confusion_matrix_output(config.label_column, config.model_family),
        per_class_output=config.per_class_output
        or default_per_class_output(config.label_column, config.model_family),
        test_size=config.test_size,
        random_state=config.random_state,
        max_rows=config.max_rows,
        min_class_count=config.min_class_count,
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        keep_stop_words=config.keep_stop_words,
        # Class weighting is a Logistic Regression setting. Carrying the default
        # into a Naive Bayes run would put a knob in the manifest that the run
        # never used, so it is cleared here rather than silently ignored later.
        class_weight=(
            config.class_weight
            if config.model_family == MODEL_FAMILY_LOGISTIC_REGRESSION
            else None
        ),
        max_iter=config.max_iter,
        alpha=config.alpha,
        fit_prior=config.fit_prior,
    )


def json_ready_dataclass(value: object) -> dict[str, object]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def write_manifest(
    path: Path,
    *,
    config: TextTrainingConfig,
    result: TrainingResult,
    label_counts: pd.Series,
) -> None:
    manifest = {
        "config": json_ready_dataclass(config),
        "result": json_ready_dataclass(result),
        "label_counts": {
            str(label): int(count) for label, count in label_counts.items()
        },
        "artifacts": {
            "model": str(result.model_output),
            "metrics": str(result.metrics_output),
            "label_counts": str(result.label_counts_output),
            "predictions": str(result.predictions_output),
            "manifest": str(result.manifest_output),
        },
    }
    write_json_artifact(path, manifest)


def validate_config(config: TextTrainingConfig) -> None:
    if config.model_family not in SUPPORTED_MODEL_FAMILIES:
        raise ValueError(
            f"Unsupported model_family: {config.model_family}. "
            f"Supported values: {', '.join(SUPPORTED_MODEL_FAMILIES)}."
        )
    if not 0 < config.test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    if config.min_class_count < 2:
        raise ValueError("min_class_count must be at least 2 for stratified splitting")
    if config.model_family == MODEL_FAMILY_MULTINOMIAL_NB and config.alpha <= 0:
        raise ValueError("alpha must be greater than 0")


def train_text_classifier(config: TextTrainingConfig) -> TrainingResult:
    """Train a configured publication text classifier and write run artifacts."""

    config = resolved_config(config)
    validate_config(config)
    text_columns = list(config.text_columns)

    training_frame, input_rows, label_counts = load_training_frame(
        config.input_path,
        label_column=config.label_column,
        text_columns=text_columns,
        min_class_count=config.min_class_count,
        max_rows=config.max_rows,
    )

    train_text, test_text, train_labels, test_labels = train_test_split(
        training_frame["text"],
        training_frame["label"],
        test_size=config.test_size,
        random_state=config.random_state,
        stratify=training_frame["label"],
    )

    pipeline = build_pipeline(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        keep_stop_words=config.keep_stop_words,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        random_state=config.random_state,
        model_family=config.model_family,
        alpha=config.alpha,
        fit_prior=config.fit_prior,
    )
    pipeline.fit(train_text, train_labels)

    predictions = pipeline.predict(test_text)
    accuracy = accuracy_score(test_labels, predictions)
    macro_f1 = f1_score(test_labels, predictions, average="macro", zero_division=0)
    weighted_f1 = f1_score(
        test_labels, predictions, average="weighted", zero_division=0
    )
    report = classification_report(test_labels, predictions, zero_division=0)

    # Every family is scored through the same evaluation pipeline, so runs stay
    # comparable and the confusion matrix and per-class results come out of one
    # implementation rather than one per model.
    evaluation = evaluate_predictions(
        test_labels,
        predictions,
        run_name=artifact_stem(config.model_family, config.label_column),
        labels=[str(label) for label in label_counts.index],
        metadata={
            "model_family": config.model_family,
            "input_csv": str(config.input_path),
            "label_column": config.label_column,
            "text_columns": list(text_columns),
            "train_rows": len(train_text),
            "test_rows": len(test_text),
            "hyperparameters": family_hyperparameters(config),
        },
    )

    assert config.model_output is not None
    assert config.metrics_output is not None
    assert config.label_counts_output is not None
    assert config.predictions_output is not None
    assert config.manifest_output is not None
    assert config.confusion_matrix_output is not None
    assert config.per_class_output is not None

    metrics_text = render_metrics(
        input_path=config.input_path,
        label_column=config.label_column,
        text_columns=text_columns,
        model_family=config.model_family,
        input_rows=input_rows,
        usable_rows=len(training_frame),
        train_rows=len(train_text),
        test_rows=len(test_text),
        label_counts=label_counts,
        accuracy=accuracy,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        report=report,
        hyperparameters=family_hyperparameters(config),
        evaluation=evaluation,
    )

    result = TrainingResult(
        model_output=config.model_output,
        metrics_output=config.metrics_output,
        label_counts_output=config.label_counts_output,
        predictions_output=config.predictions_output,
        manifest_output=config.manifest_output,
        input_rows=input_rows,
        usable_rows=len(training_frame),
        train_rows=len(train_text),
        test_rows=len(test_text),
        class_count=len(label_counts),
        accuracy=accuracy,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        confusion_matrix_output=config.confusion_matrix_output,
        per_class_output=config.per_class_output,
        balanced_accuracy=evaluation.balanced_accuracy,
    )
    saved_artifacts = save_model_artifacts(
        model=pipeline,
        model_output=config.model_output,
        metrics_text=metrics_text,
        metrics_output=config.metrics_output,
        label_counts=label_counts,
        label_counts_output=config.label_counts_output,
        predictions=prediction_rows(
            test_text=test_text,
            test_labels=test_labels,
            predictions=predictions,
        ),
        predictions_output=config.predictions_output,
        manifest_output=config.manifest_output,
        manifest_config=json_ready_dataclass(config),
        manifest_result=json_ready_dataclass(result),
        extra_csv_artifacts=(
            CsvArtifactSpec(
                name="confusion_matrix",
                path=config.confusion_matrix_output,
                fieldnames=evaluation.confusion.fieldnames,
                rows=confusion_matrix_rows(evaluation),
            ),
            CsvArtifactSpec(
                name="per_class",
                path=config.per_class_output,
                fieldnames=PER_CLASS_FIELDNAMES,
                rows=per_class_rows(evaluation),
            ),
        ),
    )
    return replace(result, model_sha256=saved_artifacts.model.sha256)


def train_logistic_regression_classifier(
    *,
    input_path: Path = DEFAULT_INPUT,
    label_column: str = DEFAULT_LABEL_COLUMN,
    text_columns: list[str] | tuple[str, ...] | None = None,
    model_output: Path | None = None,
    metrics_output: Path | None = None,
    label_counts_output: Path | None = None,
    predictions_output: Path | None = None,
    manifest_output: Path | None = None,
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
    """Backward-compatible wrapper for the default Logistic Regression pipeline."""

    return train_text_classifier(
        TextTrainingConfig(
            input_path=input_path,
            label_column=label_column,
            text_columns=tuple(text_columns or DEFAULT_TEXT_COLUMNS),
            model_family=DEFAULT_MODEL_FAMILY,
            model_output=model_output,
            metrics_output=metrics_output,
            label_counts_output=label_counts_output,
            predictions_output=predictions_output,
            manifest_output=manifest_output,
            test_size=test_size,
            random_state=random_state,
            max_rows=max_rows,
            min_class_count=min_class_count,
            max_features=max_features,
            min_df=min_df,
            max_df=max_df,
            ngram_max=ngram_max,
            keep_stop_words=keep_stop_words,
            class_weight=class_weight,
            max_iter=max_iter,
        )
    )


def train_multinomial_nb_classifier(
    *,
    input_path: Path = DEFAULT_INPUT,
    label_column: str = DEFAULT_LABEL_COLUMN,
    text_columns: list[str] | tuple[str, ...] | None = None,
    model_output: Path | None = None,
    metrics_output: Path | None = None,
    label_counts_output: Path | None = None,
    predictions_output: Path | None = None,
    manifest_output: Path | None = None,
    confusion_matrix_output: Path | None = None,
    per_class_output: Path | None = None,
    test_size: float = 0.2,
    random_state: int = 42,
    max_rows: int | None = None,
    min_class_count: int = 20,
    max_features: int = 50_000,
    min_df: int | float = 2,
    max_df: int | float = 0.95,
    ngram_max: int = 2,
    keep_stop_words: bool = False,
    alpha: float = 1.0,
    fit_prior: bool = True,
) -> TrainingResult:
    """Train the TF-IDF + Multinomial Naive Bayes baseline.

    The baseline every later model is measured against: it is fast, has two
    knobs, and its errors are easy to read off the confusion matrix, so a more
    expensive model has to justify itself against these numbers.
    """

    return train_text_classifier(
        TextTrainingConfig(
            input_path=input_path,
            label_column=label_column,
            text_columns=tuple(text_columns or DEFAULT_TEXT_COLUMNS),
            model_family=MODEL_FAMILY_MULTINOMIAL_NB,
            model_output=model_output,
            metrics_output=metrics_output,
            label_counts_output=label_counts_output,
            predictions_output=predictions_output,
            manifest_output=manifest_output,
            confusion_matrix_output=confusion_matrix_output,
            per_class_output=per_class_output,
            test_size=test_size,
            random_state=random_state,
            max_rows=max_rows,
            min_class_count=min_class_count,
            max_features=max_features,
            min_df=min_df,
            max_df=max_df,
            ngram_max=ngram_max,
            keep_stop_words=keep_stop_words,
            alpha=alpha,
            fit_prior=fit_prior,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train a reusable TF-IDF publication text classifier -- Logistic "
            "Regression or the Multinomial Naive Bayes baseline -- and write "
            "model, metrics, predictions, labels, evaluation and manifest "
            "artifacts."
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
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=None,
        help="Output held-out predictions CSV path. Default: data/models/logistic_regression_<label>_predictions.csv",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=None,
        help="Output run manifest JSON path. Default: data/models/logistic_regression_<label>_manifest.json",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=DEFAULT_TEST_SIZE,
        help="Held-out test fraction.",
    )
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
    parser.add_argument(
        "--model-family",
        choices=SUPPORTED_MODEL_FAMILIES,
        default=DEFAULT_MODEL_FAMILY,
        help=f"Classifier to train. Default: {DEFAULT_MODEL_FAMILY}",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1.0,
        help="Naive Bayes additive smoothing. Default: 1.0",
    )
    parser.add_argument(
        "--no-fit-prior",
        dest="fit_prior",
        action="store_false",
        help=(
            "Give Naive Bayes a uniform class prior instead of learning it, the "
            "closest this family has to balanced class weighting."
        ),
    )
    parser.set_defaults(fit_prior=True)
    parser.add_argument(
        "--confusion-matrix-output",
        type=Path,
        default=None,
        help="Output confusion-matrix CSV path. Default: data/models/<family>_<label>_confusion_matrix.csv",
    )
    parser.add_argument(
        "--per-class-output",
        type=Path,
        default=None,
        help="Output per-class results CSV path. Default: data/models/<family>_<label>_per_class.csv",
    )
    return parser.parse_args()


def result_summary(
    result: TrainingResult, *, model_family: str = DEFAULT_MODEL_FAMILY
) -> str:
    lines = [
        f"Trained {model_family} classifier on {result.usable_rows:,} rows.",
        f"Classes: {result.class_count:,}",
        f"Accuracy: {result.accuracy:.4f}",
        f"Balanced accuracy: {result.balanced_accuracy:.4f}",
        f"Macro F1: {result.macro_f1:.4f}",
        f"Model: {result.model_output}",
    ]
    if result.model_sha256:
        lines.append(f"Model SHA-256: {result.model_sha256}")
    lines.extend(
        [
            f"Metrics: {result.metrics_output}",
            f"Predictions: {result.predictions_output}",
            f"Confusion matrix: {result.confusion_matrix_output}",
            f"Per-class results: {result.per_class_output}",
            f"Manifest: {result.manifest_output}",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    result = train_text_classifier(
        TextTrainingConfig(
            input_path=args.input,
            label_column=args.label_column,
            text_columns=tuple(args.text_columns),
            model_family=args.model_family,
            model_output=args.model_output,
            metrics_output=args.metrics_output,
            label_counts_output=args.label_counts_output,
            predictions_output=args.predictions_output,
            manifest_output=args.manifest_output,
            confusion_matrix_output=args.confusion_matrix_output,
            per_class_output=args.per_class_output,
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
            alpha=args.alpha,
            fit_prior=args.fit_prior,
        )
    )
    print(result_summary(result, model_family=args.model_family))


if __name__ == "__main__":
    main()
