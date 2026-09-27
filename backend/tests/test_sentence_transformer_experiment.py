"""Tests for sentence-transformer AI relevance experiment plumbing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.ai_relevance.embedding_experiment import (
    SentenceTransformerExperimentConfig,
    run_sentence_transformer_experiment,
)


class KeywordEncoder:
    def encode(self, texts: list[str], **_kwargs):
        rows = []
        for text in texts:
            lowered = text.casefold()
            ai_signal = float(
                any(
                    term in lowered
                    for term in (
                        "machine learning",
                        "deep learning",
                        "neural network",
                        "representation learning",
                    )
                )
            )
            non_ai_signal = float(
                any(term in lowered for term in ("soil", "survey", "accounting", "bridge"))
            )
            length_signal = min(len(lowered) / 100.0, 1.0)
            rows.append([ai_signal, non_ai_signal, length_signal])
        return np.asarray(rows, dtype=np.float32)


def write_split(path: Path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_sentence_transformer_experiment_writes_frozen_metrics(tmp_path: Path) -> None:
    selection_dir = tmp_path / "selection"
    output_dir = tmp_path / "embedding_experiment"
    selection_dir.mkdir()
    common_ai = {
        "label": "AI",
        "label_source": "human_train",
        "title": "Deep representation learning for crop disease",
        "abstract": "A neural network identifies disease.",
        "keywords": "deep learning",
        "doi": "",
    }
    common_non_ai = {
        "label": "NON_AI",
        "label_source": "human_train",
        "title": "Soil nutrient survey",
        "abstract": "A field survey measures soil chemistry.",
        "keywords": "soil",
        "doi": "",
    }
    write_split(
        selection_dir / "selection_training_dataset.csv",
        [
            {"record_key": "ai-1", **common_ai},
            {"record_key": "ai-2", **common_ai, "title": "Machine learning for tea yield"},
            {"record_key": "non-1", **common_non_ai},
            {"record_key": "non-2", **common_non_ai, "title": "Accounting compliance survey"},
        ],
    )
    write_split(
        selection_dir / "human_validation_set.csv",
        [
            {"record_key": "val-ai", **common_ai},
            {"record_key": "val-non", **common_non_ai},
        ],
    )
    write_split(
        selection_dir / "frozen_human_test_set.csv",
        [
            {"record_key": "test-ai", **common_ai},
            {"record_key": "test-non", **common_non_ai},
        ],
    )

    summary = run_sentence_transformer_experiment(
        SentenceTransformerExperimentConfig(
            selection_dir=selection_dir,
            output_dir=output_dir,
            sentence_transformer_model="fake-keyword-encoder",
            classifiers=("logistic_regression",),
            human_weight=1.0,
        ),
        encoder=KeywordEncoder(),
    )

    comparison = pd.read_csv(summary["comparison_csv"])
    assert summary["experiment_type"] == "sentence_transformer_embeddings"
    assert summary["best_model_family"] == "sentence_transformer_logistic_regression"
    assert "brier_score" in comparison.columns
    assert "false_positives" in comparison.columns
    assert Path(summary["models"][0]["model_path"]).exists()
    assert Path(summary["models"][0]["false_positives_path"]).exists()
    assert (output_dir / "sentence_transformer_metrics.txt").exists()
