"""
Production entry point for the NMF topic-modelling step.

Two modes:
  1. Sweep mode (no --k given): re-runs the k-search over --k-range, picks the best k by
     coherence, then fits the final model and writes all artifacts. Use this the first time,
     or whenever you re-run after changing the data / text columns.
  2. Fixed mode (--k given): skips the sweep and fits directly at that k. Use this day-to-day
     once you've settled on a k from the test notebook / a previous sweep.

Text is cleaned by default (Tamil/Sinhala-script stripping + metadata-boilerplate
stripping + expanded stopwords - see src/modeling/text_cleaning.py). Pass --no-clean
to reproduce the original uncleaned baseline, e.g. to compare coherence/diversity
before and after.

FIX: the sweep branch now passes the fitted `vectorizer` into evaluate_k_range()
so coherence scoring tokenizes with the same n-gram analyzer used to build the
topic-word vocabulary (see nmf_topic_modeling.py's tokenize_docs() docstring).
Previously this branch built the vectorizer but never passed it through, so the
k-sweep's coherence numbers were computed against a mismatched, single-word
tokenization while run_final_pipeline()'s fixed-k coherence was fine.

Usage:
    python scripts/run_nmf_pipeline.py \
        --data ../data/processed/common/common_publications_final_with_linearsvm.csv \
        --output-dir ../data/processed/common/nmf \
        --k 20

    # or let it sweep and choose:
    python scripts/run_nmf_pipeline.py \
        --data ../data/processed/common/common_publications_final_with_linearsvm.csv \
        --output-dir ../data/processed/common/nmf

    # compare against the uncleaned baseline:
    python scripts/run_nmf_pipeline.py \
        --data ../data/processed/common/common_publications_final_with_linearsvm.csv \
        --output-dir ../data/processed/common/nmf_uncleaned \
        --no-clean
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# backend/scripts/run_nmf_pipeline.py -> parent.parent is backend itself.
# sys.path needs backend (NOT backend/src), since the imports below carry the
# "src." prefix - this mirrors the same fix needed in the test notebook.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.modeling.nmf_topic_modeling import (  # noqa: E402
    TEXT_COLUMNS,
    build_tfidf,
    combined_text,
    evaluate_k_range,
    pick_best_k,
    run_final_pipeline,
)
from src.preprocessing.text_cleaning import cleaning_report  # noqa: E402

# Reasonable starting default — matches the middle of the range tested in the original
# notebook ([5, 10, 15, 20, 25, 30]). Swap this once your test notebook gives you a
# coherence-backed best_k for the real dataset.
DEFAULT_K = 20
DEFAULT_K_RANGE = [5, 10, 15, 20, 25, 30]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fit / evaluate the NMF topic model for ResearchLanka."
    )
    p.add_argument("--data", required=True, help="Path to the publications CSV.")
    p.add_argument(
        "--output-dir", required=True, help="Directory to write all NMF artifacts to."
    )
    p.add_argument(
        "--k",
        type=int,
        default=None,
        help="Fixed number of topics. Omit to sweep --k-range instead.",
    )
    p.add_argument(
        "--k-range",
        type=int,
        nargs="+",
        default=DEFAULT_K_RANGE,
        help=f"Values of k to sweep when --k is not given (default: {DEFAULT_K_RANGE}).",
    )
    p.add_argument(
        "--n-words",
        type=int,
        default=15,
        help="Top words per topic to keep (default: 15).",
    )
    p.add_argument(
        "--naming-words",
        type=int,
        default=3,
        help="Words used to auto-name each topic (default: 3).",
    )
    p.add_argument(
        "--year-col",
        default=None,
        help="Year column for trend analysis (auto-detected if omitted).",
    )
    p.add_argument(
        "--text-columns",
        nargs="+",
        default=TEXT_COLUMNS,
        help=f"Columns concatenated into the NMF document text (default: {TEXT_COLUMNS}).",
    )
    p.add_argument(
        "--no-clean",
        action="store_true",
        help=(
            "Skip Tamil/Sinhala-script stripping and metadata-boilerplate stripping "
            "(reproduces the original uncleaned baseline, e.g. for comparison)."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    clean = not args.no_clean

    print(f"Loading {args.data} ...")
    df = pd.read_csv(args.data, low_memory=False)
    print(f"Shape: {df.shape}")

    raw_texts = combined_text(df, args.text_columns, clean=False)
    report = cleaning_report(raw_texts)
    print(
        f"\nCleaning check: {report['rows_with_non_latin_chars']} of {report['n_rows']} rows "
        f"contain Tamil/Sinhala-script characters; "
        f"{report['rows_with_boilerplate_phrases']} rows contain metadata-boilerplate phrases "
        f"(abstract available / editorial / etc.)."
    )
    print(
        f"clean={clean} — {'stripping' if clean else 'KEEPING'} these at the token/phrase level "
        f"(rows are never dropped)."
    )

    output_dir = Path(args.output_dir)

    k = args.k
    if k is None:
        print(f"\nNo --k given, sweeping k in {args.k_range} ...")
        texts = combined_text(df, args.text_columns, clean=clean)
        has_text = texts.str.len() > 0
        vectorizer, X = build_tfidf(texts[has_text])
        feature_names = vectorizer.get_feature_names_out()

        # FIX: pass vectorizer=vectorizer through so coherence tokenization
        # during the sweep matches the n-gram vocabulary the topics come
        # from (see nmf_topic_modeling.tokenize_docs()).
        summary_df, _ = evaluate_k_range(
            X,
            feature_names,
            texts[has_text],
            args.k_range,
            vectorizer=vectorizer,
            n_words=args.n_words,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(output_dir / "nmf_k_sweep_evaluation.csv", index=False)

        k = pick_best_k(summary_df)
        print(f"\nBest k by coherence: {k}")
    else:
        print(f"\nUsing fixed k={k}")

    run_final_pipeline(
        df=df,
        k=k,
        output_dir=output_dir,
        text_columns=args.text_columns,
        n_words=args.n_words,
        naming_words=args.naming_words,
        year_col=args.year_col,
        clean=clean,
    )


if __name__ == "__main__":
    main()



# cd researchlanka-ai/backend
# python scripts/run_nmf_pipeline.py \
#   --data data/processed/common/common_publications_final_with_linearsvm.csv \
#   --output-dir data/processed/common/nmf \
#   --k 20