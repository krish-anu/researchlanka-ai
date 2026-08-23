"""Hierarchical Linear SVM pipeline for publication text classification.

Trains two layers of TF-IDF + LinearSVC classifiers and combines them with a
taxonomy lookup to assign a full domain/field/subfield hierarchy to each
publication:

    Domain model (primary_field)
            |
    Domain-specific subfield models (primary_subfield)
            |
    Field lookup (domain, subfield) -> field, via category_hierarchy.json

Generates the columns: linearsvm_domain, linearsvm_field, linearsvm_subfield

Mirrors the structure of the flat Linear SVM pipeline (linear_svm.py) and the
Logistic Regression reference pipeline: dataclass-based configuration, a
single training entry point, and structured artifacts written via
save_model_artifacts (joblib-backed).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from src.modeling.artifacts import (
    SavedArtifact,
    SavedModelArtifacts,
    file_sha256,
    save_model_artifacts,
    write_csv_artifact,
    write_json_artifact,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

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
    / "common_publications_final_with_linearsvm.csv"
)
DEFAULT_TAXONOMY = PROJECT_ROOT / "data" / "taxonomy" / "category_hierarchy.json"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models"
DEFAULT_MODEL_FAMILY = "linear_svm_hierarchical"
DEFAULT_DOMAIN_COLUMN = "primary_field"
DEFAULT_SUBFIELD_COLUMN = "primary_subfield"
DEFAULT_TEXT_COLUMNS = ["title", "abstract", "topics", "keywords", "concepts"]


@dataclass(frozen=True)
class HierarchicalTrainingConfig:
    """Configuration for one hierarchical Linear SVM training run."""

    input_path: Path = DEFAULT_INPUT
    taxonomy_path: Path = DEFAULT_TAXONOMY
    domain_column: str = DEFAULT_DOMAIN_COLUMN
    subfield_column: str = DEFAULT_SUBFIELD_COLUMN
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    model_family: str = DEFAULT_MODEL_FAMILY
    domain_model_output: Path | None = None
    subfield_model_output: Path | None = None
    metrics_output: Path | None = None
    label_counts_output: Path | None = None
    manifest_output: Path | None = None
    test_size: float = 0.15
    random_state: int = 42
    max_rows: int | None = None
    min_subfield_count: int = 2
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 3
    c_value: float = 1.0
    class_weight: str | None = "balanced"
    max_iter: int = 5000


@dataclass(frozen=True)
class HierarchicalTrainingResult:
    """Paths and evaluation stats produced by one hierarchical training run."""

    domain_model_output: Path
    subfield_model_output: Path
    metrics_output: Path
    label_counts_output: Path
    manifest_output: Path
    input_rows: int
    usable_rows: int
    domain_class_count: int
    subfield_model_count: int
    domain_accuracy: float | None
    domain_macro_f1: float | None
    domain_model_sha256: str = ""
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


def default_domain_model_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'domain')}.joblib"


def default_subfield_model_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'subfield')}.joblib"


def default_metrics_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'domain')}_metrics.txt"


def default_label_counts_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'domain')}_labels.csv"


def default_manifest_output(model_family: str = DEFAULT_MODEL_FAMILY) -> Path:
    return DEFAULT_MODEL_DIR / f"{artifact_stem(model_family, 'domain')}_manifest.json"


# ============================================================================
# Taxonomy lookup
# ============================================================================


def build_lookup(taxonomy: dict) -> dict[tuple[str, str], str]:
    """Convert {domain: {field: [subfields]}} into {(domain, subfield): field}."""
    lookup: dict[tuple[str, str], str] = {}
    for domain, fields in taxonomy.items():
        for field, subfields in fields.items():
            for subfield in subfields:
                lookup[(domain, subfield)] = field
    return lookup


def load_taxonomy(path: Path) -> dict[tuple[str, str], str]:
    with open(path, "r", encoding="utf-8") as handle:
        taxonomy = json.load(handle)
    return build_lookup(taxonomy)


# ============================================================================
# Text preparation
# ============================================================================


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


# ============================================================================
# Pipeline construction
# ============================================================================


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
    """Fit a held-out split for evaluation, then refit on all rows.

    Returns (model refit on all of `frame`, accuracy, macro_f1). The
    evaluation metrics are None when the label column doesn't have enough
    per-class examples to stratify a held-out split.
    """
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
        accuracy = accuracy_score(test_frame[label_column], predictions)
        macro_f1 = f1_score(
            test_frame[label_column], predictions, average="macro", zero_division=0
        )

    final_model = build_pipeline(**pipeline_kwargs)
    final_model.fit(frame["text"], frame[label_column])
    return final_model, accuracy, macro_f1


# ============================================================================
# Data loading
# ============================================================================


def load_labeled_frame(
    input_path: Path,
    *,
    domain_column: str,
    subfield_column: str,
    text_columns: Iterable[str],
    max_rows: int | None,
) -> tuple[pd.DataFrame, int]:
    frame = pd.read_csv(input_path, nrows=max_rows)
    input_rows = len(frame)

    labeled = frame[
        frame[domain_column].notna() & frame[subfield_column].notna()
    ].copy()
    labeled["text"] = combined_text(labeled, text_columns, clean=True)
    labeled = labeled[labeled["text"] != ""]

    if labeled.empty:
        raise ValueError("No usable training rows after filtering.")

    return labeled, input_rows


# ============================================================================
# Metrics / manifest
# ============================================================================


def render_metrics(
    *,
    config: HierarchicalTrainingConfig,
    input_rows: int,
    usable_rows: int,
    domain_label_counts: pd.Series,
    subfield_model_count: int,
    domain_accuracy: float | None,
    domain_macro_f1: float | None,
) -> str:
    lines = [
        "Publication hierarchical Linear SVM classifier",
        "",
        f"model_family: {config.model_family}",
        f"input_csv: {config.input_path}",
        f"taxonomy_json: {config.taxonomy_path}",
        f"domain_column: {config.domain_column}",
        f"subfield_column: {config.subfield_column}",
        f"text_columns: {', '.join(config.text_columns)}",
        f"input_rows: {input_rows}",
        f"usable_rows: {usable_rows}",
        f"domain_class_count: {len(domain_label_counts)}",
        f"subfield_model_count: {subfield_model_count}",
    ]
    if domain_accuracy is not None and domain_macro_f1 is not None:
        lines.append(f"domain_accuracy: {domain_accuracy:.4f}")
        lines.append(f"domain_macro_f1: {domain_macro_f1:.4f}")
    else:
        lines.append(
            "domain_accuracy: n/a (not enough rows per class to hold out a split)"
        )
    lines.extend(["", "Domain class distribution:"])
    lines.extend(f"{label}: {count}" for label, count in domain_label_counts.items())
    return "\n".join(lines).rstrip() + "\n"


def write_label_counts(path: Path, label_counts: pd.Series) -> None:
    rows = [
        {"label": label, "count": int(count)} for label, count in label_counts.items()
    ]
    write_csv_artifact(path, fieldnames=["label", "count"], rows=rows)


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
    config: HierarchicalTrainingConfig,
    result: HierarchicalTrainingResult,
    domain_label_counts: pd.Series,
    subfield_domains: list[str],
) -> None:
    manifest = {
        "config": json_ready_dataclass(config),
        "result": json_ready_dataclass(result),
        "domain_label_counts": {
            str(label): int(count) for label, count in domain_label_counts.items()
        },
        "subfield_models_trained_for": subfield_domains,
        "artifacts": {
            "domain_model": str(result.domain_model_output),
            "subfield_model": str(result.subfield_model_output),
            "metrics": str(result.metrics_output),
            "label_counts": str(result.label_counts_output),
            "manifest": str(result.manifest_output),
        },
    }
    write_json_artifact(path, manifest)


def resolved_config(config: HierarchicalTrainingConfig) -> HierarchicalTrainingConfig:
    return HierarchicalTrainingConfig(
        input_path=config.input_path,
        taxonomy_path=config.taxonomy_path,
        domain_column=config.domain_column,
        subfield_column=config.subfield_column,
        text_columns=config.text_columns,
        model_family=config.model_family,
        domain_model_output=config.domain_model_output
        or default_domain_model_output(config.model_family),
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


# ============================================================================
# Training
# ============================================================================


def train_hierarchical_classifier(
    config: HierarchicalTrainingConfig,
) -> HierarchicalTrainingResult:
    """Train a domain classifier and one subfield classifier per domain."""

    config = resolved_config(config)
    validate_config(config)

    labeled, input_rows = load_labeled_frame(
        config.input_path,
        domain_column=config.domain_column,
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

    domain_model, domain_accuracy, domain_macro_f1 = fit_and_score(
        labeled,
        config.domain_column,
        pipeline_kwargs=pipeline_kwargs,
        test_size=config.test_size,
        random_state=config.random_state,
    )

    subfield_models: dict[str, Pipeline] = {}
    for domain in sorted(labeled[config.domain_column].unique()):
        domain_frame = labeled[labeled[config.domain_column] == domain]
        if domain_frame[config.subfield_column].nunique() < config.min_subfield_count:
            continue
        model, _, _ = fit_and_score(
            domain_frame,
            config.subfield_column,
            pipeline_kwargs=pipeline_kwargs,
            test_size=config.test_size,
            random_state=config.random_state,
        )
        subfield_models[domain] = model

    domain_label_counts = labeled[config.domain_column].value_counts()

    assert config.domain_model_output is not None
    assert config.subfield_model_output is not None
    assert config.metrics_output is not None
    assert config.label_counts_output is not None
    assert config.manifest_output is not None

    metrics_text = render_metrics(
        config=config,
        input_rows=input_rows,
        usable_rows=len(labeled),
        domain_label_counts=domain_label_counts,
        subfield_model_count=len(subfield_models),
        domain_accuracy=domain_accuracy,
        domain_macro_f1=domain_macro_f1,
    )

    result = HierarchicalTrainingResult(
        domain_model_output=config.domain_model_output,
        subfield_model_output=config.subfield_model_output,
        metrics_output=config.metrics_output,
        label_counts_output=config.label_counts_output,
        manifest_output=config.manifest_output,
        input_rows=input_rows,
        usable_rows=len(labeled),
        domain_class_count=labeled[config.domain_column].nunique(),
        subfield_model_count=len(subfield_models),
        domain_accuracy=domain_accuracy,
        domain_macro_f1=domain_macro_f1,
    )

    # Domain model: full structured artifact set (metrics/labels/manifest live here).
    saved_domain_artifacts = save_model_artifacts(
        model=domain_model,
        model_output=config.domain_model_output,
        metrics_text=metrics_text,
        metrics_output=config.metrics_output,
        label_counts=domain_label_counts,
        label_counts_output=config.label_counts_output,
        predictions=[],
        predictions_output=None,
        manifest_output=config.manifest_output,
        manifest_config=json_ready_dataclass(config),
        manifest_result=json_ready_dataclass(result),
    )

    # Subfield models: one dict of per-domain pipelines saved as a single joblib artifact.
    config.subfield_model_output.parent.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(subfield_models, config.subfield_model_output)
    subfield_model_sha256 = file_sha256(config.subfield_model_output)

    write_manifest(
        config.manifest_output,
        config=config,
        result=result,
        domain_label_counts=domain_label_counts,
        subfield_domains=sorted(subfield_models),
    )

    result = HierarchicalTrainingResult(
        domain_model_output=result.domain_model_output,
        subfield_model_output=result.subfield_model_output,
        metrics_output=result.metrics_output,
        label_counts_output=result.label_counts_output,
        manifest_output=result.manifest_output,
        input_rows=result.input_rows,
        usable_rows=result.usable_rows,
        domain_class_count=result.domain_class_count,
        subfield_model_count=result.subfield_model_count,
        domain_accuracy=result.domain_accuracy,
        domain_macro_f1=result.domain_macro_f1,
        domain_model_sha256=saved_domain_artifacts.model.sha256,
        subfield_model_sha256=subfield_model_sha256,
    )
    return result


# ============================================================================
# Prediction
# ============================================================================


def load_hierarchical_models(
    domain_model_path: Path, subfield_model_path: Path
) -> tuple[Pipeline, dict[str, Pipeline]]:
    import joblib

    domain_model = joblib.load(domain_model_path)
    subfield_models = joblib.load(subfield_model_path)
    return domain_model, subfield_models


def predict_hierarchy(
    frame: pd.DataFrame,
    *,
    domain_model: Pipeline,
    subfield_models: dict[str, Pipeline],
    lookup: dict[tuple[str, str], str],
    text_columns: Iterable[str],
) -> pd.DataFrame:
    """Predict domain, subfield, and looked-up field for every row with text."""
    frame = frame.copy()
    frame["text"] = combined_text(frame, text_columns)
    has_text = frame["text"].str.len() > 0

    frame["linearsvm_domain"] = None
    frame.loc[has_text, "linearsvm_domain"] = domain_model.predict(
        frame.loc[has_text, "text"]
    )

    frame["linearsvm_subfield"] = None
    for domain, model in subfield_models.items():
        mask = (frame["linearsvm_domain"] == domain) & has_text
        if mask.sum() == 0:
            continue
        frame.loc[mask, "linearsvm_subfield"] = model.predict(frame.loc[mask, "text"])

    frame["linearsvm_field"] = frame.apply(
        lambda row: (
            lookup.get((row["linearsvm_domain"], row["linearsvm_subfield"]))
            if pd.notna(row["linearsvm_domain"]) and pd.notna(row["linearsvm_subfield"])
            else None
        ),
        axis=1,
    )

    return frame.drop(columns=["text"])


def run_hierarchical_prediction(
    *,
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    domain_model_path: Path,
    subfield_model_path: Path,
    taxonomy_path: Path = DEFAULT_TAXONOMY,
    text_columns: Iterable[str] = DEFAULT_TEXT_COLUMNS,
) -> pd.DataFrame:
    """Load trained models, predict the full hierarchy, and save the result."""

    frame = pd.read_csv(input_path)
    domain_model, subfield_models = load_hierarchical_models(
        domain_model_path, subfield_model_path
    )
    lookup = load_taxonomy(taxonomy_path)

    result = predict_hierarchy(
        frame,
        domain_model=domain_model,
        subfield_models=subfield_models,
        lookup=lookup,
        text_columns=text_columns,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


# ============================================================================
# CLI
# ============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train a hierarchical TF-IDF + LinearSVC publication classifier "
            "(domain, then per-domain subfield models) and write model, "
            "metrics, labels, and manifest artifacts."
        )
    )
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT, help="Input publication CSV"
    )
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=DEFAULT_TAXONOMY,
        help="Path to category_hierarchy.json",
    )
    parser.add_argument("--domain-column", default=DEFAULT_DOMAIN_COLUMN)
    parser.add_argument("--subfield-column", default=DEFAULT_SUBFIELD_COLUMN)
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns. Default: title,abstract,topics,keywords,concepts",
    )
    parser.add_argument("--domain-model-output", type=Path, default=None)
    parser.add_argument("--subfield-model-output", type=Path, default=None)
    parser.add_argument("--metrics-output", type=Path, default=None)
    parser.add_argument("--label-counts-output", type=Path, default=None)
    parser.add_argument("--manifest-output", type=Path, default=None)
    parser.add_argument("--test-size", type=float, default=0.15)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--min-subfield-count", type=int, default=2)
    parser.add_argument("--max-features", type=int, default=50_000)
    parser.add_argument("--min-df", type=parse_document_frequency, default=2)
    parser.add_argument("--max-df", type=parse_document_frequency, default=0.95)
    parser.add_argument("--ngram-max", type=int, default=3)
    parser.add_argument("--c-value", type=float, default=1.0)
    parser.add_argument("--class-weight", type=parse_class_weight, default="balanced")
    parser.add_argument("--max-iter", type=int, default=5000)
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
        f"Trained hierarchical Linear SVM classifier on {result.usable_rows:,} rows.",
        f"Domain classes: {result.domain_class_count:,}",
        f"Subfield models: {result.subfield_model_count:,}",
    ]
    if result.domain_accuracy is not None:
        lines.append(f"Domain accuracy: {result.domain_accuracy:.4f}")
        lines.append(f"Domain macro F1: {result.domain_macro_f1:.4f}")
    lines.append(f"Domain model: {result.domain_model_output}")
    if result.domain_model_sha256:
        lines.append(f"Domain model SHA-256: {result.domain_model_sha256}")
    lines.append(f"Subfield model: {result.subfield_model_output}")
    if result.subfield_model_sha256:
        lines.append(f"Subfield model SHA-256: {result.subfield_model_sha256}")
    lines.extend(
        [
            f"Metrics: {result.metrics_output}",
            f"Manifest: {result.manifest_output}",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    config = HierarchicalTrainingConfig(
        input_path=args.input,
        taxonomy_path=args.taxonomy,
        domain_column=args.domain_column,
        subfield_column=args.subfield_column,
        text_columns=tuple(args.text_columns),
        domain_model_output=args.domain_model_output,
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
    result = train_hierarchical_classifier(config)
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
