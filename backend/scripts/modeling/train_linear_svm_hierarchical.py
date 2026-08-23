"""Hierarchical LinearSVM classifier for publication text classification.

Pipeline:

    Domain model (primary_field)
            |
    Domain-specific subfield models (primary_subfield)
            |
    Field lookup (domain, subfield) -> field, via category_hierarchy.json

Generates the columns: linearsvm_domain, linearsvm_field, linearsvm_subfield

Run via: scripts/modeling/train_linear_svm_hierarchical.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_linearsvm.csv"
)
DEFAULT_TAXONOMY = PROJECT_ROOT / "data" / "taxonomy" / "category_hierarchy.json"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models" / "linear_svm"

DEFAULT_DOMAIN_MODEL = DEFAULT_MODEL_DIR / "linear_svm_domain.joblib"
DEFAULT_SUBFIELD_MODEL = DEFAULT_MODEL_DIR / "linear_svm_subfield_models.joblib"

TEXT_COLUMNS = ["title", "abstract", "topics", "keywords", "concepts"]
RANDOM_STATE = 42


# ============================================================================
# TAXONOMY LOOKUP
# ============================================================================


def build_lookup(taxonomy: dict) -> Dict[Tuple[str, str], str]:
    """Convert {domain: {field: [subfields]}} into {(domain, subfield): field}."""
    lookup: Dict[Tuple[str, str], str] = {}
    for domain, fields in taxonomy.items():
        for field, subfields in fields.items():
            for subfield in subfields:
                lookup[(domain, subfield)] = field
    return lookup


def load_taxonomy(path: Path = DEFAULT_TAXONOMY) -> Dict[Tuple[str, str], str]:
    with open(path, "r", encoding="utf-8") as f:
        taxonomy = json.load(f)
    return build_lookup(taxonomy)


# ============================================================================
# TEXT PREPARATION
# ============================================================================


def build_text(df: pd.DataFrame) -> pd.Series:
    return (
        df[TEXT_COLUMNS]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


# ============================================================================
# PIPELINE CONSTRUCTION
# ============================================================================


def build_svm_pipeline(
    *,
    ngram_max: int = 3,
    C: float = 1.0,
    class_weight: str | None = "balanced",
    max_features: int = 50_000,
    min_df: int | float = 2,
    max_df: int | float = 0.95,
    max_iter: int = 5000,
    random_state: int = RANDOM_STATE,
) -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    stop_words=None,
                    ngram_range=(1, ngram_max),
                    min_df=min_df,
                    max_df=max_df,
                    max_features=(None if max_features <= 0 else max_features),
                    sublinear_tf=True,
                ),
            ),
            (
                "svm",
                LinearSVC(
                    C=C,
                    class_weight=class_weight,
                    max_iter=max_iter,
                    random_state=random_state,
                    dual="auto",
                ),
            ),
        ]
    )


def _fit_and_score(
    df: pd.DataFrame,
    label_column: str,
    *,
    pipeline_kwargs: dict,
    test_size: float,
    random_state: int,
) -> tuple[Pipeline, float, float]:
    """Fit on a train split for evaluation, then return (model refit on all
    rows, accuracy, macro_f1) evaluated on the held-out split."""
    can_stratify = (
        df[label_column].value_counts().min() >= 2 and df[label_column].nunique() >= 2
    )

    if can_stratify:
        train_df, test_df = train_test_split(
            df,
            test_size=test_size,
            random_state=random_state,
            stratify=df[label_column],
        )
        eval_model = build_svm_pipeline(**pipeline_kwargs)
        eval_model.fit(train_df["text"], train_df[label_column])
        predictions = eval_model.predict(test_df["text"])
        accuracy = accuracy_score(test_df[label_column], predictions)
        macro_f1 = f1_score(
            test_df[label_column], predictions, average="macro", zero_division=0
        )
    else:
        accuracy = float("nan")
        macro_f1 = float("nan")

    final_model = build_svm_pipeline(**pipeline_kwargs)
    final_model.fit(df["text"], df[label_column])
    return final_model, accuracy, macro_f1


# ============================================================================
# TRAINING RESULT
# ============================================================================


@dataclass(frozen=True)
class HierarchicalTrainingResult:
    domain_model_path: Path
    subfield_model_path: Path
    domain_classes: int
    subfield_models: int
    domain_accuracy: float
    domain_macro_f1: float


# ============================================================================
# TRAINING
# ============================================================================


def train_hierarchical_pipeline(
    input_csv: Path = DEFAULT_INPUT,
    domain_output: Path = DEFAULT_DOMAIN_MODEL,
    subfield_output: Path = DEFAULT_SUBFIELD_MODEL,
    *,
    ngram_max: int = 3,
    C: float = 1.0,
    class_weight: str | None = "balanced",
    max_features: int = 50_000,
    min_df: int | float = 2,
    max_df: int | float = 0.95,
    max_iter: int = 5000,
    min_subfield_count: int = 2,
    test_size: float = 0.15,
    random_state: int = RANDOM_STATE,
) -> HierarchicalTrainingResult:
    """Train a domain classifier and one subfield classifier per domain."""

    print("Loading dataset...")
    df = pd.read_csv(input_csv)
    print("Dataset:", df.shape)

    pipeline_kwargs = dict(
        ngram_max=ngram_max,
        C=C,
        class_weight=class_weight,
        max_features=max_features,
        min_df=min_df,
        max_df=max_df,
        max_iter=max_iter,
        random_state=random_state,
    )

    labeled = df[df["primary_field"].notna() & df["primary_subfield"].notna()].copy()
    labeled["text"] = build_text(labeled)
    print("Training rows:", len(labeled))

    print("\nTraining domain model...")
    domain_model, domain_accuracy, domain_macro_f1 = _fit_and_score(
        labeled,
        "primary_field",
        pipeline_kwargs=pipeline_kwargs,
        test_size=test_size,
        random_state=random_state,
    )

    print("\nTraining subfield models...")
    subfield_models: dict[str, Pipeline] = {}
    for domain in sorted(labeled["primary_field"].unique()):
        domain_df = labeled[labeled["primary_field"] == domain]
        if domain_df["primary_subfield"].nunique() < min_subfield_count:
            continue
        print("  Training:", domain)
        model, _, _ = _fit_and_score(
            domain_df,
            "primary_subfield",
            pipeline_kwargs=pipeline_kwargs,
            test_size=test_size,
            random_state=random_state,
        )
        subfield_models[domain] = model

    domain_output.parent.mkdir(parents=True, exist_ok=True)
    subfield_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(domain_model, domain_output)
    joblib.dump(subfield_models, subfield_output)

    return HierarchicalTrainingResult(
        domain_model_path=domain_output,
        subfield_model_path=subfield_output,
        domain_classes=labeled["primary_field"].nunique(),
        subfield_models=len(subfield_models),
        domain_accuracy=domain_accuracy,
        domain_macro_f1=domain_macro_f1,
    )


# ============================================================================
# PREDICTION
# ============================================================================


def load_hierarchical_models(
    domain_model_path: Path, subfield_model_path: Path
) -> tuple[Pipeline, dict[str, Pipeline]]:
    domain_model = joblib.load(domain_model_path)
    subfield_models = joblib.load(subfield_model_path)
    return domain_model, subfield_models


def predict_hierarchy(
    df: pd.DataFrame,
    domain_model: Pipeline,
    subfield_models: dict[str, Pipeline],
    lookup: Dict[Tuple[str, str], str],
) -> pd.DataFrame:
    """Predict domain, subfield and looked-up field for every row with text."""
    df = df.copy()
    df["text"] = build_text(df)
    has_text = df["text"].str.len() > 0

    df["linearsvm_domain"] = None
    df.loc[has_text, "linearsvm_domain"] = domain_model.predict(
        df.loc[has_text, "text"]
    )

    df["linearsvm_subfield"] = None
    for domain, model in subfield_models.items():
        mask = (df["linearsvm_domain"] == domain) & has_text
        if mask.sum() == 0:
            continue
        df.loc[mask, "linearsvm_subfield"] = model.predict(df.loc[mask, "text"])

    df["linearsvm_field"] = df.apply(
        lambda row: (
            lookup.get((row["linearsvm_domain"], row["linearsvm_subfield"]))
            if pd.notna(row["linearsvm_domain"]) and pd.notna(row["linearsvm_subfield"])
            else None
        ),
        axis=1,
    )

    return df.drop(columns=["text"])


def run_hierarchical_prediction(
    input_csv: Path,
    domain_model_path: Path,
    subfield_model_path: Path,
    taxonomy_lookup: Dict[Tuple[str, str], str],
    output_csv: Path,
) -> pd.DataFrame:
    """Load models, predict the full hierarchy for a dataset, and save the result."""
    print("\nLoading dataset for prediction...")
    df = pd.read_csv(input_csv)

    domain_model, subfield_models = load_hierarchical_models(
        domain_model_path, subfield_model_path
    )

    result = predict_hierarchy(df, domain_model, subfield_models, taxonomy_lookup)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False)

    print("Saved:", output_csv)
    print(
        result[["linearsvm_domain", "linearsvm_field", "linearsvm_subfield"]]
        .notna()
        .sum()
    )
    return result
