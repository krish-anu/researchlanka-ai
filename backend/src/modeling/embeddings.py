"""Reusable publication-text embeddings pipeline."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
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
EMBEDDINGS_PATH_ENV = "RESEARCHLANKA_SEMANTIC_EMBEDDINGS_PATH"
EMBEDDING_MODEL_PATH_ENV = "RESEARCHLANKA_SEMANTIC_MODEL_PATH"
EMBEDDING_COLUMN_PREFIX = "embedding_"
SEMANTIC_SCORE_FIELD = "semantic_score"
SEMANTIC_RANK_FIELD = "semantic_rank"

SEMANTIC_TEXT_FILTER_COLUMNS = {
    "type": "type",
    "journal": "journal",
    "field": "primary_field",
    "subfield": "primary_subfield",
}

SEMANTIC_MULTIVALUE_FILTER_COLUMNS = {
    "institution": (
        "institutions",
        "sri_lankan_institutions",
        "source_institution_id",
    ),
    "country": ("countries",),
    "topic": ("topics", "concepts", "primary_topic"),
    "source_dataset": ("source_dataset",),
}

SEMANTIC_LOOKUP_COLUMNS = (
    "publication_key",
    "doi",
    "openalex_id",
    "source_record_id",
    "record_number",
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


class SemanticSearchIndex:
    """In-memory semantic search over saved publication embedding artifacts."""

    def __init__(
        self,
        *,
        metadata: pd.DataFrame,
        embeddings: np.ndarray,
        embedder: Mapping[str, Any],
        embedding_columns: Sequence[str],
    ) -> None:
        if embeddings.ndim != 2:
            raise ValueError("embeddings must be a 2D matrix")
        if len(metadata) != embeddings.shape[0]:
            raise ValueError(
                "metadata row count must match embedding row count: "
                f"{len(metadata)} != {embeddings.shape[0]}"
            )
        if embeddings.shape[1] == 0:
            raise ValueError("embeddings must include at least one dimension")

        self.metadata = metadata.reset_index(drop=True).copy()
        self.embeddings = l2_normalized_matrix(embeddings)
        self.embedder = dict(embedder)
        self.embedding_columns = tuple(embedding_columns)

    @classmethod
    def from_artifacts(
        cls,
        *,
        embeddings_path: Path = DEFAULT_OUTPUT_PATH,
        model_path: Path = DEFAULT_MODEL_OUTPUT_PATH,
    ) -> "SemanticSearchIndex":
        return load_semantic_search_index(
            embeddings_path=embeddings_path,
            model_path=model_path,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        min_score: float | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return nearest publication rows for a natural-language query."""

        query_vector = encode_semantic_query(query, self.embedder)
        if is_zero_vector(query_vector):
            return []
        return self.search_by_vector(
            query_vector,
            limit=limit,
            min_score=min_score,
            filters=filters,
        )

    def related_publications(
        self,
        publication_key: str,
        *,
        limit: int = 10,
        min_score: float | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return nearest rows to an existing publication embedding."""

        row_index = find_publication_index(self.metadata, publication_key)
        return self.search_by_vector(
            self.embeddings[row_index],
            limit=limit,
            min_score=min_score,
            filters=filters,
            exclude_indices={row_index},
        )

    def search_by_vector(
        self,
        vector: np.ndarray,
        *,
        limit: int = 10,
        min_score: float | None = None,
        filters: Mapping[str, Any] | None = None,
        exclude_indices: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Return nearest rows to a dense vector using cosine similarity."""

        validate_search_limit(limit)
        query_vector = l2_normalized_vector(vector)
        if is_zero_vector(query_vector):
            return []
        if query_vector.shape[0] != self.embeddings.shape[1]:
            raise ValueError(
                "Query embedding dimension does not match index dimension: "
                f"{query_vector.shape[0]} != {self.embeddings.shape[1]}"
            )

        candidate_mask = semantic_filter_mask(self.metadata, filters or {})
        if exclude_indices:
            for index in exclude_indices:
                if 0 <= index < len(candidate_mask):
                    candidate_mask[index] = False

        candidate_indices = np.flatnonzero(candidate_mask)
        if len(candidate_indices) == 0:
            return []

        scores = self.embeddings[candidate_indices] @ query_vector
        if min_score is not None:
            score_mask = scores >= min_score
            candidate_indices = candidate_indices[score_mask]
            scores = scores[score_mask]

        if len(candidate_indices) == 0:
            return []

        order = np.argsort(scores)[::-1][:limit]
        return semantic_search_rows(
            self.metadata,
            indices=candidate_indices[order],
            scores=scores[order],
        )


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


def default_semantic_embeddings_path() -> Path:
    """Return the preferred available embeddings artifact for semantic search."""

    if DEFAULT_OUTPUT_PATH.exists():
        return DEFAULT_OUTPUT_PATH
    candidates = [
        path
        for path in DEFAULT_MODEL_DIR.glob("publication_text_embeddings*.parquet")
        if path.is_file()
    ]
    if not candidates:
        return DEFAULT_OUTPUT_PATH
    return max(candidates, key=lambda path: path.stat().st_size)


def default_semantic_model_path(embeddings_path: Path | None = None) -> Path:
    """Return the model artifact that best matches an embeddings parquet."""

    if embeddings_path and embeddings_path != DEFAULT_OUTPUT_PATH:
        suffix = embeddings_path.stem.removeprefix("publication_text_embeddings")
        candidate = DEFAULT_MODEL_DIR / f"publication_text_embedding_model{suffix}.joblib"
        if candidate.exists():
            return candidate
    if DEFAULT_MODEL_OUTPUT_PATH.exists():
        return DEFAULT_MODEL_OUTPUT_PATH
    candidates = [
        path
        for path in DEFAULT_MODEL_DIR.glob("publication_text_embedding_model*.joblib")
        if path.is_file()
    ]
    if not candidates:
        return DEFAULT_MODEL_OUTPUT_PATH
    return max(candidates, key=lambda path: path.stat().st_size)


def embedding_columns_from_frame(frame: pd.DataFrame) -> list[str]:
    columns = [
        column
        for column in frame.columns
        if column.startswith(EMBEDDING_COLUMN_PREFIX)
    ]
    if not columns:
        raise ValueError(
            "Embedding parquet does not contain columns named "
            f"{EMBEDDING_COLUMN_PREFIX}####"
        )
    return sorted(columns)


def validate_embedding_model(embedder: Mapping[str, Any]) -> None:
    missing_keys = [
        key
        for key in ("vectorizer", "svd")
        if key not in embedder or embedder[key] is None
    ]
    if missing_keys:
        raise ValueError(
            "Embedding model is missing required components: "
            + ", ".join(missing_keys)
        )
    model_family = embedder.get("model_family")
    if model_family not in {None, DEFAULT_MODEL_FAMILY}:
        raise ValueError(f"Unsupported embedding model_family: {model_family}")


def load_semantic_search_index(
    *,
    embeddings_path: Path = DEFAULT_OUTPUT_PATH,
    model_path: Path = DEFAULT_MODEL_OUTPUT_PATH,
) -> SemanticSearchIndex:
    """Load a reusable in-memory semantic-search index from saved artifacts."""

    if not embeddings_path.exists():
        raise FileNotFoundError(f"Embeddings artifact not found: {embeddings_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Embedding model artifact not found: {model_path}")

    frame = pd.read_parquet(embeddings_path)
    embedding_columns = embedding_columns_from_frame(frame)
    embeddings = frame[embedding_columns].to_numpy(dtype=np.float32, copy=True)
    embeddings = np.nan_to_num(embeddings, nan=0.0, posinf=0.0, neginf=0.0)
    metadata = frame.drop(columns=embedding_columns)
    embedder = joblib.load(model_path)
    if not isinstance(embedder, Mapping):
        raise ValueError("Embedding model artifact must contain a mapping")
    validate_embedding_model(embedder)
    return SemanticSearchIndex(
        metadata=metadata,
        embeddings=embeddings,
        embedder=embedder,
        embedding_columns=embedding_columns,
    )


def encode_semantic_query(query: str, embedder: Mapping[str, Any]) -> np.ndarray:
    """Transform query text with the saved TF-IDF + SVD embedding model."""

    text = query.strip()
    if not text:
        raise ValueError("Semantic search query must not be blank")

    validate_embedding_model(embedder)
    tfidf_matrix = embedder["vectorizer"].transform([text])
    dense = embedder["svd"].transform(tfidf_matrix)
    return np.asarray(dense[0], dtype=np.float32)


def l2_normalized_matrix(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return values
    return normalize(values, norm="l2").astype(np.float32)


def l2_normalized_vector(value: np.ndarray) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float32).reshape(1, -1)
    if is_zero_vector(vector):
        return vector.ravel()
    return normalize(vector, norm="l2").astype(np.float32).ravel()


def is_zero_vector(value: np.ndarray) -> bool:
    return not bool(np.any(np.asarray(value, dtype=np.float32)))


def validate_search_limit(limit: int) -> None:
    if limit < 1:
        raise ValueError("limit must be at least 1")


def semantic_filter_mask(
    metadata: pd.DataFrame,
    filters: Mapping[str, Any],
) -> np.ndarray:
    """Build a best-effort boolean mask for filters present in embedding metadata."""

    mask = np.ones(len(metadata), dtype=bool)
    if not filters:
        return mask

    if filters.get("year_min") is not None and "publication_year" in metadata.columns:
        years = pd.to_numeric(metadata["publication_year"], errors="coerce")
        mask &= (years >= filters["year_min"]).fillna(False).to_numpy()
    if filters.get("year_max") is not None and "publication_year" in metadata.columns:
        years = pd.to_numeric(metadata["publication_year"], errors="coerce")
        mask &= (years <= filters["year_max"]).fillna(False).to_numpy()

    for filter_name, column in SEMANTIC_TEXT_FILTER_COLUMNS.items():
        values = filters.get(filter_name)
        if values and column in metadata.columns:
            mask &= text_membership_mask(metadata[column], values)

    for filter_name, columns in SEMANTIC_MULTIVALUE_FILTER_COLUMNS.items():
        values = filters.get(filter_name)
        present_columns = [column for column in columns if column in metadata.columns]
        if values and present_columns:
            mask &= multivalue_contains_mask(metadata, present_columns, values)

    if filters.get("is_oa") is not None and "is_oa" in metadata.columns:
        mask &= boolean_mask(metadata["is_oa"], bool(filters["is_oa"]))
    if filters.get("has_doi") is not None and "doi" in metadata.columns:
        doi_present = nonblank_mask(metadata["doi"])
        mask &= doi_present if filters["has_doi"] else ~doi_present
    if filters.get("has_abstract") is not None and "abstract" in metadata.columns:
        abstract_present = nonblank_mask(metadata["abstract"])
        mask &= abstract_present if filters["has_abstract"] else ~abstract_present

    return mask


def text_membership_mask(series: pd.Series, values: Sequence[Any]) -> np.ndarray:
    wanted = {str(value).casefold() for value in values if value not in (None, "")}
    if not wanted:
        return np.ones(len(series), dtype=bool)
    return series.fillna("").astype(str).str.casefold().isin(wanted).to_numpy()


def multivalue_contains_mask(
    frame: pd.DataFrame,
    columns: Sequence[str],
    values: Sequence[Any],
) -> np.ndarray:
    wanted = [str(value).casefold() for value in values if value not in (None, "")]
    if not wanted:
        return np.ones(len(frame), dtype=bool)

    mask = np.zeros(len(frame), dtype=bool)
    for column in columns:
        text = frame[column].fillna("").astype(str).str.casefold()
        column_mask = np.zeros(len(frame), dtype=bool)
        for value in wanted:
            column_mask |= text.str.contains(value, regex=False).to_numpy()
        mask |= column_mask
    return mask


def boolean_mask(series: pd.Series, expected: bool) -> np.ndarray:
    truthy = {"true", "t", "yes", "y", "1"}
    falsy = {"false", "f", "no", "n", "0"}
    normalized = series.fillna("").astype(str).str.casefold()
    values = normalized.isin(truthy) if expected else normalized.isin(falsy)
    if series.dtype == bool:
        values = series.fillna(False).astype(bool) == expected
    return values.to_numpy()


def nonblank_mask(series: pd.Series) -> np.ndarray:
    return (
        series.notna()
        & (series.astype(str).str.strip() != "")
        & (series.astype(str).str.casefold() != "nan")
    ).to_numpy()


def semantic_search_rows(
    metadata: pd.DataFrame,
    *,
    indices: Sequence[int],
    scores: Sequence[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, (index, score) in enumerate(zip(indices, scores, strict=True), start=1):
        row = clean_metadata_row(metadata.iloc[int(index)].to_dict())
        row[SEMANTIC_SCORE_FIELD] = round(float(score), 6)
        row[SEMANTIC_RANK_FIELD] = rank
        rows.append(row)
    return rows


def clean_metadata_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: clean_metadata_value(value) for key, value in row.items()}


def clean_metadata_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def find_publication_index(metadata: pd.DataFrame, publication_key: str) -> int:
    """Find one embedding row by publication_key or common source identifiers."""

    candidates = publication_lookup_candidates(publication_key)
    for column in SEMANTIC_LOOKUP_COLUMNS:
        if column not in metadata.columns:
            continue
        values = metadata[column].fillna("").astype(str).str.casefold()
        matches = values[values.isin(candidates)]
        if not matches.empty:
            return int(matches.index[0])
    raise KeyError(f"Publication embedding not found: {publication_key}")


def publication_lookup_candidates(publication_key: str) -> set[str]:
    text = publication_key.strip()
    candidates = {text.casefold()}
    for prefix in ("doi:", "openalex:", "source:"):
        if text.casefold().startswith(prefix):
            candidates.add(text[len(prefix) :].casefold())
    if ":" in text:
        candidates.add(text.rsplit(":", maxsplit=1)[-1].casefold())
    return {candidate for candidate in candidates if candidate}


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
