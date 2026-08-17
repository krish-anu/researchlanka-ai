"""Reusable publication-text embeddings pipeline."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from src.modeling.artifacts import (
    describe_artifact,
    dump_joblib_artifact,
    write_json_artifact,
    write_text_artifact,
)
from src.modeling.inference import DEFAULT_METADATA_COLUMNS, parse_columns
from src.modeling.training import (
    DEFAULT_INPUT,
    DEFAULT_MODEL_DIR,
    DEFAULT_TEXT_COLUMNS,
    combined_text,
    parse_document_frequency,
    parse_text_columns,
)

DEFAULT_MODEL_FAMILY = "publication_tfidf_svd"
DEFAULT_EMBEDDING_DIM = 384
DEFAULT_OUTPUT_PATH = DEFAULT_MODEL_DIR / "publication_text_embeddings.parquet"
DEFAULT_MODEL_OUTPUT_PATH = (
    DEFAULT_MODEL_DIR / "publication_text_embedding_model.joblib"
)
DEFAULT_MANIFEST_OUTPUT_PATH = (
    DEFAULT_MODEL_DIR / "publication_text_embeddings_manifest.json"
)
DEFAULT_SUMMARY_OUTPUT_PATH = (
    DEFAULT_MODEL_DIR / "publication_text_embeddings_summary.txt"
)


@dataclass(frozen=True)
class PublicationEmbeddingConfig:
    """Configuration for one reusable publication embedding run."""

    input_path: Path = DEFAULT_INPUT
    output_path: Path | None = None
    model_output: Path | None = None
    manifest_output: Path | None = None
    summary_output: Path | None = None
    text_columns: tuple[str, ...] = tuple(DEFAULT_TEXT_COLUMNS)
    metadata_columns: tuple[str, ...] = tuple(DEFAULT_METADATA_COLUMNS)
    model_family: str = DEFAULT_MODEL_FAMILY
    embedding_dim: int = DEFAULT_EMBEDDING_DIM
    max_rows: int | None = None
    max_features: int = 50_000
    min_df: int | float = 2
    max_df: int | float = 0.95
    ngram_max: int = 2
    keep_stop_words: bool = False
    normalize_embeddings: bool = True
    random_state: int = 42


@dataclass(frozen=True)
class EmbeddingResult:
    """Paths and summary stats produced by one embedding run."""

    output_path: Path
    model_output: Path
    manifest_output: Path
    summary_output: Path
    input_rows: int
    embedded_rows: int
    skipped_rows: int
    embedding_dimensions: int
    tfidf_features: int
    explained_variance_ratio: float | None
    output_sha256: str
    model_sha256: str


def json_ready_dataclass(
    value: PublicationEmbeddingConfig | EmbeddingResult,
) -> dict[str, object]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def resolved_config(config: PublicationEmbeddingConfig) -> PublicationEmbeddingConfig:
    return PublicationEmbeddingConfig(
        input_path=config.input_path,
        output_path=config.output_path or DEFAULT_OUTPUT_PATH,
        model_output=config.model_output or DEFAULT_MODEL_OUTPUT_PATH,
        manifest_output=config.manifest_output or DEFAULT_MANIFEST_OUTPUT_PATH,
        summary_output=config.summary_output or DEFAULT_SUMMARY_OUTPUT_PATH,
        text_columns=config.text_columns,
        metadata_columns=config.metadata_columns,
        model_family=config.model_family,
        embedding_dim=config.embedding_dim,
        max_rows=config.max_rows,
        max_features=config.max_features,
        min_df=config.min_df,
        max_df=config.max_df,
        ngram_max=config.ngram_max,
        keep_stop_words=config.keep_stop_words,
        normalize_embeddings=config.normalize_embeddings,
        random_state=config.random_state,
    )


def validate_config(config: PublicationEmbeddingConfig) -> None:
    if config.model_family != DEFAULT_MODEL_FAMILY:
        raise ValueError(
            f"Unsupported model_family: {config.model_family}. "
            f"Supported value: {DEFAULT_MODEL_FAMILY}."
        )
    if config.embedding_dim < 1:
        raise ValueError("embedding_dim must be at least 1")
    if config.ngram_max < 1:
        raise ValueError("ngram_max must be at least 1")


def existing_columns(input_path: Path) -> list[str]:
    return list(pd.read_csv(input_path, nrows=0).columns)


def selected_input_columns(
    *,
    input_path: Path,
    text_columns: tuple[str, ...],
    metadata_columns: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    available_columns = existing_columns(input_path)
    missing_text_columns = [
        column for column in text_columns if column not in available_columns
    ]
    if missing_text_columns:
        raise ValueError(
            "Input CSV is missing required text columns: "
            + ", ".join(missing_text_columns)
        )

    present_metadata_columns = [
        column for column in metadata_columns if column in available_columns
    ]
    usecols = list(dict.fromkeys([*text_columns, *present_metadata_columns]))
    return usecols, present_metadata_columns


def load_embedding_frame(
    *,
    input_path: Path,
    text_columns: tuple[str, ...],
    metadata_columns: tuple[str, ...],
    max_rows: int | None,
) -> tuple[pd.DataFrame, int, list[str]]:
    usecols, present_metadata_columns = selected_input_columns(
        input_path=input_path,
        text_columns=text_columns,
        metadata_columns=metadata_columns,
    )
    frame = pd.read_csv(
        input_path,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        nrows=max_rows,
    )
    input_rows = len(frame)
    embedding_frame = frame[present_metadata_columns].copy()
    embedding_frame.insert(0, "source_row", frame.index)
    embedding_frame["text"] = combined_text(frame, text_columns)
    embedding_frame = embedding_frame[embedding_frame["text"] != ""].copy()
    return embedding_frame, input_rows, present_metadata_columns


def build_dense_embeddings(
    *,
    text: pd.Series,
    max_features: int,
    min_df: int | float,
    max_df: int | float,
    ngram_max: int,
    keep_stop_words: bool,
    embedding_dim: int,
    normalize_embeddings: bool,
    random_state: int,
) -> tuple[np.ndarray, TfidfVectorizer, TruncatedSVD, int, float]:
    vectorizer = TfidfVectorizer(
        stop_words=None if keep_stop_words else "english",
        strip_accents="unicode",
        lowercase=True,
        ngram_range=(1, ngram_max),
        min_df=min_df,
        max_df=max_df,
        max_features=None if max_features <= 0 else max_features,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(text)
    tfidf_features = int(tfidf_matrix.shape[1])
    if tfidf_features < 2:
        raise ValueError(
            "Not enough TF-IDF features to build dense embeddings. "
            "Try lowering --min-df or increasing --max-features."
        )

    target_dim = min(embedding_dim, tfidf_features - 1)
    if target_dim < 1:
        raise ValueError(
            "Unable to derive a positive embedding dimension from TF-IDF features"
        )

    svd = TruncatedSVD(n_components=target_dim, random_state=random_state)
    dense = svd.fit_transform(tfidf_matrix)
    explained_variance = float(svd.explained_variance_ratio_.sum())

    if normalize_embeddings:
        dense = normalize(dense, norm="l2")

    return dense.astype(np.float32), vectorizer, svd, tfidf_features, explained_variance


def embedding_column_names(dimensions: int) -> list[str]:
    return [f"embedding_{index:04d}" for index in range(dimensions)]


def write_embeddings_parquet(
    *,
    output_path: Path,
    embedding_frame: pd.DataFrame,
    embeddings: np.ndarray,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = embedding_column_names(embeddings.shape[1])
    embedding_values = pd.DataFrame(
        embeddings, columns=columns, index=embedding_frame.index
    )
    output_frame = pd.concat(
        [
            embedding_frame.drop(columns=["text"]).reset_index(drop=True),
            embedding_values.reset_index(drop=True),
        ],
        axis=1,
    )
    output_frame.to_parquet(output_path, index=False)


def render_summary(
    *, config: PublicationEmbeddingConfig, result: EmbeddingResult
) -> str:
    lines = [
        "Publication text embeddings",
        "",
        f"model_family: {config.model_family}",
        f"input_csv: {config.input_path}",
        f"output_parquet: {result.output_path}",
        f"model_output: {result.model_output}",
        f"manifest_output: {result.manifest_output}",
        f"text_columns: {', '.join(config.text_columns)}",
        f"metadata_columns: {', '.join(config.metadata_columns)}",
        f"input_rows: {result.input_rows}",
        f"embedded_rows: {result.embedded_rows}",
        f"skipped_rows: {result.skipped_rows}",
        f"embedding_dimensions: {result.embedding_dimensions}",
        f"tfidf_features: {result.tfidf_features}",
        f"normalize_embeddings: {config.normalize_embeddings}",
    ]
    if result.explained_variance_ratio is not None:
        lines.append(f"explained_variance_ratio: {result.explained_variance_ratio:.6f}")
    lines.extend(
        [
            f"output_sha256: {result.output_sha256}",
            f"model_sha256: {result.model_sha256}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def generate_publication_text_embeddings(
    config: PublicationEmbeddingConfig,
) -> EmbeddingResult:
    """Generate dense publication-text embeddings and save reproducible artifacts."""

    config = resolved_config(config)
    validate_config(config)

    embedding_frame, input_rows, _present_metadata_columns = load_embedding_frame(
        input_path=config.input_path,
        text_columns=config.text_columns,
        metadata_columns=config.metadata_columns,
        max_rows=config.max_rows,
    )
    if embedding_frame.empty:
        raise ValueError("No usable rows found after combining text columns")

    embeddings, vectorizer, svd, tfidf_features, explained_variance_ratio = (
        build_dense_embeddings(
            text=embedding_frame["text"],
            max_features=config.max_features,
            min_df=config.min_df,
            max_df=config.max_df,
            ngram_max=config.ngram_max,
            keep_stop_words=config.keep_stop_words,
            embedding_dim=config.embedding_dim,
            normalize_embeddings=config.normalize_embeddings,
            random_state=config.random_state,
        )
    )

    assert config.output_path is not None
    assert config.model_output is not None
    assert config.manifest_output is not None
    assert config.summary_output is not None

    write_embeddings_parquet(
        output_path=config.output_path,
        embedding_frame=embedding_frame,
        embeddings=embeddings,
    )
    saved_output = describe_artifact(config.output_path)

    embedder = {
        "model_family": config.model_family,
        "text_columns": list(config.text_columns),
        "vectorizer": vectorizer,
        "svd": svd,
        "normalize_embeddings": config.normalize_embeddings,
    }
    saved_model = dump_joblib_artifact(config.model_output, embedder)

    result = EmbeddingResult(
        output_path=config.output_path,
        model_output=config.model_output,
        manifest_output=config.manifest_output,
        summary_output=config.summary_output,
        input_rows=input_rows,
        embedded_rows=int(embeddings.shape[0]),
        skipped_rows=input_rows - int(embeddings.shape[0]),
        embedding_dimensions=int(embeddings.shape[1]),
        tfidf_features=tfidf_features,
        explained_variance_ratio=explained_variance_ratio,
        output_sha256=saved_output.sha256,
        model_sha256=saved_model.sha256,
    )

    summary_text = render_summary(config=config, result=result)
    write_text_artifact(config.summary_output, summary_text)

    write_json_artifact(
        config.manifest_output,
        {
            "config": json_ready_dataclass(config),
            "result": json_ready_dataclass(result),
            "artifacts": {
                "embeddings": saved_output.as_manifest_dict(),
                "model": saved_model.as_manifest_dict(),
                "summary": str(config.summary_output),
                "manifest": str(config.manifest_output),
            },
        },
    )
    return result


def result_summary(result: EmbeddingResult) -> str:
    return (
        "Generated publication text embeddings: "
        f"rows={result.embedded_rows}, dim={result.embedding_dimensions}, "
        f"output={result.output_path}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate dense publication-text embeddings from selected CSV text columns "
            "and write parquet, model, summary, and manifest artifacts."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input publication CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output parquet path with metadata and embedding vectors. "
            "Default: data/models/publication_text_embeddings.parquet"
        ),
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=None,
        help="Output .joblib embedding model path. Default: data/models/publication_text_embedding_model.joblib",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=None,
        help="Output JSON manifest path. Default: data/models/publication_text_embeddings_manifest.json",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Output text summary path. Default: data/models/publication_text_embeddings_summary.txt",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns to combine. Default: title,abstract,keywords",
    )
    parser.add_argument(
        "--metadata-columns",
        type=parse_columns,
        default=DEFAULT_METADATA_COLUMNS,
        help=(
            "Comma-separated metadata columns to include in the parquet output. "
            "Missing metadata columns are skipped."
        ),
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=DEFAULT_EMBEDDING_DIM,
        help="Target dense embedding dimension. Default: 384",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=50_000,
        help="Maximum TF-IDF vocabulary size. Default: 50000",
    )
    parser.add_argument(
        "--min-df",
        type=parse_document_frequency,
        default=2,
        help="TF-IDF min_df as count or fraction. Default: 2",
    )
    parser.add_argument(
        "--max-df",
        type=parse_document_frequency,
        default=0.95,
        help="TF-IDF max_df as count or fraction. Default: 0.95",
    )
    parser.add_argument(
        "--ngram-max",
        type=int,
        default=2,
        help="Upper bound for word n-grams. Default: 2",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional cap on rows read from input CSV.",
    )
    parser.add_argument(
        "--keep-stop-words",
        action="store_true",
        help="Keep stop words instead of removing English stop words.",
    )
    parser.add_argument(
        "--disable-normalize",
        action="store_true",
        help="Disable L2 normalization on output embeddings.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed used by SVD. Default: 42",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_publication_text_embeddings(
        PublicationEmbeddingConfig(
            input_path=args.input,
            output_path=args.output,
            model_output=args.model_output,
            manifest_output=args.manifest_output,
            summary_output=args.summary_output,
            text_columns=tuple(args.text_columns),
            metadata_columns=tuple(args.metadata_columns),
            embedding_dim=args.embedding_dim,
            max_rows=args.max_rows,
            max_features=args.max_features,
            min_df=args.min_df,
            max_df=args.max_df,
            ngram_max=args.ngram_max,
            keep_stop_words=args.keep_stop_words,
            normalize_embeddings=not args.disable_normalize,
            random_state=args.random_state,
        )
    )
    print(result_summary(result))


if __name__ == "__main__":
    main()
