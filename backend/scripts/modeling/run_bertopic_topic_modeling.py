"""
Production entry point for the semantic (BERTopic) topic-modelling step.

Embeds every paper with a sentence transformer, clusters the embeddings into
topics, and writes keyword / assignment / per-year trend artifacts that mirror
the NMF ones (see src/modeling/bertopic_topic_modeling.py for the why).

Two modes, like run_nmf_topic_modeling.py:
  1. Sweep mode (no --n-topics): fits k in --k-range, picks the best by
     NPMI coherence x diversity, then fits the final model.
  2. Fixed mode (--n-topics given): fits directly at that k.

--compare-nmf also fits NMF on the same documents at the chosen k and writes
topic_model_comparison.csv, scored with the same metrics.

Embeddings are cached in <output-dir>/cache, so re-runs only pay for UMAP +
clustering (seconds), not for encoding the corpus again.

Requires the topic-modeling extra:  pip install -e ".[topic-modeling]"

Usage (from backend/):
    python scripts/modeling/run_bertopic_topic_modeling.py \
        --data Data/processed/common/common_publications_final_2016_2026_ai_only_all_review_binary_resolved.csv \
        --output-dir Data/processed/common/bertopic \
        --compare-nmf
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.modeling.bertopic_topic_modeling import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_N_WORDS,
    EMBEDDING_TEXT_COLUMNS,
    YEAR_COLUMN,
    CoherenceReference,
    TopicModelConfig,
    add_publication_year,
    build_documents,
    compare_with_nmf,
    encode_documents,
    load_embedding_model,
    pick_best_k,
    run_final_pipeline,
    sweep_n_topics,
)
from src.pipeline.accepted_snapshot import validate_accepted_snapshot_frame  # noqa: E402

DEFAULT_K_RANGE = [10, 15, 20, 25, 30]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fit / evaluate the BERTopic model for ResearchLanka.")
    p.add_argument("--data", required=True, help="Path to the publications CSV.")
    p.add_argument("--output-dir", required=True, help="Directory to write all BERTopic artifacts to.")
    p.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"sentence-transformers model name or path (default: {DEFAULT_EMBEDDING_MODEL}).",
    )
    p.add_argument(
        "--clustering",
        choices=["kmeans", "hdbscan"],
        default="kmeans",
        help="kmeans fixes the topic count; hdbscan lets density decide (default: kmeans).",
    )
    p.add_argument(
        "--n-topics",
        type=int,
        default=None,
        help="Fixed number of topics (kmeans). Omit to sweep --k-range instead.",
    )
    p.add_argument(
        "--k-range",
        type=int,
        nargs="+",
        default=DEFAULT_K_RANGE,
        help=f"Topic counts to sweep when --n-topics is not given (default: {DEFAULT_K_RANGE}).",
    )
    p.add_argument(
        "--min-cluster-size",
        type=int,
        default=20,
        help="Smallest topic HDBSCAN may form (hdbscan only, default: 20).",
    )
    p.add_argument("--n-words", type=int, default=DEFAULT_N_WORDS, help="Top words per topic.")
    p.add_argument(
        "--mmr-diversity",
        type=float,
        default=0.3,
        help="MMR keyword diversity in [0, 1]; pass a negative value to keep plain c-TF-IDF words.",
    )
    p.add_argument(
        "--text-columns",
        nargs="+",
        default=list(EMBEDDING_TEXT_COLUMNS),
        help=f"Columns joined into each document (default: {list(EMBEDDING_TEXT_COLUMNS)}).",
    )
    p.add_argument("--device", default=None, help="Torch device for encoding, e.g. cuda or cpu.")
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--compare-nmf", action="store_true", help="Also fit NMF on the same docs and compare.")
    p.add_argument("--save-model", action="store_true", help="Save the fitted BERTopic model to <output-dir>/model.")
    p.add_argument("--no-html", action="store_true", help="Skip the interactive plotly HTML files.")
    p.add_argument(
        "--allow-non-accepted-input",
        action="store_true",
        help="Development-only: allow a broad/non-accepted corpus.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    print(f"Loading {args.data} ...")
    df = pd.read_csv(args.data, low_memory=False)
    if not args.allow_non_accepted_input:
        validate_accepted_snapshot_frame(df, source=args.data)
    df = add_publication_year(df)
    print(f"Shape: {df.shape}  ({df[YEAR_COLUMN].isna().sum()} rows without a year)")

    docs = build_documents(df, args.text_columns)
    has_text = docs.str.len() > 0
    if not has_text.all():
        print(f"Dropping {int((~has_text).sum())} rows with no text after cleaning.")
    df = df.loc[has_text].reset_index(drop=True)
    docs = docs[has_text].reset_index(drop=True)

    embedding_model = load_embedding_model(args.embedding_model, device=args.device)
    embeddings = encode_documents(
        docs.tolist(),
        model_name=args.embedding_model,
        cache_dir=output_dir / "cache",
        embedding_model=embedding_model,
    )
    reference = CoherenceReference(docs)

    base_config = TopicModelConfig(
        clustering=args.clustering,
        min_cluster_size=args.min_cluster_size,
        n_words=args.n_words,
        mmr_diversity=args.mmr_diversity if args.mmr_diversity >= 0 else None,
        random_state=args.random_state,
    )

    k = args.n_topics
    if args.clustering == "kmeans" and k is None:
        print(f"\nNo --n-topics given, sweeping k in {args.k_range} ...")
        summary = sweep_n_topics(
            docs.tolist(), embeddings, args.k_range, base_config, embedding_model, reference
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        summary.to_csv(output_dir / "bertopic_k_sweep_evaluation.csv", index=False)
        k = pick_best_k(summary)
        print(f"\nBest k by NPMI x diversity: {k}")
    config = replace(base_config, n_topics=k or base_config.n_topics)

    result = run_final_pipeline(
        df=df,
        output_dir=output_dir,
        config=config,
        embeddings=embeddings,
        docs=docs,
        embedding_model=embedding_model,
        embedding_model_name=args.embedding_model,
        reference=reference,
        save_model=args.save_model,
        write_html=not args.no_html,
    )

    if args.compare_nmf:
        comparison = compare_with_nmf(
            docs,
            embeddings,
            result["topic_terms"],
            result["labels"],
            k=len(result["topic_words"]),
            reference=reference,
            n_words=args.n_words,
            random_state=args.random_state,
        )
        comparison.to_csv(output_dir / "topic_model_comparison.csv", index=False)
        print("\nNMF vs BERTopic on the same documents:")
        print(comparison.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
