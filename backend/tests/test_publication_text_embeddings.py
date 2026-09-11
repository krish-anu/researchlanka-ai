"""Tests for publication text embedding generation."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from research_analytics.cli import main as cli_main

from src.modeling.embeddings import (
    PublicationEmbeddingConfig,
    embedding_column_names,
    generate_publication_text_embeddings,
    load_semantic_search_index,
)


def write_publications_csv(path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "record_number": "1",
                "publication_year": "2024",
                "title": "Machine learning for tea disease detection",
                "abstract": "Tea disease detection with computer vision and machine learning.",
                "keywords": "ai; tea",
                "doi": "10.1000/tea",
                "openalex_id": "https://openalex.org/W1",
                "source_dataset": "openalex",
                "source_institution_id": "uoc",
                "source_record_id": "record-1",
            },
            {
                "record_number": "2",
                "publication_year": "2025",
                "title": "Rice disease forecasting in Sri Lanka",
                "abstract": "Forecasting rice disease using remote sensing signals.",
                "keywords": "ai; rice",
                "doi": "10.1000/rice",
                "openalex_id": "https://openalex.org/W2",
                "source_dataset": "crossref",
                "source_institution_id": "uom",
                "source_record_id": "record-2",
            },
            {
                "record_number": "3",
                "publication_year": "2026",
                "title": "",
                "abstract": "",
                "keywords": "",
                "doi": "",
                "openalex_id": "",
                "source_dataset": "manual",
                "source_institution_id": "",
                "source_record_id": "record-3",
            },
        ]
    )
    frame.to_csv(path, index=False)


def test_generate_publication_text_embeddings_writes_expected_artifacts(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    output_parquet = tmp_path / "embeddings.parquet"
    model_output = tmp_path / "embedding_model.joblib"
    manifest_output = tmp_path / "embeddings_manifest.json"
    summary_output = tmp_path / "embeddings_summary.txt"
    write_publications_csv(input_csv)

    result = generate_publication_text_embeddings(
        PublicationEmbeddingConfig(
            input_path=input_csv,
            output_path=output_parquet,
            model_output=model_output,
            manifest_output=manifest_output,
            summary_output=summary_output,
            text_columns=("title", "abstract", "keywords"),
            metadata_columns=("record_number", "publication_year", "doi"),
            embedding_dim=4,
            max_features=100,
            min_df=1,
            max_df=1.0,
            ngram_max=2,
        )
    )

    assert output_parquet.exists()
    assert model_output.exists()
    assert manifest_output.exists()
    assert summary_output.exists()

    frame = pd.read_parquet(output_parquet)
    assert len(frame) == 2
    assert "source_row" in frame.columns
    assert "record_number" in frame.columns
    embedding_columns = [
        column for column in frame.columns if column.startswith("embedding_")
    ]
    assert len(embedding_columns) == result.embedding_dimensions
    assert result.embedding_dimensions <= 4
    assert result.embedded_rows == 2
    assert result.skipped_rows == 1

    manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    assert manifest["result"]["embedded_rows"] == 2
    assert manifest["artifacts"]["embeddings"]["sha256"] == result.output_sha256


def test_generate_embeddings_cli_command(tmp_path: Path, capsys):
    input_csv = tmp_path / "publications.csv"
    output_parquet = tmp_path / "embeddings_cli.parquet"
    write_publications_csv(input_csv)

    cli_main(
        [
            "generate_embeddings",
            "--input",
            str(input_csv),
            "--output",
            str(output_parquet),
            "--embedding-dim",
            "4",
            "--min-df",
            "1",
            "--max-df",
            "1.0",
        ]
    )

    captured = capsys.readouterr()
    assert "Generated publication text embeddings" in captured.out
    assert output_parquet.exists()


def test_embedding_storage_persists_reloadable_vectors_and_model(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    output_parquet = tmp_path / "embeddings.parquet"
    model_output = tmp_path / "embedding_model.joblib"
    manifest_output = tmp_path / "embeddings_manifest.json"
    summary_output = tmp_path / "embeddings_summary.txt"
    write_publications_csv(input_csv)

    result = generate_publication_text_embeddings(
        PublicationEmbeddingConfig(
            input_path=input_csv,
            output_path=output_parquet,
            model_output=model_output,
            manifest_output=manifest_output,
            summary_output=summary_output,
            text_columns=("title", "abstract", "keywords"),
            metadata_columns=(
                "record_number",
                "publication_year",
                "title",
                "doi",
                "openalex_id",
                "source_dataset",
                "source_institution_id",
                "source_record_id",
            ),
            embedding_dim=4,
            max_features=100,
            min_df=1,
            max_df=1.0,
            ngram_max=2,
        )
    )

    stored = pd.read_parquet(output_parquet)
    embedding_columns = [
        column for column in stored.columns if column.startswith("embedding_")
    ]

    assert "text" not in stored.columns
    assert stored["source_row"].tolist() == [0, 1]
    assert stored["record_number"].tolist() == ["1", "2"]
    assert stored["source_record_id"].tolist() == ["record-1", "record-2"]
    assert embedding_columns == embedding_column_names(result.embedding_dimensions)
    assert stored[embedding_columns].isna().sum().sum() == 0

    stored_vectors = stored[embedding_columns].to_numpy(dtype=np.float32)
    assert stored_vectors.shape == (2, result.embedding_dimensions)
    assert np.allclose(np.linalg.norm(stored_vectors, axis=1), 1.0)

    saved_model = joblib.load(model_output)
    assert saved_model["model_family"] == "publication_tfidf_svd"
    assert saved_model["text_columns"] == ["title", "abstract", "keywords"]
    assert saved_model["normalize_embeddings"] is True
    assert hasattr(saved_model["vectorizer"], "transform")
    assert hasattr(saved_model["svd"], "transform")

    reloaded = load_semantic_search_index(
        embeddings_path=output_parquet,
        model_path=model_output,
    )

    assert reloaded.embedding_columns == tuple(embedding_columns)
    assert reloaded.metadata["doi"].tolist() == ["10.1000/tea", "10.1000/rice"]
    assert np.allclose(reloaded.embeddings, stored_vectors)


def test_semantic_search_index_ranks_filters_and_finds_related(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    output_parquet = tmp_path / "embeddings.parquet"
    model_output = tmp_path / "embedding_model.joblib"
    write_publications_csv(input_csv)

    generate_publication_text_embeddings(
        PublicationEmbeddingConfig(
            input_path=input_csv,
            output_path=output_parquet,
            model_output=model_output,
            text_columns=("title", "abstract", "keywords"),
            metadata_columns=(
                "record_number",
                "publication_year",
                "title",
                "doi",
                "openalex_id",
                "source_dataset",
                "source_record_id",
            ),
            embedding_dim=4,
            max_features=100,
            min_df=1,
            max_df=1.0,
            ngram_max=2,
        )
    )
    index = load_semantic_search_index(
        embeddings_path=output_parquet,
        model_path=model_output,
    )

    rows = index.search("computer vision tea disease", limit=2)

    assert rows[0]["title"] == "Machine learning for tea disease detection"
    assert rows[0]["semantic_rank"] == 1
    assert rows[0]["similarity_rank"] == 1
    assert rows[0]["semantic_score"] >= rows[1]["semantic_score"]
    assert rows[0]["similarity_score"] == rows[0]["semantic_score"]

    filtered = index.search(
        "disease forecasting",
        limit=5,
        filters={"year_min": 2025},
    )
    assert [row["title"] for row in filtered] == ["Rice disease forecasting in Sri Lanka"]

    related = index.related_publications("doi:10.1000/tea", limit=1)
    assert related[0]["title"] == "Rice disease forecasting in Sri Lanka"

    openalex_related = index.related_publications(
        "openalex:https://openalex.org/W1",
        limit=1,
    )
    assert openalex_related[0]["title"] == "Rice disease forecasting in Sri Lanka"

    source_related = index.related_publications("source:openalex:record-1", limit=1)
    assert source_related[0]["title"] == "Rice disease forecasting in Sri Lanka"


def test_embedding_retrieval_reports_missing_and_malformed_artifacts(tmp_path: Path):
    input_csv = tmp_path / "publications.csv"
    output_parquet = tmp_path / "embeddings.parquet"
    model_output = tmp_path / "embedding_model.joblib"
    write_publications_csv(input_csv)

    generate_publication_text_embeddings(
        PublicationEmbeddingConfig(
            input_path=input_csv,
            output_path=output_parquet,
            model_output=model_output,
            text_columns=("title", "abstract", "keywords"),
            metadata_columns=("record_number", "publication_year", "title", "doi"),
            embedding_dim=4,
            max_features=100,
            min_df=1,
            max_df=1.0,
            ngram_max=2,
        )
    )

    with pytest.raises(FileNotFoundError, match="Embeddings artifact not found"):
        load_semantic_search_index(
            embeddings_path=tmp_path / "missing.parquet",
            model_path=model_output,
        )

    with pytest.raises(FileNotFoundError, match="Embedding model artifact not found"):
        load_semantic_search_index(
            embeddings_path=output_parquet,
            model_path=tmp_path / "missing.joblib",
        )

    malformed_parquet = tmp_path / "malformed.parquet"
    pd.DataFrame([{"title": "No embedding columns"}]).to_parquet(
        malformed_parquet,
        index=False,
    )

    with pytest.raises(ValueError, match="does not contain columns"):
        load_semantic_search_index(
            embeddings_path=malformed_parquet,
            model_path=model_output,
        )
