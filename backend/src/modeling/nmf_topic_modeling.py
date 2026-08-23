"""
NMF topic-modelling module for ResearchLanka.

Covers the 5 deliverables:
  1. topic keywords            -> get_topic_keywords()
  2. topic naming               -> name_topics() (+ build_annotation_template() for manual naming)
  3. topic coherence            -> compute_coherence()  (gensim c_v)
  4. topic interpretability     -> compute_topic_diversity(), compute_pairwise_redundancy(),
                                    build_annotation_template() for the human-scored part
                                    (interpretability isn't fully automatable — diversity/redundancy
                                    are proxies, the annotation template is for you to hand-score)
  5. trend analysis             -> assign_dominant_topic(), topic_trend_table()

Text cleaning (fixes the Tamil-token topic and the metadata-boilerplate topic
seen in the k=10 baseline) lives in text_cleaning.py and is applied inside
combined_text() by default - see its `clean=` argument. Row-dropping was
considered and rejected (~1928 affected rows is too much of the corpus to
lose), so cleaning happens at the token/phrase level instead.

FIX: tokenize_docs() now optionally tokenizes with the SAME TfidfVectorizer
analyzer (ngram_range=(1, 3), stop words, accent-stripping) used to build the
topic-word vocabulary, instead of a bare whitespace .split(). Without this,
any topic whose top words include a bigram/trigram (very common here, since
ngram_range=(1, 3)) would hand gensim's CoherenceModel "words" that never
appear as single whitespace-delimited tokens in its dictionary — silently
breaking (or erroring on) coherence for those topics. evaluate_k_range() and
run_final_pipeline() now pass the fitted vectorizer through so this is fixed
end to end.

Import this from the test notebook or from scripts/run_nmf_pipeline.py — don't duplicate logic
in both places.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

from src.preprocessing.text_cleaning import (
    CUSTOM_STOP_WORDS,
    clean_text_series,
    cleaning_report,
)

try:
    from gensim.corpora import Dictionary
    from gensim.models import CoherenceModel

    _GENSIM_AVAILABLE = True
except ImportError:  # coherence is optional at import time, required at call time
    _GENSIM_AVAILABLE = False


# --------------------------------------------------------------------------
# Text prep
# --------------------------------------------------------------------------

TEXT_COLUMNS = ["title", "abstract", "topics", "keywords", "concepts"]


def combined_text(
    frame: pd.DataFrame, text_columns=TEXT_COLUMNS, clean: bool = True
) -> pd.Series:
    """Same column-joining logic as the SVM step, reused so NMF sees the same text.

    clean=True (default) additionally strips Tamil/Sinhala-script tokens and
    known metadata-boilerplate phrases (see text_cleaning.py) instead of
    dropping the affected rows. Pass clean=False to reproduce the original
    uncleaned baseline for an A/B comparison in the sweep.
    """
    text = frame[list(text_columns)].fillna("").astype(str).agg(" ".join, axis=1)
    text = text.str.replace(r"\s+", " ", regex=True).str.strip()
    if clean:
        text = clean_text_series(text)
    return text


def find_year_column(
    df: pd.DataFrame, candidates=("publication_year", "year", "pub_year", "date")
) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


# --------------------------------------------------------------------------
# TF-IDF + NMF fitting
# --------------------------------------------------------------------------

DEFAULT_TFIDF_KWARGS = dict(
    lowercase=True,
    stop_words=CUSTOM_STOP_WORDS,  # sklearn's "english" list + domain terms (study/using/data/...)
    strip_accents="unicode",
    ngram_range=(1, 3),
    min_df=5,
    max_df=0.95,
    sublinear_tf=True,
)


def build_tfidf(
    texts: pd.Series, **tfidf_kwargs
) -> tuple[TfidfVectorizer, sparse.csr_matrix]:
    kwargs = {**DEFAULT_TFIDF_KWARGS, **tfidf_kwargs}
    vectorizer = TfidfVectorizer(**kwargs)
    X = vectorizer.fit_transform(texts)
    return vectorizer, X


def fit_nmf(
    X, k: int, random_state: int = 42, max_iter: int = 500
) -> tuple[NMF, np.ndarray]:
    model = NMF(
        n_components=k,
        init="nndsvda",
        solver="cd",
        max_iter=max_iter,
        random_state=random_state,
    )
    W = model.fit_transform(X)
    return model, W


# --------------------------------------------------------------------------
# 1. Keywords + 2. Naming
# --------------------------------------------------------------------------


def get_topic_keywords(model: NMF, feature_names, n_words: int = 15) -> list[list[str]]:
    topics = []
    for topic in model.components_:
        top_idx = topic.argsort()[-n_words:][::-1]
        topics.append([feature_names[i] for i in top_idx])
    return topics


def name_topic(words: list[str], n: int = 3) -> str:
    """Cheap auto-label from a topic's top words. Meant as a starting point — relabel
    by hand in the annotation template once you've eyeballed the keywords."""
    return " / ".join(w.replace(" ", "_") for w in words[:n])


def name_topics(topic_words: list[list[str]], n: int = 3) -> list[str]:
    return [name_topic(words, n=n) for words in topic_words]


def build_annotation_template(
    topic_words: list[list[str]], topic_names: list[str], n_words: int = 10
) -> pd.DataFrame:
    """CSV you fill in by hand: this is the real 'interpretability evaluation' step.
    Diversity/redundancy below are cheap proxies — human judgement is what actually counts."""
    return pd.DataFrame(
        {
            "topic_id": range(1, len(topic_words) + 1),
            "auto_name": topic_names,
            "top_words": [", ".join(w[:n_words]) for w in topic_words],
            "manual_name": "",
            "interpretability_score_1to5": "",
            "notes": "",
        }
    )


# --------------------------------------------------------------------------
# 3. Coherence
# --------------------------------------------------------------------------


def tokenize_docs(
    texts: pd.Series, vectorizer: Optional[TfidfVectorizer] = None
) -> list[list[str]]:
    """Tokenize documents for gensim coherence scoring.

    When `vectorizer` is given, tokens are produced with that vectorizer's
    OWN analyzer (respects ngram_range, stop_words, lowercase, strip_accents)
    so multi-word n-gram topic terms — this pipeline uses ngram_range=(1, 3),
    so topic words are routinely bigrams/trigrams like "machine learning" —
    actually appear as tokens in the coherence dictionary.

    Falling back to a bare whitespace .split() (vectorizer=None) only
    produces single-word tokens, which silently breaks coherence scoring for
    any topic whose top words include an n-gram: those "words" never match
    anything in a dictionary built from single-word tokens. Always pass the
    fitted vectorizer when tokenizing for compute_coherence()/evaluate_k*().
    """
    if vectorizer is not None:
        analyze = vectorizer.build_analyzer()
        return [analyze(t) for t in texts.fillna("")]
    return texts.fillna("").apply(str.split).tolist()


def compute_coherence(
    topic_words: list[list[str]],
    tokenized_docs: list[list[str]],
    dictionary,
    coherence: str = "c_v",
) -> float:
    if not _GENSIM_AVAILABLE:
        raise ImportError(
            "gensim is required for coherence scoring: pip install gensim"
        )
    cm = CoherenceModel(
        topics=topic_words,
        texts=tokenized_docs,
        dictionary=dictionary,
        coherence=coherence,
    )
    return cm.get_coherence()


# --------------------------------------------------------------------------
# 4. Interpretability proxies
# --------------------------------------------------------------------------


def compute_topic_diversity(topic_words: list[list[str]], top_n: int = 15) -> float:
    """Share of unique words across all topics' top-N words (Dieng et al., 2020 TD metric).
    Close to 1.0 = topics use mostly distinct vocabulary (good). Close to 0 = topics overlap
    heavily / are redundant (bad)."""
    all_words = [w for words in topic_words for w in words[:top_n]]
    if not all_words:
        return 0.0
    return len(set(all_words)) / len(all_words)


def compute_pairwise_redundancy(topic_words: list[list[str]], top_n: int = 15) -> float:
    """Mean Jaccard similarity between every pair of topics' top-N word sets.
    Lower = topics are more distinct from each other (good)."""
    sets = [set(words[:top_n]) for words in topic_words]
    if len(sets) < 2:
        return 0.0
    sims = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            union = sets[i] | sets[j]
            if union:
                sims.append(len(sets[i] & sets[j]) / len(union))
    return float(np.mean(sims)) if sims else 0.0


# --------------------------------------------------------------------------
# Evaluate one k (bundles reconstruction error / coherence / diversity / redundancy)
# --------------------------------------------------------------------------


def evaluate_k(
    X,
    feature_names,
    tokenized_docs: list[list[str]],
    dictionary,
    k: int,
    n_words: int = 15,
    random_state: int = 42,
) -> dict:
    model, W = fit_nmf(X, k, random_state=random_state)
    topic_words = get_topic_keywords(model, feature_names, n_words=n_words)
    return {
        "k": k,
        "model": model,
        "W": W,
        "topic_words": topic_words,
        "iterations": model.n_iter_,
        "reconstruction_error": model.reconstruction_err_,
        "coherence_cv": compute_coherence(topic_words, tokenized_docs, dictionary),
        "diversity": compute_topic_diversity(topic_words, top_n=n_words),
        "redundancy": compute_pairwise_redundancy(topic_words, top_n=n_words),
    }


def evaluate_k_range(
    X,
    feature_names,
    texts: pd.Series,
    k_range: list[int],
    vectorizer: Optional[TfidfVectorizer] = None,
    n_words: int = 15,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict]:
    """Runs evaluate_k() for every k in k_range. Returns (summary_df, {k: full_result_dict}).

    Pass the fitted `vectorizer` (the one used to build X/feature_names) so
    coherence tokenization matches the n-gram vocabulary the topics are
    drawn from — see tokenize_docs() for why this matters.
    """
    if not _GENSIM_AVAILABLE:
        raise ImportError(
            "gensim is required for coherence scoring: pip install gensim"
        )

    tokenized_docs = tokenize_docs(texts, vectorizer=vectorizer)
    dictionary = Dictionary(tokenized_docs)

    results = {}
    rows = []
    for k in k_range:
        res = evaluate_k(
            X,
            feature_names,
            tokenized_docs,
            dictionary,
            k,
            n_words=n_words,
            random_state=random_state,
        )
        results[k] = res
        rows.append(
            {
                "k": k,
                "iterations": res["iterations"],
                "reconstruction_error": res["reconstruction_error"],
                "coherence_cv": res["coherence_cv"],
                "diversity": res["diversity"],
                "redundancy": res["redundancy"],
            }
        )
        print(
            f"k={k:>3}  coherence_cv={res['coherence_cv']:.4f}  "
            f"diversity={res['diversity']:.3f}  redundancy={res['redundancy']:.3f}  "
            f"recon_err={res['reconstruction_error']:.4f}"
        )

    summary_df = pd.DataFrame(rows).sort_values("k").reset_index(drop=True)
    return summary_df, results


def pick_best_k(summary_df: pd.DataFrame) -> int:
    """Best k by coherence alone (matches the original notebook's selection rule)."""
    return int(summary_df.loc[summary_df["coherence_cv"].idxmax(), "k"])


# --------------------------------------------------------------------------
# 5. Trend analysis
# --------------------------------------------------------------------------


def assign_dominant_topic(W: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-publication dominant topic. Returns (topic_index_array, topic_weight_array)."""
    dominant = W.argmax(axis=1)
    weight = W.max(axis=1)
    return dominant, weight


def topic_trend_table(
    df: pd.DataFrame, dominant_topic: np.ndarray, year_col: str, topic_names: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Publication counts per topic per year, and the year-normalized share (each year sums to 1).
    Returns (counts_df, shares_df), both wide with years as rows and topic names as columns."""
    work = pd.DataFrame({year_col: df[year_col].values})
    work["topic_name"] = [topic_names[t] for t in dominant_topic]

    counts = work.groupby([year_col, "topic_name"]).size().unstack(fill_value=0)
    counts = counts.sort_index()
    shares = counts.div(counts.sum(axis=1), axis=0)
    return counts, shares


# --------------------------------------------------------------------------
# End-to-end pipeline for one final k (used by the CLI script)
# --------------------------------------------------------------------------


def run_final_pipeline(
    df: pd.DataFrame,
    k: int,
    output_dir: Path,
    text_columns=TEXT_COLUMNS,
    n_words: int = 15,
    naming_words: int = 3,
    year_col: Optional[str] = None,
    tfidf_kwargs: Optional[dict] = None,
    random_state: int = 42,
    clean: bool = True,
) -> dict:
    """Fits NMF at a fixed k and writes every artifact to output_dir:
    - nmf_cleaning_report.csv             (rows affected by non-Latin/boilerplate cleaning)
    - nmf_topic_keywords.csv
    - nmf_topic_annotation_template.csv   (fill this in by hand)
    - nmf_publication_topics.csv          (df + dominant_topic + topic_name + weight)
    - nmf_topic_trend_counts.csv / nmf_topic_trend_shares.csv  (only if a year column is found)

    clean=True (default) applies the text-cleaning step in combined_text() -
    see its docstring. Pass clean=False to reproduce the original baseline.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Document what the cleaning step touches, computed over the FULL raw corpus
    # (not filtered by has_text below) so rows that clean down to empty - e.g. a
    # purely Tamil title/abstract - still get counted rather than silently
    # disappearing from their own report.
    raw_texts = combined_text(df, text_columns, clean=False)
    report = cleaning_report(raw_texts)
    pd.DataFrame([report]).to_csv(output_dir / "nmf_cleaning_report.csv", index=False)
    print(
        f"Cleaning report: {report['rows_with_non_latin_chars']} of {report['n_rows']} rows "
        f"had non-Latin chars, {report['rows_with_boilerplate_phrases']} rows had "
        f"boilerplate phrases. clean={clean}"
    )

    texts = combined_text(df, text_columns, clean=clean)
    has_text = texts.str.len() > 0
    if has_text.sum() == 0:
        raise ValueError(
            "No non-empty text rows found — check text_columns / input data."
        )
    n_emptied_by_cleaning = int(((raw_texts.str.len() > 0) & ~has_text).sum())
    if n_emptied_by_cleaning:
        print(
            f"{n_emptied_by_cleaning} rows had text before cleaning but are empty "
            f"after it (e.g. a title/abstract that was entirely Tamil/boilerplate) "
            f"and are excluded from the NMF fit."
        )

    vectorizer, X = build_tfidf(texts[has_text], **(tfidf_kwargs or {}))
    feature_names = vectorizer.get_feature_names_out()

    model, W = fit_nmf(X, k, random_state=random_state)
    topic_words = get_topic_keywords(model, feature_names, n_words=n_words)
    topic_names = name_topics(topic_words, n=naming_words)

    # coherence / diversity / redundancy for the record.
    # FIX: pass `vectorizer` so n-gram topic words (ngram_range=(1, 3)) are
    # tokenized the same way for the coherence dictionary — see
    # tokenize_docs() docstring.
    tokenized_docs = tokenize_docs(texts[has_text], vectorizer=vectorizer)
    dictionary = Dictionary(tokenized_docs) if _GENSIM_AVAILABLE else None
    coherence = (
        compute_coherence(topic_words, tokenized_docs, dictionary)
        if _GENSIM_AVAILABLE
        else None
    )
    diversity = compute_topic_diversity(topic_words, top_n=n_words)
    redundancy = compute_pairwise_redundancy(topic_words, top_n=n_words)

    keywords_df = pd.DataFrame(
        {
            "topic_id": range(1, k + 1),
            "topic_name": topic_names,
            "top_words": [", ".join(w) for w in topic_words],
        }
    )
    keywords_df.to_csv(output_dir / "nmf_topic_keywords.csv", index=False)

    annotation_df = build_annotation_template(topic_words, topic_names, n_words=n_words)
    annotation_df.to_csv(output_dir / "nmf_topic_annotation_template.csv", index=False)

    dominant, weight = assign_dominant_topic(W)
    pub_topics = df.loc[has_text].copy()
    pub_topics["nmf_topic_id"] = dominant + 1
    pub_topics["nmf_topic_name"] = [topic_names[t] for t in dominant]
    pub_topics["nmf_topic_weight"] = weight
    pub_topics.to_csv(output_dir / "nmf_publication_topics.csv", index=False)

    trend_info = None
    resolved_year_col = year_col or find_year_column(pub_topics)
    if resolved_year_col:
        counts, shares = topic_trend_table(
            pub_topics, dominant, resolved_year_col, topic_names
        )
        counts.to_csv(output_dir / "nmf_topic_trend_counts.csv")
        shares.to_csv(output_dir / "nmf_topic_trend_shares.csv")
        trend_info = {"year_col": resolved_year_col, "counts": counts, "shares": shares}
    else:
        print(
            "No year column found (looked for publication_year/year/pub_year/date) — "
            "skipping trend analysis. Pass year_col= explicitly if your column is named differently."
        )

    print(
        f"\nk={k}  coherence_cv={coherence}  diversity={diversity:.3f}  redundancy={redundancy:.3f}"
    )
    print(f"Artifacts written to: {output_dir}")

    return {
        "vectorizer": vectorizer,
        "model": model,
        "W": W,
        "topic_words": topic_words,
        "topic_names": topic_names,
        "coherence_cv": coherence,
        "diversity": diversity,
        "redundancy": redundancy,
        "keywords_df": keywords_df,
        "annotation_df": annotation_df,
        "pub_topics": pub_topics,
        "trend": trend_info,
        "cleaning_report": report,
    }
