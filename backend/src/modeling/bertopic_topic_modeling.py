"""
Semantic (BERTopic) topic modelling for ResearchLanka.

NMF (nmf_topic_modeling.py) factorises a TF-IDF matrix, so it groups papers
that share *words*: "crop disease detection" and "leaf blight classification"
land in different topics unless they reuse vocabulary. The accepted AI corpus
is now small (~4k papers), so it is cheap to embed every paper with a
pretrained sentence transformer and cluster by *meaning* instead:

    text -> sentence-transformer embedding -> UMAP (5-d) -> KMeans / HDBSCAN
         -> c-TF-IDF keywords per cluster (same stopwords as NMF)

Clustering:
  - "kmeans" (default) fixes the number of topics, like NMF's k, and assigns
    every paper to a topic - what the per-year trend tables need.
  - "hdbscan" lets density decide the topic count; its outliers (topic -1) are
    reassigned to the nearest topic by embedding similarity so trend counts
    still cover the whole corpus.

Evaluation reuses the NMF metrics (coherence, diversity, redundancy) but
scores *unigram* top words against a unigram reference corpus, so NMF's 1-3
gram topic words ("coronavirus disease", "disease 2019", ...) and BERTopic's
1-2 gram words compete on the same footing. compare_with_nmf() fits NMF on
the same documents and k so the two can be compared directly.

Trend analysis reuses topic_trend_table() and nmf_trends.classify_trend(), so
emerging / declining / stable topics are labelled exactly the same way for
both models.

bertopic, sentence-transformers, umap-learn and gensim are imported lazily so
the pure helpers stay importable where only requirements.txt is installed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

from src.modeling.nmf_topic_modeling import (
    build_tfidf,
    compute_pairwise_redundancy,
    compute_topic_diversity,
    fit_nmf,
    get_topic_keywords,
    topic_trend_table,
)
from src.modeling.nmf_trends import classify_trend, topic_trend_slopes
from src.preprocessing.text_cleaning import CUSTOM_STOP_WORDS, clean_text_series


# --------------------------------------------------------------------------
# Text prep
# --------------------------------------------------------------------------

# `concepts` is left out on purpose: in this AI-only corpus it is dominated by
# generic OpenAlex taxonomy terms ("Computer science; Artificial intelligence;
# Mathematics"). Adding it cut NPMI coherence from ~0.19 to ~0.11 at k=15/20/25
# with no diversity gain. `topics` (OpenAlex's 3 topic labels) stays in because
# ~74% of rows have no abstract and the title alone is a thin signal.
EMBEDDING_TEXT_COLUMNS = ("title", "abstract", "keywords", "topics")
DEFAULT_EMBEDDING_MODEL = "all-mpnet-base-v2"
DEFAULT_N_WORDS = 10
YEAR_COLUMN = "publication_year"

_LEADING_YEAR = re.compile(r"^\s*(\d{4})")


def add_publication_year(
    df: pd.DataFrame, date_col: str = "publication_date", year_col: str = YEAR_COLUMN
) -> pd.DataFrame:
    """Adds an integer year column derived from `date_col` if it isn't there.

    publication_date mixes "2022-04-07", "2022-01" and "2022", which
    pd.to_datetime() can't infer as one format, so the leading 4-digit year is
    read straight from the string instead.
    """
    if year_col in df.columns or date_col not in df.columns:
        return df
    out = df.copy()
    years = out[date_col].astype("string").str.extract(_LEADING_YEAR, expand=False)
    out[year_col] = pd.to_numeric(years, errors="coerce").astype("Int64")
    return out


def build_documents(
    frame: pd.DataFrame, text_columns=EMBEDDING_TEXT_COLUMNS
) -> pd.Series:
    """Joins the text columns as sentences ("Title. Abstract. kw1, kw2.") so the
    embedding model reads prose rather than one run-on string, then applies the
    same Tamil/Sinhala-script and boilerplate stripping as NMF."""
    parts = frame[list(text_columns)].apply(
        lambda col: clean_text_series(col).str.replace(r"\s*;\s*", ", ", regex=True)
    )
    return parts.apply(lambda row: ". ".join(p for p in row if p), axis=1)


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------


def load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL, device: Optional[str] = None):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def encode_documents(
    docs: list[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    cache_dir: Optional[Path] = None,
    embedding_model=None,
    batch_size: int = 32,
    device: Optional[str] = None,
) -> np.ndarray:
    """L2-normalised document embeddings, cached on disk by (model, docs) hash
    so k sweeps and re-runs don't re-encode the corpus."""
    cache_path = None
    if cache_dir is not None:
        digest = hashlib.sha256(
            "\0".join([model_name, *docs]).encode("utf-8")
        ).hexdigest()[:16]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name)
        cache_path = Path(cache_dir) / f"embeddings_{safe_name}_{digest}.npy"
        if cache_path.exists():
            print(f"Loaded cached embeddings: {cache_path}")
            return np.load(cache_path)

    model = embedding_model or load_embedding_model(model_name, device=device)
    embeddings = model.encode(
        docs,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, embeddings)
    return embeddings


# --------------------------------------------------------------------------
# BERTopic fitting
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicModelConfig:
    clustering: str = "kmeans"  # "kmeans" | "hdbscan"
    n_topics: int = 20  # kmeans only
    min_cluster_size: int = 20  # hdbscan only
    umap_neighbors: int = 15
    umap_components: int = 5
    ngram_range: tuple[int, int] = (1, 2)
    min_df: int = 2
    n_words: int = DEFAULT_N_WORDS
    # MaximalMarginalRelevance diversity for the keyword list; None keeps plain
    # c-TF-IDF words (no embedding model needed, e.g. in tests).
    mmr_diversity: Optional[float] = 0.3
    random_state: int = 42


# n-gram topic terms overlap ("tutoring", "tutoring systems", "intelligent
# tutoring systems"), so n_words terms can collapse to ~5 unique unigrams, and
# coherence over fewer words is higher. Both models therefore keep
# n_words * SCORING_TERMS_FACTOR ranked terms for scoring and show the first
# n_words. MMR selects greedily, so its first n_words don't change.
SCORING_TERMS_FACTOR = 3


def _n_terms(config: TopicModelConfig) -> int:
    return config.n_words * SCORING_TERMS_FACTOR


def build_vectorizer(config: TopicModelConfig) -> CountVectorizer:
    return CountVectorizer(
        lowercase=True,
        stop_words=CUSTOM_STOP_WORDS,
        strip_accents="unicode",
        ngram_range=config.ngram_range,
        min_df=config.min_df,
    )


def _topic_model_parts(config: TopicModelConfig) -> dict[str, Any]:
    from bertopic.representation import MaximalMarginalRelevance
    from bertopic.vectorizers import ClassTfidfTransformer

    return {
        "vectorizer_model": build_vectorizer(config),
        "ctfidf_model": ClassTfidfTransformer(reduce_frequent_words=True),
        "representation_model": (
            MaximalMarginalRelevance(diversity=config.mmr_diversity, top_n_words=_n_terms(config))
            if config.mmr_diversity is not None
            else None
        ),
    }


def build_topic_model(config: TopicModelConfig, embedding_model=None):
    from bertopic import BERTopic
    from umap import UMAP

    umap_model = UMAP(
        n_neighbors=config.umap_neighbors,
        n_components=config.umap_components,
        min_dist=0.0,
        metric="cosine",
        random_state=config.random_state,
    )
    if config.clustering == "kmeans":
        from sklearn.cluster import KMeans

        cluster_model = KMeans(
            n_clusters=config.n_topics, n_init=10, random_state=config.random_state
        )
    elif config.clustering == "hdbscan":
        from hdbscan import HDBSCAN

        cluster_model = HDBSCAN(
            min_cluster_size=config.min_cluster_size,
            metric="euclidean",
            cluster_selection_method="eom",
            prediction_data=True,
        )
    else:
        raise ValueError(f"Unknown clustering: {config.clustering!r} (use kmeans or hdbscan)")

    return BERTopic(
        embedding_model=embedding_model,
        umap_model=umap_model,
        hdbscan_model=cluster_model,
        top_n_words=_n_terms(config),
        calculate_probabilities=False,
        verbose=False,
        **_topic_model_parts(config),
    )


def fit_topic_model(
    docs: list[str],
    embeddings: np.ndarray,
    config: TopicModelConfig,
    embedding_model=None,
):
    """Returns (fitted BERTopic, per-document topic array with no -1 outliers)."""
    model = build_topic_model(config, embedding_model=embedding_model)
    topics, _ = model.fit_transform(docs, embeddings)
    topics = np.asarray(topics)

    if (topics == -1).any():
        n_outliers = int((topics == -1).sum())
        topics = np.asarray(
            model.reduce_outliers(docs, topics, strategy="embeddings", embeddings=embeddings)
        )
        # update_topics() falls back to a stopword-free default CountVectorizer
        # unless the parts are passed again.
        model.update_topics(docs, topics=topics.tolist(), top_n_words=_n_terms(config), **_topic_model_parts(config))
        print(f"Reassigned {n_outliers} HDBSCAN outliers to their nearest topic.")

    return model, topics


def topic_keywords(model, n_words: int = DEFAULT_N_WORDS) -> tuple[list[int], list[list[str]]]:
    """(BERTopic topic ids in ascending order, top words per topic), skipping -1."""
    topic_ids = sorted(t for t in model.get_topics() if t != -1)
    words = [[w for w, _ in model.get_topic(t)[:n_words] if w] for t in topic_ids]
    return topic_ids, words


def _same_word(a: str, b: str) -> bool:
    """Equal, or a plural/derived form ("robot" ~ "robots" ~ "robotics").
    The 5-letter floor keeps e.g. "sign" and "signal" apart."""
    short, long = sorted((a, b), key=len)
    return short == long or (len(short) >= 5 and long.startswith(short))


def distinct_topic_name(words: list[str], n: int = 3) -> str:
    """First n terms that don't share a word with a term already picked, so
    "topic modeling, topic, language" gives "topic modeling / language / ..."
    rather than repeating "topic"."""
    picked: list[str] = []
    seen: set[str] = set()
    for term in words:
        tokens = set(term.split())
        if any(_same_word(t, s) for t in tokens for s in seen):
            continue
        picked.append(term)
        seen |= tokens
        if len(picked) == n:
            break
    return " / ".join(picked)


def unique_topic_names(topic_words: list[list[str]], n: int = 3) -> list[str]:
    """distinct_topic_name() labels, suffixed with the topic number when two
    collide - the trend tables use names as column headers, so they must be
    unique."""
    names = [distinct_topic_name(words, n=n) for words in topic_words]
    counts = pd.Series(names).value_counts()
    return [
        f"{name} ({i})" if counts[name] > 1 else name
        for i, name in enumerate(names, start=1)
    ]


def representative_titles(
    embeddings: np.ndarray, labels: np.ndarray, titles: pd.Series, n: int = 3
) -> dict[int, list[str]]:
    """Titles closest to each topic's embedding centroid - easier to name a
    topic from than keywords alone."""
    titles = titles.fillna("").astype(str).to_numpy()
    out = {}
    for label in np.unique(labels):
        idx = np.flatnonzero(labels == label)
        centroid = embeddings[idx].mean(axis=0)
        sims = embeddings[idx] @ centroid
        out[int(label)] = [titles[i] for i in idx[np.argsort(sims)[::-1][:n]]]
    return out


# --------------------------------------------------------------------------
# Evaluation (shared by BERTopic and NMF so the numbers are comparable)
# --------------------------------------------------------------------------


def reference_analyzer():
    """Unigram analyzer used for both the coherence corpus and topic words."""
    return CountVectorizer(
        lowercase=True, stop_words=CUSTOM_STOP_WORDS, strip_accents="unicode"
    ).build_analyzer()


def unigram_topic_words(topic_words: list[list[str]], n: int = DEFAULT_N_WORDS) -> list[list[str]]:
    """Splits n-gram topic terms into unique unigrams, in rank order.

    NMF topics routinely list the same phrase several ways ("coronavirus",
    "coronavirus disease", "disease 2019", ...). Scoring those n-grams against
    an n-gram-tokenised corpus inflates coherence, because overlapping n-grams
    of one phrase always co-occur. Unigrams put every model on equal footing.
    """
    analyze = reference_analyzer()
    out = []
    for words in topic_words:
        seen: list[str] = []
        for term in words:
            for tok in analyze(term):
                if tok not in seen:
                    seen.append(tok)
        out.append(seen[:n])
    return out


class CoherenceReference:
    """Tokenised corpus + gensim dictionary, built once and reused for every
    model scored against the same documents."""

    def __init__(self, docs: pd.Series | list[str]):
        from gensim.corpora import Dictionary

        analyze = reference_analyzer()
        self.tokenized = [analyze(d) for d in pd.Series(docs).fillna("")]
        self.dictionary = Dictionary(self.tokenized)

    def score(self, topic_words: list[list[str]], measure: str) -> float:
        from gensim.models import CoherenceModel

        topics = [[w for w in words if w in self.dictionary.token2id] for words in topic_words]
        topics = [t for t in topics if len(t) >= 2]
        return float(
            CoherenceModel(
                topics=topics,
                texts=self.tokenized,
                dictionary=self.dictionary,
                coherence=measure,
                processes=1,
            ).get_coherence()
        )


def evaluate_topics(
    topic_words: list[list[str]],
    labels: np.ndarray,
    embeddings: np.ndarray,
    reference: Optional[CoherenceReference] = None,
    n_words: int = DEFAULT_N_WORDS,
) -> dict[str, float]:
    """Keyword quality (coherence, diversity, redundancy on each topic's first
    n_words unique unigrams - pass n_words * SCORING_TERMS_FACTOR ranked terms
    so there are enough) plus how semantically tight the document groups are
    (cosine silhouette on the sentence embeddings). The silhouette naturally favours the model that
    clustered in that space, but it measures exactly what the switch to
    semantic topics is meant to improve."""
    from sklearn.metrics import silhouette_score

    words = unigram_topic_words(topic_words, n=n_words)
    sizes = pd.Series(labels).value_counts()
    metrics = {
        "n_topics": len(topic_words),
        "coherence_cv": reference.score(words, "c_v") if reference else np.nan,
        "coherence_npmi": reference.score(words, "c_npmi") if reference else np.nan,
        "diversity": compute_topic_diversity(words, top_n=n_words),
        "redundancy": compute_pairwise_redundancy(words, top_n=n_words),
        "silhouette_cosine": (
            float(silhouette_score(embeddings, labels, metric="cosine"))
            if sizes.size > 1
            else np.nan
        ),
        "largest_topic_share": float(sizes.max() / sizes.sum()),
        "smallest_topic_size": int(sizes.min()),
    }
    return metrics


# --------------------------------------------------------------------------
# Sweep + NMF comparison
# --------------------------------------------------------------------------


def sweep_n_topics(
    docs: list[str],
    embeddings: np.ndarray,
    k_range: list[int],
    base_config: TopicModelConfig,
    embedding_model=None,
    reference: Optional[CoherenceReference] = None,
) -> pd.DataFrame:
    rows = []
    for k in k_range:
        config = replace(base_config, n_topics=k)
        model, labels = fit_topic_model(docs, embeddings, config, embedding_model)
        _, terms = topic_keywords(model, n_words=_n_terms(config))
        metrics = {"k": k, **evaluate_topics(terms, labels, embeddings, reference, config.n_words)}
        rows.append(metrics)
        print(
            f"k={k:>3}  c_v={metrics['coherence_cv']:.4f}  npmi={metrics['coherence_npmi']:.4f}  "
            f"diversity={metrics['diversity']:.3f}  silhouette={metrics['silhouette_cosine']:.3f}"
        )
    return pd.DataFrame(rows)


def pick_best_k(summary_df: pd.DataFrame) -> int:
    """Highest NPMI coherence x diversity (Dieng et al., 2020 'topic quality').
    Coherence alone always favours the smallest k; the diversity term stops
    the sweep from picking a few broad, overlapping topics."""
    quality = summary_df["coherence_npmi"] * summary_df["diversity"]
    return int(summary_df.loc[quality.idxmax(), "k"])


def compare_with_nmf(
    docs: pd.Series,
    embeddings: np.ndarray,
    bertopic_terms: list[list[str]],
    bertopic_labels: np.ndarray,
    k: int,
    reference: Optional[CoherenceReference] = None,
    n_words: int = DEFAULT_N_WORDS,
    random_state: int = 42,
) -> pd.DataFrame:
    """Fits NMF on the *same* documents at the same k and scores both models
    with the same metrics, so the only difference is word-frequency vs
    semantic grouping."""
    vectorizer, X = build_tfidf(docs)
    nmf, W = fit_nmf(X, k, random_state=random_state)
    nmf_terms = get_topic_keywords(
        nmf, vectorizer.get_feature_names_out(), n_words=n_words * SCORING_TERMS_FACTOR
    )
    nmf_labels = W.argmax(axis=1)

    rows = [
        {"model": "nmf_tfidf", **evaluate_topics(nmf_terms, nmf_labels, embeddings, reference, n_words)},
        {"model": "bertopic", **evaluate_topics(bertopic_terms, bertopic_labels, embeddings, reference, n_words)},
    ]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Trend analysis
# --------------------------------------------------------------------------


def classify_topic_trends(
    shares: pd.DataFrame, keywords_df: pd.DataFrame, alpha: float = 0.10
) -> pd.DataFrame:
    """Emerging / declining / stable per topic (same rule as the NMF trends),
    joined back to topic ids, sizes and keywords."""
    trends = classify_trend(topic_trend_slopes(shares), alpha=alpha)
    return keywords_df.merge(trends, on="topic_name", how="left").sort_values(
        "slope_per_year", ascending=False
    )


# --------------------------------------------------------------------------
# End-to-end pipeline for one final config (used by the CLI script)
# --------------------------------------------------------------------------


def run_final_pipeline(
    df: pd.DataFrame,
    output_dir: Path,
    config: TopicModelConfig,
    embeddings: np.ndarray,
    docs: pd.Series,
    embedding_model=None,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    reference: Optional[CoherenceReference] = None,
    year_col: str = YEAR_COLUMN,
    naming_words: int = 3,
    save_model: bool = False,
    write_html: bool = True,
) -> dict[str, Any]:
    """Fits BERTopic with `config` on rows that have text and writes to output_dir:
    - bertopic_topic_keywords.csv              (id, name, size, keywords, example titles)
    - bertopic_topic_annotation_template.csv   (fill in manual names by hand)
    - bertopic_publication_topics.csv          (df + bertopic_topic_id/name/similarity)
    - bertopic_topic_trend_counts.csv / bertopic_topic_trend_shares.csv
    - bertopic_topic_trends.csv                (slope, p-value, emerging/declining/stable)
    - bertopic_evaluation.csv
    - bertopic_*.html                          (interactive plots, if write_html)
    - model/                                   (BERTopic safetensors, if save_model)

    `df`, `docs` and `embeddings` must be row-aligned; rows whose cleaned
    text is empty should already be filtered out.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_list = docs.tolist()

    model, raw_topics = fit_topic_model(doc_list, embeddings, config, embedding_model)
    topic_ids, terms = topic_keywords(model, n_words=_n_terms(config))
    words = [t[: config.n_words] for t in terms]
    names = unique_topic_names(words, n=naming_words)

    # BERTopic ids are 0-based (and only size-ordered before outlier
    # reduction); expose 1-based ids like the NMF artifacts.
    id_map = {t: i for i, t in enumerate(topic_ids, start=1)}
    labels = np.array([id_map[t] for t in raw_topics])

    examples = representative_titles(embeddings, labels, df["title"])
    sizes = pd.Series(labels).value_counts()
    keywords_df = pd.DataFrame(
        {
            "topic_id": range(1, len(words) + 1),
            "topic_name": names,
            "size": [int(sizes.get(i, 0)) for i in range(1, len(words) + 1)],
            "top_words": [", ".join(w) for w in words],
            "example_titles": [" | ".join(examples.get(i, [])) for i in range(1, len(words) + 1)],
        }
    )
    keywords_df.to_csv(output_dir / "bertopic_topic_keywords.csv", index=False)

    keywords_df.assign(manual_name="", interpretability_score_1to5="", notes="")[
        ["topic_id", "topic_name", "top_words", "example_titles", "manual_name",
         "interpretability_score_1to5", "notes"]
    ].to_csv(output_dir / "bertopic_topic_annotation_template.csv", index=False)

    # Cosine similarity of each paper to its topic centroid: a confidence-like
    # weight analogous to nmf_topic_weight.
    centroids = np.vstack([embeddings[labels == i].mean(axis=0) for i in range(1, len(words) + 1)])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    similarity = np.einsum("ij,ij->i", embeddings, centroids[labels - 1])

    pub_topics = df.copy()
    pub_topics["bertopic_topic_id"] = labels
    pub_topics["bertopic_topic_name"] = [names[i - 1] for i in labels]
    pub_topics["bertopic_topic_similarity"] = similarity.round(4)
    pub_topics.to_csv(output_dir / "bertopic_publication_topics.csv", index=False)

    counts, shares = topic_trend_table(pub_topics, labels - 1, year_col, names)
    counts.to_csv(output_dir / "bertopic_topic_trend_counts.csv")
    shares.to_csv(output_dir / "bertopic_topic_trend_shares.csv")
    trends = classify_topic_trends(shares, keywords_df)
    trends.to_csv(output_dir / "bertopic_topic_trends.csv", index=False)

    metrics = evaluate_topics(terms, labels, embeddings, reference, config.n_words)
    # metrics last: for hdbscan the fitted topic count replaces config.n_topics
    evaluation = pd.DataFrame(
        [{**asdict(config), **metrics, "embedding_model": embedding_model_name}]
    )
    evaluation.to_csv(output_dir / "bertopic_evaluation.csv", index=False)

    if write_html:
        _write_visualisations(model, doc_list, pub_topics[year_col], output_dir)
    if save_model:
        model.save(
            output_dir / "model",
            serialization="safetensors",
            save_ctfidf=True,
            save_embedding_model=embedding_model_name,
        )

    print(
        f"\nBERTopic {config.clustering} topics={len(words)}  "
        f"c_v={metrics['coherence_cv']:.4f}  npmi={metrics['coherence_npmi']:.4f}  "
        f"diversity={metrics['diversity']:.3f}  silhouette={metrics['silhouette_cosine']:.3f}"
    )
    print(trends["trend"].value_counts().to_string())
    print(f"Artifacts written to: {output_dir}")

    return {
        "model": model,
        "labels": labels,
        "topic_words": words,
        "topic_terms": terms,
        "topic_names": names,
        "keywords_df": keywords_df,
        "pub_topics": pub_topics,
        "counts": counts,
        "shares": shares,
        "trends": trends,
        "metrics": metrics,
    }


def _write_visualisations(model, docs: list[str], years: pd.Series, output_dir: Path) -> None:
    """Interactive plotly views from BERTopic. Best-effort: a plotting failure
    shouldn't throw away a finished fit."""
    try:
        has_year = years.notna().to_numpy()
        over_time = model.topics_over_time(
            [d for d, keep in zip(docs, has_year) if keep],
            years[has_year].astype(int).tolist(),
            topics=[t for t, keep in zip(model.topics_, has_year) if keep],
        )
        model.visualize_topics_over_time(over_time, top_n_topics=len(model.get_topics())).write_html(
            output_dir / "bertopic_topics_over_time.html"
        )
        model.visualize_barchart(top_n_topics=len(model.get_topics()), n_words=8).write_html(
            output_dir / "bertopic_topic_keywords.html"
        )
        model.visualize_topics().write_html(output_dir / "bertopic_intertopic_map.html")
    except Exception as exc:  # noqa: BLE001
        print(f"Skipped BERTopic visualisations: {exc}")
