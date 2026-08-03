"""
Fuzzy title duplicate detection for publication metadata.

Uses:
- title similarity
- publication year agreement
- author similarity
- DOI agreement (authoritative signal, overrides fuzzy score)

DOI decision rules (in priority order):
1. Both DOIs present & EQUAL         -> always a duplicate (merge), regardless of fuzzy score.
2. Both DOIs present & DIFFERENT     -> never a duplicate, regardless of fuzzy score.
   (Different DOIs = different works, even if titles/authors look alike.)
3. DOI present on exactly one record -> only a duplicate if title, authors, and year
   are all (near) identical on the fields that ARE comparable. If so, merge and
   keep the record that HAS the DOI, drop the one without.
4. Both DOIs missing                 -> fall back to pure fuzzy title/author/year
   similarity_threshold as before.

Produces:
1. Candidate duplicate pairs (with a doi_decision + is_duplicate flag)
2. Combined duplicate score
3. Threshold evaluation
4. A deduplicated dataset (records to keep) based on the above rules
"""

from __future__ import annotations

import re
import unicodedata
from itertools import combinations
from collections import defaultdict

import pandas as pd
import numpy as np

from rapidfuzz.fuzz import ratio


# --------------------------------------------------
# Normalization
# --------------------------------------------------


def normalize_text(value):

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

    text = text.strip()

    return text if text else None


def normalize_author(value):

    text = normalize_text(value)

    if text is None:
        return set()

    tokens = set(text.split())

    return tokens


def normalize_doi(value):
    """
    Normalize a DOI for comparison:
    - lowercase
    - strip whitespace
    - strip common URL prefixes (https://doi.org/, http://dx.doi.org/, doi:, etc.)
    - treat blank/NaN/placeholder strings as missing (None)
    """

    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    if not text or text in {"nan", "none", "null", "n/a", "na", "-"}:
        return None

    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    text = text.strip().strip("/")

    return text if text else None


# --------------------------------------------------
# Load and prepare
# --------------------------------------------------


def prepare_duplicate_features(df):

    df = df.copy()

    df["title_norm"] = df["title"].apply(normalize_text)

    df["author_tokens"] = df["authors"].apply(normalize_author)

    df["year_norm"] = pd.to_numeric(df["publication_year"], errors="coerce")

    if "doi" in df.columns:
        df["doi_norm"] = df["doi"].apply(normalize_doi)
        # apply() can leave real missing values as NaN (float) rather than None
        # in some pandas edge cases; normalize explicitly so downstream
        # "is not None" checks are reliable.
        df["doi_norm"] = df["doi_norm"].where(df["doi_norm"].notna(), None)
    else:
        df["doi_norm"] = None

    return df


# --------------------------------------------------
# Blocking
# --------------------------------------------------


def create_title_blocks(df):
    """
    Block records by the first two normalized title tokens (or the first
    token if the title is a single word). Records with no usable title
    are skipped entirely -- they cannot be blocked or fuzzy-compared, and
    are handled separately (see records_without_title in the pipeline).
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


# --------------------------------------------------
# Author similarity
# --------------------------------------------------


def author_similarity(a, b):

    if not a or not b:
        return 0

    intersection = len(a.intersection(b))

    union = len(a.union(b))

    return (intersection / union) * 100


# --------------------------------------------------
# Combined duplicate score
# --------------------------------------------------


def calculate_duplicate_score(title_score, author_score, year_score):
    """
    Weight:

    Title      60%
    Authors    30%
    Year       10%

    """

    return round((title_score * 0.6 + author_score * 0.3 + year_score * 0.1), 2)


# --------------------------------------------------
# Candidate generation
# --------------------------------------------------


def generate_candidate_pairs(df, max_block_size=100):
    """
    NOTE: blocks larger than max_block_size are skipped as O(n^2) blow-ups
    (e.g. generic/blank-ish titles colliding into one bucket). This means
    pairs inside oversized blocks are NOT evaluated. If your dataset has
    many near-duplicate generic titles, raise max_block_size deliberately
    (with awareness of the runtime cost) rather than silently trusting
    full coverage.
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


# --------------------------------------------------
# DOI-aware duplicate decision
# --------------------------------------------------


def decide_doi_status(doi_1, doi_2):
    """
    Returns one of:
    - "same_doi"        both present and equal
    - "different_doi"   both present and different
    - "one_missing"     exactly one present
    - "both_missing"    neither present
    """

    # Defensive: treat NaN (float) the same as None, in case a value slips
    # through prepare_duplicate_features as a raw float NaN rather than None.
    present_1 = doi_1 is not None and not (isinstance(doi_1, float) and pd.isna(doi_1))
    present_2 = doi_2 is not None and not (isinstance(doi_2, float) and pd.isna(doi_2))

    if present_1 and present_2:
        return "same_doi" if doi_1 == doi_2 else "different_doi"

    if present_1 or present_2:
        return "one_missing"

    return "both_missing"


def fields_effectively_identical(
    r1,
    r2,
    title_score,
    author_score,
    year_score,
    title_floor=97,
    author_floor=90,
    require_year_match=True,
):
    """
    Used only for the 'one DOI missing' case: decides whether the two
    records are close enough on every comparable field to justify treating
    a missing DOI as "the same record, just missing metadata" rather than
    a coincidentally similar title.

    - Title must be near-exact (>= title_floor).
    - If BOTH have authors listed, author overlap must be high (>= author_floor).
      If one/both have no author tokens at all, we don't penalize on authors,
      since that's a missing-data situation, not a mismatch.
    - If BOTH have a year, years must match exactly (unless require_year_match=False).
      If either year is missing, we don't require agreement (missing data,
      not a mismatch) -- but we also don't reward it; it's neutral.
    """

    if title_score < title_floor:
        return False

    both_have_authors = bool(r1["author_tokens"]) and bool(r2["author_tokens"])
    if both_have_authors and author_score < author_floor:
        return False

    both_have_year = pd.notna(r1["year_norm"]) and pd.notna(r2["year_norm"])
    if both_have_year and require_year_match:
        if r1["year_norm"] != r2["year_norm"]:
            return False

    return True


# --------------------------------------------------
# Fuzzy matching (DOI-aware)
# --------------------------------------------------


def fuzzy_title_matching(df, similarity_threshold=90):

    results = []

    pairs, skipped_blocks = generate_candidate_pairs(df)

    for left, right in pairs:
        r1 = df.loc[left]
        r2 = df.loc[right]

        title_score = ratio(r1["title_norm"], r2["title_norm"])

        author_score = author_similarity(r1["author_tokens"], r2["author_tokens"])

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

        final_score = calculate_duplicate_score(title_score, author_score, year_score)

        doi_1 = r1.get("doi_norm")
        doi_2 = r2.get("doi_norm")
        doi_status = decide_doi_status(doi_1, doi_2)

        is_duplicate = False
        keep_record_id = None
        drop_record_id = None
        doi_decision = doi_status

        if doi_status == "same_doi":
            # Rule 1: identical DOI is always a duplicate, fuzzy score irrelevant.
            is_duplicate = True
            # Prefer the record with more complete data if we must pick one to keep;
            # default to record_1, downstream merge logic can refine this.
            keep_record_id = r1["source_record_id"]
            drop_record_id = r2["source_record_id"]
            doi_decision = "same_doi_merge"

        elif doi_status == "different_doi":
            # Rule 2: different DOIs -> never merge, no matter how similar titles look.
            is_duplicate = False
            doi_decision = "different_doi_keep_both"

        elif doi_status == "one_missing":
            # Rule 3: only merge if every comparable field is effectively identical.
            if fields_effectively_identical(
                r1, r2, title_score, author_score, year_score
            ):
                is_duplicate = True
                doi_1_present = doi_1 is not None and not (
                    isinstance(doi_1, float) and pd.isna(doi_1)
                )
                if doi_1_present:
                    keep_record_id = r1["source_record_id"]
                    drop_record_id = r2["source_record_id"]
                else:
                    keep_record_id = r2["source_record_id"]
                    drop_record_id = r1["source_record_id"]
                doi_decision = "fill_missing_doi_merge"
            else:
                is_duplicate = False
                doi_decision = "one_missing_not_identical_keep_both"

        else:  # both_missing
            # Rule 4: fall back to pure fuzzy threshold.
            if final_score >= similarity_threshold:
                is_duplicate = True
                keep_record_id = r1["source_record_id"]
                drop_record_id = r2["source_record_id"]
                doi_decision = "no_doi_fuzzy_match"
            else:
                is_duplicate = False
                doi_decision = "no_doi_below_threshold"

        # Only emit rows that are either flagged duplicates OR were forced-different
        # despite a high fuzzy score (useful for auditing near-miss title collisions).
        should_report = is_duplicate or (
            doi_status == "different_doi" and final_score >= similarity_threshold
        )

        if should_report:
            results.append(
                {
                    "record_1": r1["source_record_id"],
                    "record_2": r2["source_record_id"],
                    "title_1": r1["title"],
                    "title_2": r2["title"],
                    "title_similarity": round(title_score, 2),
                    "author_similarity": round(author_score, 2),
                    "year_score": year_score,
                    "combined_duplicate_score": final_score,
                    "year_1": r1["publication_year"],
                    "year_2": r2["publication_year"],
                    "doi_1": r1["doi"],
                    "doi_2": r2["doi"],
                    "doi_status": doi_status,
                    "doi_decision": doi_decision,
                    "is_duplicate": is_duplicate,
                    "keep_record_id": keep_record_id,
                    "drop_record_id": drop_record_id,
                }
            )

    return pd.DataFrame(results), skipped_blocks


# --------------------------------------------------
# Threshold testing
# --------------------------------------------------


def evaluate_thresholds(df, thresholds=[90, 92, 95, 97, 99]):
    """
    NOTE: threshold only affects the 'both_missing' DOI branch. Records with
    matching or differing DOIs are decided deterministically and are NOT
    threshold-sensitive, so their counts stay constant across thresholds --
    that's expected, not a bug.
    """

    rows = []

    for threshold in thresholds:
        matches, _ = fuzzy_title_matching(df, threshold)

        is_dup = (
            matches["is_duplicate"]
            if "is_duplicate" in matches.columns
            else pd.Series(dtype=bool)
        )

        rows.append(
            {
                "threshold": threshold,
                "duplicate_candidates": int(is_dup.sum()) if len(matches) else 0,
                "high_confidence_candidates": int(
                    (matches.loc[is_dup, "combined_duplicate_score"] >= 95).sum()
                )
                if len(matches)
                else 0,
                "same_doi_merges": int(
                    (matches["doi_decision"] == "same_doi_merge").sum()
                )
                if len(matches)
                else 0,
                "fill_missing_doi_merges": int(
                    (matches["doi_decision"] == "fill_missing_doi_merge").sum()
                )
                if len(matches)
                else 0,
                "different_doi_kept_both": int(
                    (matches["doi_decision"] == "different_doi_keep_both").sum()
                )
                if len(matches)
                else 0,
            }
        )

    return pd.DataFrame(rows)


# --------------------------------------------------
# Build final deduplicated dataset
# --------------------------------------------------


def apply_deduplication(df, matches):
    """
    Given the original dataframe (indexed as prepare_duplicate_features left it,
    with source_record_id as a column) and the matches dataframe, compute the
    final set of records to drop, using union-find so that chains of duplicates
    (A dup B, B dup C) collapse into one surviving record.
    """

    parent = {rid: rid for rid in df["source_record_id"]}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(keep, drop):
        keep_root, drop_root = find(keep), find(drop)
        if keep_root != drop_root:
            parent[drop_root] = keep_root

    dup_rows = matches[matches["is_duplicate"]]

    for _, row in dup_rows.iterrows():
        keep, drop = row["keep_record_id"], row["drop_record_id"]
        if keep in parent and drop in parent:
            union(keep, drop)

    df = df.copy()
    df["duplicate_group"] = df["source_record_id"].apply(find)

    # Within each group, prefer the record that has a DOI; if multiple/none
    # have a DOI, keep the first occurrence (stable, deterministic).
    def pick_representative(group):
        with_doi = group[group["doi_norm"].notna()]
        if len(with_doi) > 0:
            return with_doi.iloc[0]["source_record_id"]
        return group.iloc[0]["source_record_id"]

    representatives = df.groupby("duplicate_group", group_keys=False).apply(
        pick_representative, include_groups=False
    )

    df["is_kept_representative"] = df["source_record_id"].isin(representatives.values)

    deduplicated = df[df["is_kept_representative"]].drop(
        columns=["duplicate_group", "is_kept_representative"]
    )

    removed = df[~df["is_kept_representative"]]

    return deduplicated, removed


# --------------------------------------------------
# Pipeline entry point
# --------------------------------------------------


def run_fuzzy_duplicate_analysis(input_file, output_dir, similarity_threshold=90):

    df = pd.read_csv(input_file)

    required_cols = {"title", "authors", "publication_year", "source_record_id", "doi"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Input file is missing required columns: {sorted(missing_cols)}"
        )

    df = prepare_duplicate_features(df)

    n_no_title = df["title_norm"].isna().sum()
    if n_no_title:
        print(
            f"[warn] {n_no_title} record(s) have no usable title and were "
            f"excluded from blocking/comparison entirely."
        )

    matches, skipped_blocks = fuzzy_title_matching(
        df, similarity_threshold=similarity_threshold
    )
    if skipped_blocks:
        print(
            f"[warn] {skipped_blocks} title block(s) exceeded max_block_size and "
            f"were skipped -- pairs inside them were not compared."
        )

    thresholds = evaluate_thresholds(df)

    deduplicated, removed = apply_deduplication(df, matches)

    matches.to_csv(f"{output_dir}/fuzzy_duplicate_candidates.csv", index=False)
    thresholds.to_csv(f"{output_dir}/threshold_evaluation.csv", index=False)
    deduplicated.to_csv(f"{output_dir}/deduplicated_records.csv", index=False)
    removed.to_csv(f"{output_dir}/removed_duplicate_records.csv", index=False)

    print(f"Original records: {len(df)}")
    print(
        f"Duplicate pairs flagged: {int(matches['is_duplicate'].sum()) if len(matches) else 0}"
    )
    print(f"Records kept after dedup: {len(deduplicated)}")
    print(f"Records removed as duplicates: {len(removed)}")

    return matches, thresholds, deduplicated, removed


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python fuzzy_duplicate_pipeline.py <input_csv> <output_dir>")
        sys.exit(1)

    run_fuzzy_duplicate_analysis(sys.argv[1], sys.argv[2])
