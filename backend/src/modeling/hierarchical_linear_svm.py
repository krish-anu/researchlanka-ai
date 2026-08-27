"""Two-level hierarchical Linear SVM: primary_field → primary_subfield.

Trains:
  1. One field-level TF-IDF + LinearSVC on `primary_field`
  2. One subfield-level TF-IDF + LinearSVC per field (on `primary_subfield`)

Taxonomy (`category_hierarchy.json`) is `{field: [subfields, ...]}` and is used
only to validate / document allowed pairs — not to invent a third level.

Prediction columns written by the predict helpers:
  predicted_field, predicted_subfield
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


from src.modeling.artifacts import (
    file_sha256,
    save_model_artifacts,
    write_json_artifact,
)

from src.preprocessing.text_cleaning import clean_text_series, CUSTOM_STOP_WORDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_with_field_subfield.csv"
)
DEFAULT_TAXONOMY = PROJECT_ROOT / "category_hierarchy.json"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models"
DEFAULT_MODEL_FAMILY = "linear_svm_hierarchical"

# Best Linear SVM defaults (aligned with flat trainer / config sweep)
DEFAULT_FIELD_COLUMN = "primary_field"
DEFAULT_SUBFIELD_COLUMN = "primary_subfield"
DEFAULT_TEXT_COLUMNS = ["title", "abstract", "topics", "keywords", "concepts"]
DEFAULT_C_VALUE = 1.0
DEFAULT_NGRAM_MAX = 3
DEFAULT_MAX_FEATURES = 50_000
DEFAULT_MIN_DF: int | float = 2
DEFAULT_MAX_DF: int | float = 0.95
DEFAULT_CLASS_WEIGHT: str | None = "balanced"
DEFAULT_MAX_ITER = 5000
DEFAULT_TEST_SIZE = 0.15

PRED_FIELD_COLUMN = "predicted_field"
PRED_SUBFIELD_COLUMN = "predicted_subfield"


@dataclass(frozen=True)
class HierarchicalTrainingConfig:
    """Configuration for field → subfield hierarchical Linear SVM training."""

    input_path: Path = DEFAULT_INPUT
    taxonomy_path: Path = DEFAULT_TAXONOMY
    field_column: str = DEFAULT_FIELD_COLUMN
    subfield_column: str = DEFAULT_SUBFIELD_COLUMN
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    model_family: str = DEFAULT_MODEL_FAMILY
    field_model_output: Path | None = None
    subfield_model_output: Path | None = None
    metrics_output: Path | None = None
    label_counts_output: Path | None = None
    manifest_output: Path | None = None
    test_size: float = DEFAULT_TEST_SIZE
    random_state: int = 42
    max_rows: int | None = None
    min_subfield_count: int = 2
    max_features: int = DEFAULT_MAX_FEATURES
    min_df: int | float = DEFAULT_MIN_DF
    max_df: int | float = DEFAULT_MAX_DF
    ngram_max: int = DEFAULT_NGRAM_MAX
    c_value: float = DEFAULT_C_VALUE
    class_weight: str | None = DEFAULT_CLASS_WEIGHT
    max_iter: int = DEFAULT_MAX_ITER


@dataclass(frozen=True)
class HierarchicalTrainingResult:
    """Paths and evaluation stats from one hierarchical training run."""

    field_model_output: Path
    subfield_model_output: Path
    metrics_output: Path
    label_counts_output: Path
    manifest_output: Path
    input_rows: int
    usable_rows: int
    field_class_count: int
    subfield_model_count: int
    field_accuracy: float | None
    field_macro_f1: float | None
    field_model_sha256: str = ""
    subfield_model_sha256: str = ""


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


def artifact_stem(model_family: str, suffix: str) -> str:
    return f"{slugify(model_family)}_{slugify(suffix)}"


def default_field_model_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'field')}.joblib"


def default_subfield_model_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'subfield')}.joblib"


def default_metrics_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'field')}_metrics.txt"


def default_label_counts_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'field')}_labels.csv"


def default_manifest_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'field')}_manifest.json"


# ---------------------------------------------------------------------------
# Taxonomy (2-level: field → subfields)
# ---------------------------------------------------------------------------


def load_taxonomy(path: Path) -> dict[str, list[str]]:
    """Load `{field: [subfield, ...]}` hierarchy."""
    with open(path, encoding="utf-8") as handle:
        taxonomy = json.load(handle)
    if not isinstance(taxonomy, dict):
        raise ValueError(f"Taxonomy must be an object: {path}")
    cleaned: dict[str, list[str]] = {}
    for field, subfields in taxonomy.items():
        if not isinstance(subfields, list):
            raise ValueError(
                f"Taxonomy entry for {field!r} must be a list of subfields "
                f"(2-level {{field: [subfields]}}). Got {type(subfields).__name__}."
            )
        cleaned[str(field)] = [str(s) for s in subfields]
    return cleaned


def subfield_to_field_lookup(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    """Map each subfield → its parent field (first parent wins on duplicates)."""
    lookup: dict[str, str] = {}
    for field, subfields in taxonomy.items():
        for subfield in subfields:
            lookup.setdefault(subfield, field)
    return lookup


# ---------------------------------------------------------------------------
# Text / pipeline
# ---------------------------------------------------------------------------


def combined_text(
    frame: pd.DataFrame,
    text_columns: Iterable[str],
    *,
    clean: bool = True,
) -> pd.Series:
    text = frame[list(text_columns)].fillna("").astype(str).agg(" ".join, axis=1)
    text = text.str.replace(r"\s+", " ", regex=True).str.strip()

    if clean:
        text = clean_text_series(text)

    return text


def build_pipeline(
    *,
    max_features: int,
    min_df: int | float,
    max_df: int | float,
    ngram_max: int,
    class_weight: str | None,
    max_iter: int,
    random_state: int,
    c_value: float,
) -> Pipeline:
    if ngram_max < 1:
        raise ValueError("ngram_max must be at least 1")
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    strip_accents="unicode",
                    lowercase=True,
                    stop_words=CUSTOM_STOP_WORDS,
                    ngram_range=(1, ngram_max),
                    min_df=min_df,
                    max_df=max_df,
                    max_features=None if max_features <= 0 else max_features,
                    sublinear_tf=True,
                ),
            ),
            (
                "svm",
                LinearSVC(
                    C=c_value,
                    class_weight=class_weight,
                    max_iter=max_iter,
                    random_state=random_state,
                    dual="auto",
                ),
            ),
        ]
    )


def fit_and_score(
    frame: pd.DataFrame,
    label_column: str,
    *,
    pipeline_kwargs: dict[str, Any],
    test_size: float,
    random_state: int,
) -> tuple[Pipeline, float | None, float | None]:
    """Fit a hold-out split for metrics, then refit on all rows."""
    can_stratify = (
        frame[label_column].value_counts().min() >= 2
        and frame[label_column].nunique() >= 2
    )
    accuracy: float | None = None
    macro_f1: float | None = None

    if can_stratify:
        train_frame, test_frame = train_test_split(
            frame,
            test_size=test_size,
            random_state=random_state,
            stratify=frame[label_column],
        )
        eval_model = build_pipeline(**pipeline_kwargs)
        eval_model.fit(train_frame["text"], train_frame[label_column])
        predictions = eval_model.predict(test_frame["text"])
        accuracy = float(accuracy_score(test_frame[label_column], predictions))
        macro_f1 = float(
            f1_score(
                test_frame[label_column],
                predictions,
                average="macro",
                zero_division=0,
            )
        )

    final_model = build_pipeline(**pipeline_kwargs)
    final_model.fit(frame["text"], frame[label_column])
    return final_model, accuracy, macro_f1


def load_labeled_frame(
    input_path: Path,
    *,
    field_column: str,
    subfield_column: str,
    text_columns: Iterable[str],
    max_rows: int | None,
) -> tuple[pd.DataFrame, int]:
    frame = pd.read_csv(input_path, nrows=max_rows, low_memory=False)
    input_rows = len(frame)
    labeled = frame[frame[field_column].notna() & frame[subfield_column].notna()].copy()
    labeled["text"] = combined_text(labeled, text_columns, clean=True)
    labeled = labeled[labeled["text"] != ""]
    if labeled.empty:
        raise ValueError("No usable training rows after filtering.")
    return labeled, input_rows


def resolved_config(config: HierarchicalTrainingConfig) -> HierarchicalTrainingConfig:
    return HierarchicalTrainingConfig(
        input_path=config.input_path,
        taxonomy_path=config.taxonomy_path,
        field_column=config.field_column,
        subfield_column=config.subfield_column,
        text_columns=config.text_columns,
        model_family=config.model_family,
        field_model_output=config.field_model_output
        or default_field_model_output(config.model_family),
        subfield_model_output=config.subfield_model_output
        or default_subfield_model_output(config.model_family),
        metrics_output=config.metrics_output
        or default_metrics_output(config.model_family),
        label_counts_output=config.label_counts_output
        or default_label_counts_output(config.model_family),
        manifest_output=config.manifest_output
        or default_manifest_output(config.model_family),
        test_size=config.test_size,
        random_state=config.random_state,
        max_rows=config.max_rows,
        min_subfield_count=config.min_subfield_count,
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        c_value=config.c_value,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
    )


def validate_config(config: HierarchicalTrainingConfig) -> None:
    if not 0 < config.test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    if config.ngram_max < 1:
        raise ValueError("ngram_max must be at least 1")
    if config.c_value <= 0:
        raise ValueError("c_value must be positive")
    if config.min_subfield_count < 2:
        raise ValueError("min_subfield_count must be at least 2")


def json_ready_dataclass(value: object) -> dict[str, object]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def render_metrics(
    *,
    config: HierarchicalTrainingConfig,
    input_rows: int,
    usable_rows: int,
    field_label_counts: pd.Series,
    subfield_model_count: int,
    field_accuracy: float | None,
    field_macro_f1: float | None,
) -> str:
    lines = [
        "Publication hierarchical Linear SVM (field → subfield)",
        "",
        f"model_family: {config.model_family}",
        f"input_csv: {config.input_path}",
        f"taxonomy_json: {config.taxonomy_path}",
        f"field_column: {config.field_column}",
        f"subfield_column: {config.subfield_column}",
        f"text_columns: {', '.join(config.text_columns)}",
        f"ngram_max: {config.ngram_max}",
        f"c_value: {config.c_value}",
        f"class_weight: {config.class_weight}",
        f"input_rows: {input_rows}",
        f"usable_rows: {usable_rows}",
        f"field_class_count: {len(field_label_counts)}",
        f"subfield_model_count: {subfield_model_count}",
    ]
    if field_accuracy is not None and field_macro_f1 is not None:
        lines.append(f"field_accuracy: {field_accuracy:.4f}")
        lines.append(f"field_macro_f1: {field_macro_f1:.4f}")
    else:
        lines.append("field_accuracy: n/a")
    lines.extend(["", "Field class distribution:"])
    lines.extend(f"{label}: {count}" for label, count in field_label_counts.items())
    return "\n".join(lines).rstrip() + "\n"


def train_hierarchical_classifier(
    config: HierarchicalTrainingConfig | None = None,
) -> HierarchicalTrainingResult:
    """Train field classifier + one subfield classifier per field."""
    config = resolved_config(config or HierarchicalTrainingConfig())
    validate_config(config)

    # Taxonomy is optional at train time; validate shape if present.
    if config.taxonomy_path.exists():
        load_taxonomy(config.taxonomy_path)

    labeled, input_rows = load_labeled_frame(
        config.input_path,
        field_column=config.field_column,
        subfield_column=config.subfield_column,
        text_columns=config.text_columns,
        max_rows=config.max_rows,
    )

    pipeline_kwargs = dict(
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        random_state=config.random_state,
        c_value=config.c_value,
    )

    field_model, field_accuracy, field_macro_f1 = fit_and_score(
        labeled,
        config.field_column,
        pipeline_kwargs=pipeline_kwargs,
        test_size=config.test_size,
        random_state=config.random_state,
    )

    subfield_models: dict[str, Pipeline] = {}
    for field in sorted(labeled[config.field_column].astype(str).unique()):
        field_frame = labeled[labeled[config.field_column].astype(str) == field]
        if field_frame[config.subfield_column].nunique() < config.min_subfield_count:
            continue
        model, _, _ = fit_and_score(
            field_frame,
            config.subfield_column,
            pipeline_kwargs=pipeline_kwargs,
            test_size=config.test_size,
            random_state=config.random_state,
        )
        subfield_models[field] = model

    field_label_counts = labeled[config.field_column].value_counts()

    assert config.field_model_output is not None
    assert config.subfield_model_output is not None
    assert config.metrics_output is not None
    assert config.label_counts_output is not None
    assert config.manifest_output is not None

    metrics_text = render_metrics(
        config=config,
        input_rows=input_rows,
        usable_rows=len(labeled),
        field_label_counts=field_label_counts,
        subfield_model_count=len(subfield_models),
        field_accuracy=field_accuracy,
        field_macro_f1=field_macro_f1,
    )

    result = HierarchicalTrainingResult(
        field_model_output=config.field_model_output,
        subfield_model_output=config.subfield_model_output,
        metrics_output=config.metrics_output,
        label_counts_output=config.label_counts_output,
        manifest_output=config.manifest_output,
        input_rows=input_rows,
        usable_rows=len(labeled),
        field_class_count=int(labeled[config.field_column].nunique()),
        subfield_model_count=len(subfield_models),
        field_accuracy=field_accuracy,
        field_macro_f1=field_macro_f1,
    )

    saved_field = save_model_artifacts(
        model=field_model,
        model_output=config.field_model_output,
        metrics_text=metrics_text,
        metrics_output=config.metrics_output,
        label_counts=field_label_counts,
        label_counts_output=config.label_counts_output,
        predictions=[],
        predictions_output=None,
        manifest_output=config.manifest_output,
        manifest_config=json_ready_dataclass(config),
        manifest_result=json_ready_dataclass(result),
    )

    config.subfield_model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(subfield_models, config.subfield_model_output)
    subfield_sha = file_sha256(config.subfield_model_output)

    write_json_artifact(
        config.manifest_output,
        {
            "config": json_ready_dataclass(config),
            "result": {
                **json_ready_dataclass(result),
                "field_model_sha256": saved_field.model.sha256,
                "subfield_model_sha256": subfield_sha,
            },
            "field_label_counts": {
                str(label): int(count) for label, count in field_label_counts.items()
            },
            "subfield_models_trained_for": sorted(subfield_models),
            "prediction_columns": [PRED_FIELD_COLUMN, PRED_SUBFIELD_COLUMN],
        },
    )

    return HierarchicalTrainingResult(
        field_model_output=result.field_model_output,
        subfield_model_output=result.subfield_model_output,
        metrics_output=result.metrics_output,
        label_counts_output=result.label_counts_output,
        manifest_output=result.manifest_output,
        input_rows=result.input_rows,
        usable_rows=result.usable_rows,
        field_class_count=result.field_class_count,
        subfield_model_count=result.subfield_model_count,
        field_accuracy=result.field_accuracy,
        field_macro_f1=result.field_macro_f1,
        field_model_sha256=saved_field.model.sha256,
        subfield_model_sha256=subfield_sha,
    )


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def load_hierarchical_models(
    field_model_path: Path, subfield_model_path: Path
) -> tuple[Pipeline, dict[str, Pipeline]]:
    field_model = joblib.load(field_model_path)
    subfield_models = joblib.load(subfield_model_path)
    return field_model, subfield_models


def predict_field_subfield(
    frame: pd.DataFrame,
    *,
    field_model: Pipeline,
    subfield_models: dict[str, Pipeline],
    text_columns: Iterable[str],
    only_unlabeled: bool = False,
    field_column: str = DEFAULT_FIELD_COLUMN,
    subfield_column: str = DEFAULT_SUBFIELD_COLUMN,
) -> pd.DataFrame:
    """Add predicted_field / predicted_subfield columns.

    If only_unlabeled=True, only rows missing field or subfield labels are
    scored; labeled rows keep null prediction columns (or existing values left).
    """
    out = frame.copy()
    texts = combined_text(out, text_columns)
    has_text = texts.str.len() > 0

    if only_unlabeled:
        needs_pred = has_text & (
            out[field_column].isna() | out[subfield_column].isna()
            if field_column in out.columns and subfield_column in out.columns
            else has_text
        )
    else:
        needs_pred = has_text

    out[PRED_FIELD_COLUMN] = pd.NA
    out[PRED_SUBFIELD_COLUMN] = pd.NA

    if needs_pred.sum() == 0:
        return out

    pred_texts = texts[needs_pred]
    field_preds = field_model.predict(pred_texts)
    out.loc[needs_pred, PRED_FIELD_COLUMN] = field_preds

    for field_name, model in subfield_models.items():
        mask = needs_pred & (out[PRED_FIELD_COLUMN].astype(str) == str(field_name))
        if mask.sum() == 0:
            continue
        out.loc[mask, PRED_SUBFIELD_COLUMN] = model.predict(texts[mask])

    return out


def run_field_subfield_prediction(
    *,
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    field_model_path: Path | None = None,
    subfield_model_path: Path | None = None,
    text_columns: Iterable[str] = DEFAULT_TEXT_COLUMNS,
    only_unlabeled: bool = True,
    field_column: str = DEFAULT_FIELD_COLUMN,
    subfield_column: str = DEFAULT_SUBFIELD_COLUMN,
) -> pd.DataFrame:
    """Load models, predict field/subfield, write CSV with new columns."""
    field_model_path = field_model_path or default_field_model_output()
    subfield_model_path = subfield_model_path or default_subfield_model_output()

    frame = pd.read_csv(input_path, low_memory=False)
    field_model, subfield_models = load_hierarchical_models(
        field_model_path, subfield_model_path
    )
    result = predict_field_subfield(
        frame,
        field_model=field_model,
        subfield_models=subfield_models,
        text_columns=text_columns,
        only_unlabeled=only_unlabeled,
        field_column=field_column,
        subfield_column=subfield_column,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train hierarchical TF-IDF + LinearSVC classifiers for "
            "primary_field → primary_subfield (2 levels only)."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--field-column", default=DEFAULT_FIELD_COLUMN)
    parser.add_argument("--subfield-column", default=DEFAULT_SUBFIELD_COLUMN)
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns",
    )
    parser.add_argument("--field-model-output", type=Path, default=None)
    parser.add_argument("--subfield-model-output", type=Path, default=None)
    parser.add_argument("--metrics-output", type=Path, default=None)
    parser.add_argument("--label-counts-output", type=Path, default=None)
    parser.add_argument("--manifest-output", type=Path, default=None)
    parser.add_argument("--test-size", type=float, default=DEFAULT_TEST_SIZE)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--min-subfield-count", type=int, default=2)
    parser.add_argument("--max-features", type=int, default=DEFAULT_MAX_FEATURES)
    parser.add_argument(
        "--min-df", type=parse_document_frequency, default=DEFAULT_MIN_DF
    )
    parser.add_argument(
        "--max-df", type=parse_document_frequency, default=DEFAULT_MAX_DF
    )
    parser.add_argument("--ngram-max", type=int, default=DEFAULT_NGRAM_MAX)
    parser.add_argument("--c-value", type=float, default=DEFAULT_C_VALUE)
    parser.add_argument("--class-weight", type=parse_class_weight, default="balanced")

    parser.add_argument("--max-iter", type=int, default=DEFAULT_MAX_ITER)

    parser.add_argument(
        "--predict-output",
        type=Path,
        default=None,
        help="If set, run the trained models over the input CSV and save "
        "linearsvm_domain/field/subfield predictions here.",
    )

    return parser.parse_args()


def result_summary(result: HierarchicalTrainingResult) -> str:
    lines = [
        f"Trained hierarchical Linear SVM on {result.usable_rows:,} rows.",
        f"Field classes: {result.field_class_count:,}",
        f"Subfield models: {result.subfield_model_count:,}",
    ]
    if result.field_accuracy is not None:
        lines.append(f"Field accuracy: {result.field_accuracy:.4f}")
        lines.append(f"Field macro F1: {result.field_macro_f1:.4f}")
    lines.append(f"Field model: {result.field_model_output}")
    lines.append(f"Subfield models: {result.subfield_model_output}")
    lines.append(f"Metrics: {result.metrics_output}")
    lines.append(f"Manifest: {result.manifest_output}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    result = train_hierarchical_classifier(
        HierarchicalTrainingConfig(
            input_path=args.input,
            taxonomy_path=args.taxonomy,
            field_column=args.field_column,
            subfield_column=args.subfield_column,
            text_columns=tuple(args.text_columns),
            field_model_output=args.field_model_output,
            subfield_model_output=args.subfield_model_output,
            metrics_output=args.metrics_output,
            label_counts_output=args.label_counts_output,
            manifest_output=args.manifest_output,
            test_size=args.test_size,
            random_state=args.random_state,
            max_rows=args.max_rows,
            min_subfield_count=args.min_subfield_count,
            max_features=args.max_features,
            min_df=args.min_df,
            max_df=args.max_df,
            ngram_max=args.ngram_max,
            c_value=args.c_value,
            class_weight=args.class_weight,
            max_iter=args.max_iter,
        )
    )
    print(result_summary(result))
    if args.predict_output:
        lookup = load_taxonomy(config.taxonomy_path)
        run_hierarchical_prediction(
            input_path=config.input_path,
            output_path=args.predict_output,
            domain_model_path=result.domain_model_output,
            subfield_model_path=result.subfield_model_output,
            taxonomy_path=config.taxonomy_path,
            text_columns=config.text_columns,
        )
        print(f"Predictions written to: {args.predict_output}")


if __name__ == "__main__":
    main()
