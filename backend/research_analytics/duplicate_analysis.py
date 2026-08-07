"""
Fuzzy title duplicate detection for publication metadata.

Features:
- DOI-aware duplicate resolution
- Fuzzy title similarity
- Author similarity
- Publication year agreement
- Threshold evaluation
- Deduplication with representative selection
- Ground truth evaluation support
"""

from __future__ import annotations

import os
import re
import unicodedata

from itertools import combinations
from collections import defaultdict

import numpy as np
import pandas as pd

from rapidfuzz.fuzz import ratio


# ==================================================
# Normalization
# ==================================================


def normalize_text(value):
    """
    Normalize text fields:
    - lowercase
    - remove accents
    - remove punctuation
    - normalize spaces
    """

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    text = unicodedata.normalize("NFKD", text)

    text = "".join(c for c in text if not unicodedata.combining(c))

    text = text.lower()

    text = re.sub(r"[^a-z0-9 ]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip() or None


def normalize_author(value):
    """
    Convert author string into token set.
    """

    text = normalize_text(value)

    if text is None:
        return set()

    return set(text.split())


def normalize_doi(value):
    """
    Normalize DOI.

    Examples:

    https://doi.org/10.xxxx/test
    doi:10.xxxx/test
    10.xxxx/test

    become:

    10.xxxx/test
    """

    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    if text in {"", "nan", "none", "null", "n/a", "na", "-"}:
        return None

    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)

    text = re.sub(r"^doi:\s*", "", text)

    text = text.strip().strip("/")

    return text if text else None


# ==================================================
# Feature Preparation
# ==================================================


def prepare_duplicate_features(df):

    df = df.copy()

    df["title_norm"] = df["title"].apply(normalize_text)

    df["author_tokens"] = df["authors"].apply(normalize_author)

    df["year_norm"] = pd.to_numeric(df["publication_year"], errors="coerce")

    if "doi" in df.columns:
        df["doi_norm"] = df["doi"].apply(normalize_doi)

    else:
        df["doi_norm"] = None

    return df


# ==================================================
# Blocking
# ==================================================


def create_title_blocks(df):
    """
    Blocking strategy:

    First two title words are used as block key.

    Example:

    "machine learning applications"
       |
       -> ("machine","learning")

    This reduces O(n²) comparisons.
    """

    blocks = defaultdict(list)

    for idx, title in df["title_norm"].items():
        if title is None:
            continue

        words = title.split()

        if not words:
            continue

        if len(words) >= 2:
            key = (words[0], words[1])

        else:
            key = (words[0],)

        blocks[key].append(idx)

    return blocks


def generate_candidate_pairs(df, max_block_size=100):
    """
    Generate possible duplicate pairs.

    Avoid huge comparisons caused by generic titles.
    """

    blocks = create_title_blocks(df)

    pairs = set()

    skipped_blocks = 0

    for members in blocks.values():
        if len(members) > max_block_size:
            skipped_blocks += 1

            continue

        for a, b in combinations(members, 2):
            pairs.add(tuple(sorted([a, b])))

    return pairs, skipped_blocks


# ==================================================
# Similarity Functions
# ==================================================


def author_similarity(authors_a, authors_b):
    """
    Jaccard similarity.
    """

    if not authors_a or not authors_b:
        return None

    intersection = len(authors_a.intersection(authors_b))

    union = len(authors_a.union(authors_b))

    return (intersection / union) * 100


def calculate_duplicate_score(title_score, author_score, year_score):
    """
    Weighted duplicate score.

    Title  : 60%
    Author : 30%
    Year   : 10%
    """

    if author_score is None:
        author_score = 0

    return round((title_score * 0.6 + author_score * 0.3 + year_score * 0.1), 2)


# ==================================================
# DOI Decision Logic
# ==================================================


def decide_doi_status(doi_1, doi_2):
    """
    Returns:

    same_doi
    different_doi
    one_missing
    both_missing
    """

    doi1_exists = doi_1 is not None

    doi2_exists = doi_2 is not None

    if doi1_exists and doi2_exists:
        if doi_1 == doi_2:
            return "same_doi"

        else:
            return "different_doi"

    if doi1_exists or doi2_exists:
        return "one_missing"

    return "both_missing"


def fields_effectively_identical(
    r1, r2, title_score, author_score, title_floor=97, author_floor=90
):
    """
    Used when only one DOI exists.

    Require almost exact metadata match.
    """

    if title_score < title_floor:
        return False

    if r1["author_tokens"] and r2["author_tokens"]:
        if author_score is None or author_score < author_floor:
            return False

    if pd.notna(r1["year_norm"]) and pd.notna(r2["year_norm"]):
        if r1["year_norm"] != r2["year_norm"]:
            return False

    return True

# ==================================================
# Fuzzy Matching
# ==================================================


def fuzzy_title_matching(df, similarity_threshold=90):

    results = []

    pairs, skipped_blocks = generate_candidate_pairs(df)

    for left, right in pairs:
        r1 = df.loc[left]

        r2 = df.loc[right]
        title_score = ratio(r1["title_norm"] or "", r2["title_norm"] or "")


        author_score = author_similarity(r1["author_tokens"], r2["author_tokens"])

        # ------------------------------
        # Year similarity
        # ------------------------------

        if pd.notna(r1["year_norm"]) and pd.notna(r2["year_norm"]):
            diff = abs(r1["year_norm"] - r2["year_norm"])

            if diff == 0:
                year_score = 100

            elif diff == 1:
                year_score = 70

            else:
                year_score = 0

        else:
            year_score = 0

        combined_score = calculate_duplicate_score(
            title_score, author_score, year_score
        )

        doi_status = decide_doi_status(r1["doi_norm"], r2["doi_norm"])

        is_duplicate = False

        keep_id = None

        drop_id = None

        doi_decision = doi_status

        # ======================================
        # Rule 1:
        # Same DOI
        # ======================================

        if doi_status == "same_doi":
            is_duplicate = True

            doi_decision = "same_doi_merge"

            keep_id, drop_id = choose_best_record(r1, r2)

        # ======================================
        # Rule 2:
        # Different DOI
        # ======================================

        elif doi_status == "different_doi":
            is_duplicate = False

            doi_decision = "different_doi_keep_both"

        # ======================================
        # Rule 3:
        # One DOI missing
        # ======================================

        elif doi_status == "one_missing":
            if fields_effectively_identical(r1, r2, title_score, author_score):
                is_duplicate = True

                doi_decision = "fill_missing_doi_merge"

                keep_id, drop_id = choose_best_record(r1, r2)

            else:
                doi_decision = "one_missing_keep_both"

        # ======================================
        # Rule 4:
        # No DOI
        # ======================================

        else:
            if combined_score >= similarity_threshold:
                is_duplicate = True

                doi_decision = "no_doi_fuzzy_match"

                keep_id, drop_id = choose_best_record(r1, r2)

            else:
                doi_decision = "no_doi_below_threshold"

        # Save duplicates and DOI conflicts
        if is_duplicate or (
            doi_status == "different_doi" and combined_score >= similarity_threshold
        ):
            results.append(
                {
                    "record_1": r1["source_record_id"],
                    "record_2": r2["source_record_id"],
                    "title_1": r1["title"],
                    "title_2": r2["title"],
                    "title_similarity": round(title_score, 2),
                    "author_similarity": (
                        round(author_score, 2) if author_score is not None else 0
                    ),
                    "year_score": year_score,
                    "combined_duplicate_score": combined_score,
                    "doi_1": r1["doi"],
                    "doi_2": r2["doi"],
                    "doi_status": doi_status,
                    "doi_decision": doi_decision,
                    "is_duplicate": is_duplicate,
                    "keep_record_id": keep_id,
                    "drop_record_id": drop_id,
                }
            )

    columns = [
        "record_1",
        "record_2",
        "title_1",
        "title_2",
        "title_similarity",
        "author_similarity",
        "year_score",
        "combined_duplicate_score",
        "doi_1",
        "doi_2",
        "doi_status",
        "doi_decision",
        "is_duplicate",
        "keep_record_id",
        "drop_record_id",
    ]

    return (pd.DataFrame(results, columns=columns), skipped_blocks)


# ==================================================
# Representative Selection
# ==================================================


def completeness_score(row):

    cols = ["title", "authors", "abstract", "journal", "publisher", "doi"]

    return row[cols].notna().sum()


def choose_best_record(r1, r2):
    """
    Select record to keep.

    Priority:

    1. DOI exists
    2. More complete metadata
    3. First record
    """

    doi1 = r1["doi_norm"] is not None

    doi2 = r2["doi_norm"] is not None

    if doi1 and not doi2:
        return (r1["source_record_id"], r2["source_record_id"])

    if doi2 and not doi1:
        return (r2["source_record_id"], r1["source_record_id"])

    c1 = completeness_score(r1)

    c2 = completeness_score(r2)

    if c1 >= c2:
        return (r1["source_record_id"], r2["source_record_id"])

    return (r2["source_record_id"], r1["source_record_id"])


# ==================================================
# Threshold Evaluation
# ==================================================


def evaluate_thresholds(df, thresholds=[90, 92, 95, 97, 99]):

    rows = []

    for threshold in thresholds:
        matches, _ = fuzzy_title_matching(df, threshold)

        rows.append(
            {
                "threshold": threshold,
                "duplicates": int(matches["is_duplicate"].sum()) if len(matches) else 0,
                "same_doi_merges": int(
                    (matches["doi_decision"] == "same_doi_merge").sum()
                )
                if len(matches)
                else 0,
                "one_doi_merges": int(
                    (matches["doi_decision"] == "fill_missing_doi_merge").sum()
                )
                if len(matches)
                else 0,
                "different_doi_cases": int(
                    (matches["doi_decision"] == "different_doi_keep_both").sum()
                )
                if len(matches)
                else 0,
            }
        )

    return pd.DataFrame(rows)


# ==================================================
# Apply Deduplication
# ==================================================


def apply_deduplication(df, matches):

    parent = {rid: rid for rid in df["source_record_id"]}

    def find(x):

        while parent[x] != x:
            parent[x] = parent[parent[x]]

            x = parent[x]

        return x

    def union(a, b):

        ra = find(a)

        rb = find(b)

        if ra != rb:
            parent[rb] = ra

    for _, row in matches[matches["is_duplicate"]].iterrows():
        union(row["keep_record_id"], row["drop_record_id"])

    df = df.copy()

    df["duplicate_group"] = df["source_record_id"].apply(find)

    representatives = []

    for _, group in df.groupby("duplicate_group"):
        best = group.iloc[group.apply(completeness_score, axis=1).idxmax()]

        representatives.append(best["source_record_id"])

    df["keep"] = df["source_record_id"].isin(representatives)

    deduplicated = df[df["keep"]].drop(columns=["duplicate_group", "keep"])

    removed = df[~df["keep"]]

    return deduplicated, removed


# ==================================================
# Ground Truth Sample Generation
# ==================================================


def generate_duplicate_evaluation_samples(df, output_file, max_samples=200):
    """
    Generate probable duplicate samples.

    Label:
        1 = duplicate

    Sources:
    - Same DOI
    - Very high title similarity
    - High author similarity
    """

    samples = []

    pairs, _ = generate_candidate_pairs(df)

    for left, right in pairs:
        r1 = df.loc[left]
        r2 = df.loc[right]

        title_score = ratio(r1["title_norm"] or "", r2["title_norm"] or "")

        author_score = author_similarity(r1["author_tokens"], r2["author_tokens"])

        doi_status = decide_doi_status(r1["doi_norm"], r2["doi_norm"])

        if doi_status == "same_doi" or (
            title_score >= 95 and (author_score is None or author_score >= 80)
        ):
            samples.append(
                {
                    "record_1": r1["source_record_id"],
                    "record_2": r2["source_record_id"],
                    "title_1": r1["title"],
                    "title_2": r2["title"],
                    "doi_1": r1["doi"],
                    "doi_2": r2["doi"],
                    "title_similarity": round(title_score, 2),
                    "author_similarity": round(author_score, 2)
                    if author_score is not None
                    else 0,
                    "label": 1,
                }
            )

        if len(samples) >= max_samples:
            break

    result = pd.DataFrame(samples)

    result.to_csv(output_file, index=False)

    return result


def generate_non_duplicate_evaluation_samples(df, output_file, max_samples=200):
    """
    Generate hard negative samples.

    Label:
        0 = not duplicate

    Examples:
    - Similar titles
    - Different DOI
    """

    samples = []

    pairs, _ = generate_candidate_pairs(df)

    for left, right in pairs:
        r1 = df.loc[left]
        r2 = df.loc[right]

        title_score = ratio(r1["title_norm"] or "", r2["title_norm"] or "")

        doi_status = decide_doi_status(r1["doi_norm"], r2["doi_norm"])

        if doi_status == "different_doi" and title_score >= 80:
            samples.append(
                {
                    "record_1": r1["source_record_id"],
                    "record_2": r2["source_record_id"],
                    "title_1": r1["title"],
                    "title_2": r2["title"],
                    "doi_1": r1["doi"],
                    "doi_2": r2["doi"],
                    "title_similarity": round(title_score, 2),
                    "label": 0,
                }
            )

        if len(samples) >= max_samples:
            break

    result = pd.DataFrame(samples)

    result.to_csv(output_file, index=False)

    return result


# ==================================================
# Evaluation
# ==================================================


def evaluate_against_ground_truth(predictions, ground_truth_file, output_file):

    truth = pd.read_csv(ground_truth_file)

    predicted_pairs = set()

    for _, row in predictions.iterrows():
        if bool(row["is_duplicate"]):
            pair = tuple(sorted([row["record_1"], row["record_2"]]))

            predicted_pairs.add(pair)

    y_true = []
    y_pred = []

    for _, row in truth.iterrows():
        pair = tuple(sorted([row["record_1"], row["record_2"]]))

        y_true.append(row["label"])

        y_pred.append(1 if pair in predicted_pairs else 0)

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    tp = np.sum((y_true == 1) & (y_pred == 1))

    fp = np.sum((y_true == 0) & (y_pred == 1))

    fn = np.sum((y_true == 1) & (y_pred == 0))

    tn = np.sum((y_true == 0) & (y_pred == 0))

    precision = tp / (tp + fp) if tp + fp else 0

    recall = tp / (tp + fn) if tp + fn else 0

    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    accuracy = (tp + tn) / (tp + tn + fp + fn) if tp + tn + fp + fn else 0

    report = pd.DataFrame(
        [
            {
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "true_negative": tn,
            }
        ]
    )

    report.to_csv(output_file, index=False)

    return report

# ==================================================
# Main Pipeline
# ==================================================


def run_fuzzy_duplicate_analysis(input_file, output_dir, similarity_threshold=90):

    os.makedirs(output_dir, exist_ok=True)

    print("\nLoading dataset...")

    df = pd.read_csv(input_file)

    required_cols = {"title", "authors", "publication_year", "source_record_id", "doi"}

    missing = required_cols - set(df.columns)

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    print(f"Original records: {len(df)}")

    # ==================================================
    # Feature preparation
    # ==================================================

    print("\nPreparing duplicate features...")

    df = prepare_duplicate_features(df)

    # ==================================================
    # Duplicate detection
    # ==================================================

    print("\nRunning fuzzy duplicate detection...")

    matches, skipped_blocks = fuzzy_title_matching(df, similarity_threshold)

    if skipped_blocks:
        print(f"Skipped blocks: {skipped_blocks}")

    # ==================================================
    # Threshold analysis
    # ==================================================

    print("\nEvaluating thresholds...")

    threshold_results = evaluate_thresholds(df)

    # ==================================================
    # Deduplication
    # ==================================================

    print("\nApplying deduplication...")

    deduplicated, removed = apply_deduplication(df, matches)

    # ==================================================
    # Ground truth generation
    # ==================================================

    print("\nGenerating evaluation samples...")

    duplicate_samples = generate_duplicate_evaluation_samples(
        df, os.path.join(output_dir, "duplicate_validation_samples.csv")
    )

    non_duplicate_samples = generate_non_duplicate_evaluation_samples(
        df, os.path.join(output_dir, "non_duplicate_validation_samples.csv")
    )

    if len(duplicate_samples) > 0 and len(non_duplicate_samples) > 0:
        ground_truth = pd.concat(
            [duplicate_samples, non_duplicate_samples], ignore_index=True
        )

        ground_truth_file = os.path.join(output_dir, "ground_truth.csv")

        ground_truth.to_csv(ground_truth_file, index=False)

        print("\nRunning evaluation...")

        evaluation = evaluate_against_ground_truth(
            matches,
            ground_truth_file,
            os.path.join(output_dir, "evaluation_report.csv"),
        )

        print(evaluation)

    else:
        print("Not enough samples for evaluation")

    # ==================================================
    # Save outputs
    # ==================================================

    print("\nSaving outputs...")

    matches.to_csv(
        os.path.join(output_dir, "fuzzy_duplicate_candidates.csv"), index=False
    )

    threshold_results.to_csv(
        os.path.join(output_dir, "threshold_evaluation.csv"), index=False
    )

    deduplicated.to_csv(
        os.path.join(output_dir, "deduplicated_records.csv"), index=False
    )

    removed.to_csv(
        os.path.join(output_dir, "removed_duplicate_records.csv"), index=False
    )

    # ==================================================
    # Summary
    # ==================================================

    print("\n======================================")
    print("Duplicate Analysis Summary")
    print("======================================")

    print(f"Original records        : {len(df)}")

    print(
        f"Duplicate pairs found   : "
        f"{matches['is_duplicate'].sum() if len(matches) else 0}"
    )

    print(f"Records after cleaning  : {len(deduplicated)}")

    print(f"Removed duplicates      : {len(removed)}")

    print("======================================")

    return (matches, threshold_results, deduplicated, removed)


# ==================================================
# Command Line Execution
# ==================================================


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage:")

        print("python fuzzy_duplicate_pipeline.py <input_csv> <output_dir>")

        sys.exit(1)

    input_csv = sys.argv[1]

    output_dir = sys.argv[2]

    run_fuzzy_duplicate_analysis(input_csv, output_dir)