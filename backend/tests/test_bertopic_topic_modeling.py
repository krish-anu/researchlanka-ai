"""Tests for the semantic (BERTopic) topic-modelling module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modeling.bertopic_topic_modeling import (
    TopicModelConfig,
    add_publication_year,
    build_documents,
    classify_topic_trends,
    distinct_topic_name,
    representative_titles,
    unigram_topic_words,
    unique_topic_names,
)


def test_add_publication_year_reads_mixed_date_formats():
    df = pd.DataFrame({"publication_date": ["2022-04-07", "2019-07", "2018", None, "n.d."]})

    out = add_publication_year(df)

    assert out["publication_year"].tolist() == [2022, 2019, 2018, pd.NA, pd.NA]
    assert "publication_year" not in df.columns


def test_add_publication_year_keeps_existing_column():
    df = pd.DataFrame({"publication_date": ["2022-04-07"], "publication_year": [2020]})

    assert add_publication_year(df)["publication_year"].tolist() == [2020]


def test_build_documents_joins_sentences_and_cleans():
    df = pd.DataFrame(
        {
            "title": ["Crop disease detection தமிழ்"],
            "abstract": [None],
            "keywords": ["deep learning; leaf blight"],
            "topics": ["Smart Agriculture and AI"],
        }
    )

    doc = build_documents(df).iloc[0]

    assert doc == "Crop disease detection. deep learning, leaf blight. Smart Agriculture and AI"


def test_unigram_topic_words_splits_and_dedupes_ngrams():
    words = [["coronavirus", "coronavirus disease", "disease 2019", "the outbreak"]]

    assert unigram_topic_words(words, n=10) == [["coronavirus", "disease", "2019", "outbreak"]]


def test_distinct_topic_name_skips_overlapping_terms():
    words = ["topic modeling", "topic", "language", "language processing", "sinhala"]

    assert distinct_topic_name(words) == "topic modeling / language / sinhala"
    assert distinct_topic_name(["robot", "robotics", "robots", "path planning", "pose"]) == (
        "robot / path planning / pose"
    )
    assert distinct_topic_name(["sign", "signal", "gesture"]) == "sign / signal / gesture"


def test_unique_topic_names_suffixes_collisions():
    words = [["crop", "leaf", "plant"], ["crop", "leaf", "plant"], ["stock", "price", "market"]]

    assert unique_topic_names(words) == [
        "crop / leaf / plant (1)",
        "crop / leaf / plant (2)",
        "stock / price / market",
    ]


def test_representative_titles_picks_closest_to_centroid():
    embeddings = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.6, 0.8]])
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    labels = np.array([1, 1, 2, 2])
    titles = pd.Series(["a", "b", "c", "d"])

    out = representative_titles(embeddings, labels, titles, n=1)

    assert set(out) == {1, 2}
    assert out[1][0] in {"a", "b"}


def test_classify_topic_trends_labels_emerging_and_declining():
    years = list(range(2016, 2026))
    shares = pd.DataFrame(
        {
            "rising": np.linspace(0.1, 0.6, len(years)),
            "falling": np.linspace(0.6, 0.1, len(years)),
            "flat": [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
        },
        index=years,
    )
    keywords = pd.DataFrame({"topic_id": [1, 2, 3], "topic_name": ["rising", "falling", "flat"]})

    trends = classify_topic_trends(shares, keywords).set_index("topic_name")["trend"]

    assert trends["rising"] == "emerging"
    assert trends["falling"] == "declining"
    assert trends["flat"] == "stable"


def test_run_final_pipeline_end_to_end(tmp_path):
    pytest.importorskip("bertopic")
    pytest.importorskip("umap")
    from src.modeling.bertopic_topic_modeling import run_final_pipeline

    themes = {
        "crop leaf disease plant agriculture": 2016,
        "stock market price forecasting finance": 2020,
        "sentiment text language social media": 2024,
    }
    rng = np.random.default_rng(0)
    rows, vectors = [], []
    for i, (text, base_year) in enumerate(themes.items()):
        centre = np.zeros(16)
        centre[i] = 1.0
        for j in range(30):
            rows.append({"title": f"{text} {j}", "publication_year": base_year + j % 3})
            vectors.append(centre + rng.normal(scale=0.05, size=16))
    df = pd.DataFrame(rows)
    embeddings = np.asarray(vectors, dtype=np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

    result = run_final_pipeline(
        df=df,
        output_dir=tmp_path,
        config=TopicModelConfig(n_topics=3, mmr_diversity=None, min_df=1),
        embeddings=embeddings,
        docs=df["title"],
        write_html=False,
    )

    assert sorted(set(result["labels"])) == [1, 2, 3]
    assert (tmp_path / "bertopic_topic_keywords.csv").exists()
    assert (tmp_path / "bertopic_topic_trends.csv").exists()
    pubs = pd.read_csv(tmp_path / "bertopic_publication_topics.csv")
    # each synthetic theme should map to exactly one topic
    assert pubs.groupby(pubs.index // 30)["bertopic_topic_id"].nunique().eq(1).all()
