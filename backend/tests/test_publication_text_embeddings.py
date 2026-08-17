"""Tests for publication text embedding generation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from research_analytics.cli import main as cli_main

from src.modeling.embeddings import (
    PublicationEmbeddingConfig,
    generate_publication_text_embeddings,
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
