"""Build a publication dataset with disambiguated author identities.

Resolves every author mention onto a stable ``author_id`` using the rules in
:mod:`research_analytics.authors`: ORCID first, then shared affiliation, then
shared coauthor, then an exact fully spelled-out name inside one surname block.
Records are never dropped and names are never rewritten -- the identity is added
alongside the original ``authors`` string, and the evidence that produced it is
written next to it.

The run makes two passes over the input. The first indexes name variants and
their evidence; the second assigns identifiers back onto the records. Variant
level aggregation keeps memory bounded by the number of distinct spellings
rather than the number of authorships.

Four files come out:

* the dataset, with ``author_ids`` and the matching evidence per record;
* an author registry, one row per resolved identity;
* a summary of what the run resolved and how;
* a review queue of author pairs the rules could not settle.

Reviewed verdicts are fed back through ``--decisions-csv`` and applied on the
next run, so the review queue shrinks instead of being re-answered.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_analytics.authors import (  # noqa: E402
    AuthorDisambiguationResult,
    AuthorVariantIndex,
    MATCH_METHOD_PRECEDENCE,
    author_mentions,
    disambiguate_authors,
    load_author_decisions,
)


DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_institution_normalized.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_author_disambiguated.csv"
)
DEFAULT_REGISTRY_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "author_registry.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_author_disambiguation_summary.csv"
)
DEFAULT_REVIEW_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "author_review_candidates.csv"
)
DEFAULT_DECISIONS_CSV = (
    PROJECT_ROOT / "configurations" / "sri_lanka" / "author_decisions.csv"
)

DEFAULT_CHUNK_SIZE = 25_000

# A pair is only worth a reviewer's time once it carries this many mentions
# between the two candidates; smaller pairs stay in the file, unflagged.
AUTHOR_REVIEW_MENTION_THRESHOLD = 5
# Share of clusters expected to carry an ORCID. ORCID coverage in the corpus is
# ~13% of records, so this is a floor for noticing a regression, not a target.
ORCID_LINKED_CLUSTER_RATE_THRESHOLD = 0.05
# Every parsed author mention should end up with an identifier.
MENTION_ASSIGNMENT_RATE_THRESHOLD = 1.0

ADDED_COLUMNS = (
    "author_ids",
    "author_match_methods",
    "author_disambiguation_level",
    "ambiguous_author_flag",
)

MULTI_VALUE_SEPARATOR = "; "

REGISTRY_COLUMNS = [
    "author_id",
    "preferred_name",
    "surname",
    "match_method",
    "confidence",
    "needs_review",
    "review_reasons",
    "orcids",
    "publications",
    "name_variants",
    "name_variant_count",
    "national_institution_ids",
    "affiliation_keys",
    "distinct_coauthor_names",
    "year_min",
    "year_max",
    "sources",
    "sample_records",
    "merge_evidence",
]

REVIEW_COLUMNS = [
    "blocking_key",
    "variant_key_a",
    "variant_key_b",
    "name_a",
    "name_b",
    "author_id_a",
    "author_id_b",
    "mentions_a",
    "mentions_b",
    "mentions_total",
    "shared_institutions",
    "shared_coauthors",
    "reasons",
    "sample_records_a",
    "sample_records_b",
    "needs_review",
    "decision",
    "reviewer",
    "note",
]


def _join(values: Any) -> str:
    return MULTI_VALUE_SEPARATOR.join(str(value) for value in values)


def build_variant_index(
    input_csv: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> AuthorVariantIndex:
    """Pass 1: accumulate name variants and their evidence across the corpus."""

    index = AuthorVariantIndex()
    for chunk in _read_chunks(input_csv, chunk_size):
        for row in chunk.to_dict("records"):
            index.add_record(row)
    return index


def assign_row(row: dict[str, Any], result: AuthorDisambiguationResult) -> dict[str, Any]:
    """Attach author identifiers and their evidence to one record.

    Identifiers are positional against the record's parsed authors, so an
    ``authors`` entry that could not be parsed leaves no gap: unparsed positions
    are simply absent from both lists, and ``author_disambiguation_level``
    reports the weakest evidence behind the record's identities.
    """

    output = dict(row)
    author_ids: list[str] = []
    methods: list[str] = []
    ambiguous = False

    for mention in author_mentions(row):
        author_id = result.variant_to_author.get(mention.name.variant_key)
        if not author_id:
            continue
        cluster = result.clusters[author_id]
        author_ids.append(author_id)
        methods.append(cluster.match_method)
        ambiguous = ambiguous or cluster.needs_review

    output["author_ids"] = _join(author_ids)
    output["author_match_methods"] = _join(methods)
    output["author_disambiguation_level"] = (
        min(methods, key=MATCH_METHOD_PRECEDENCE.index) if methods else "none"
    )
    output["ambiguous_author_flag"] = ambiguous
    return output


def iter_assigned_chunks(
    input_csv: Path,
    result: AuthorDisambiguationResult,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[pd.DataFrame]:
    """Pass 2: stream the dataset back out with identifiers attached."""

    for chunk in _read_chunks(input_csv, chunk_size):
        assigned = [assign_row(row, result) for row in chunk.to_dict("records")]
        yield pd.DataFrame(assigned, columns=list(chunk.columns) + list(ADDED_COLUMNS))


def _read_chunks(input_csv: Path, chunk_size: int) -> Iterator[pd.DataFrame]:
    return pd.read_csv(
        input_csv,
        dtype="object",
        low_memory=False,
        chunksize=chunk_size,
        keep_default_na=False,
    )


def write_registry(
    registry_csv: Path,
    index: AuthorVariantIndex,
    result: AuthorDisambiguationResult,
) -> None:
    """Write one row per resolved author identity."""

    rows: list[dict[str, Any]] = []
    for cluster in sorted(
        result.clusters.values(), key=lambda item: (-item.mentions, item.author_id)
    ):
        coauthor_keys = {
            key
            for variant_key in cluster.variant_keys
            for key in index.variants[variant_key].coauthor_keys
        }
        rows.append(
            {
                "author_id": cluster.author_id,
                "preferred_name": cluster.preferred_name,
                "surname": cluster.surname,
                "match_method": cluster.match_method,
                "confidence": cluster.confidence,
                "needs_review": cluster.needs_review,
                "review_reasons": _join(cluster.review_reasons),
                "orcids": _join(cluster.orcids),
                "publications": cluster.mentions,
                "name_variants": _join(cluster.variant_keys),
                "name_variant_count": len(cluster.variant_keys),
                "national_institution_ids": _join(cluster.national_institution_ids),
                "affiliation_keys": _join(
                    key.split(":", 1)[1]
                    for key in cluster.institution_keys
                    if key.startswith("aff:")
                ),
                "distinct_coauthor_names": len(coauthor_keys),
                "year_min": cluster.year_min,
                "year_max": cluster.year_max,
                "sources": _join(cluster.sources),
                "sample_records": _join(cluster.records),
                "merge_evidence": _join(cluster.merge_evidence),
            }
        )

    registry_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=REGISTRY_COLUMNS).to_csv(registry_csv, index=False)


def write_review_candidates(
    review_csv: Path,
    result: AuthorDisambiguationResult,
    *,
    review_mention_threshold: int = AUTHOR_REVIEW_MENTION_THRESHOLD,
) -> int:
    """Write the ambiguous-author queue, ready to be filled in and fed back.

    The ``decision``, ``reviewer`` and ``note`` columns are left empty: a
    reviewer fills them in, and the same file is then accepted as the decisions
    input on the next run.
    """

    rows: list[dict[str, Any]] = []
    flagged = 0
    for pair in result.review_pairs:
        needs_review = pair.mentions >= review_mention_threshold
        flagged += int(needs_review)
        rows.append(
            {
                "blocking_key": pair.blocking_key,
                "variant_key_a": pair.variant_key_a,
                "variant_key_b": pair.variant_key_b,
                "name_a": pair.name_a,
                "name_b": pair.name_b,
                "author_id_a": pair.author_id_a,
                "author_id_b": pair.author_id_b,
                "mentions_a": pair.mentions_a,
                "mentions_b": pair.mentions_b,
                "mentions_total": pair.mentions,
                "shared_institutions": _join(pair.shared_institution_keys),
                "shared_coauthors": _join(pair.shared_coauthor_keys),
                "reasons": _join(pair.reasons),
                "sample_records_a": _join(pair.records_a),
                "sample_records_b": _join(pair.records_b),
                "needs_review": needs_review,
                "decision": "",
                "reviewer": "",
                "note": "",
            }
        )

    review_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=REVIEW_COLUMNS).to_csv(review_csv, index=False)
    return flagged


def write_summary(
    summary_csv: Path,
    index: AuthorVariantIndex,
    result: AuthorDisambiguationResult,
    *,
    input_csv: Path,
    output_csv: Path,
    decisions_csv: Path | None,
    review_mention_threshold: int = AUTHOR_REVIEW_MENTION_THRESHOLD,
    orcid_cluster_rate_threshold: float = ORCID_LINKED_CLUSTER_RATE_THRESHOLD,
    assignment_rate_threshold: float = MENTION_ASSIGNMENT_RATE_THRESHOLD,
) -> None:
    def rate(part: int, whole: int) -> float:
        return part / whole if whole else 0.0

    def percentage(part: int, whole: int) -> str:
        return f"{(rate(part, whole) * 100):.1f}%"

    index_stats = index.stats
    stats = result.stats
    assigned_mentions = sum(
        index.variants[key].mentions for key in result.variant_to_author
    )
    orcid_clusters = sum(1 for cluster in result.clusters.values() if cluster.orcids)
    review_clusters = sum(1 for cluster in result.clusters.values() if cluster.needs_review)
    flagged_pairs = sum(
        1 for pair in result.review_pairs if pair.mentions >= review_mention_threshold
    )
    orcid_cluster_rate = rate(orcid_clusters, len(result.clusters))
    assignment_rate = rate(assigned_mentions, index_stats.author_mentions)

    rows: list[dict[str, Any]] = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "decisions_csv", "value": str(decisions_csv) if decisions_csv else ""},
        {
            "metric": "entity_auto_resolution_threshold",
            "value": "orcid_or_shared_affiliation_or_shared_coauthor_or_exact_full_name",
        },
        {"metric": "entity_fuzzy_auto_resolution_enabled", "value": False},
        {"metric": "entity_fuzzy_review_only", "value": True},
        {"metric": "review_mention_threshold", "value": review_mention_threshold},
        {
            "metric": "orcid_linked_cluster_rate_threshold",
            "value": f"{orcid_cluster_rate_threshold * 100:.1f}%",
        },
        {
            "metric": "mention_assignment_rate_threshold",
            "value": f"{assignment_rate_threshold * 100:.1f}%",
        },
        {"metric": "records", "value": index_stats.records},
        {"metric": "author_mentions", "value": index_stats.author_mentions},
        {"metric": "unparsed_author_names", "value": index_stats.unparsed_names},
        {"metric": "author_mentions_assigned", "value": assigned_mentions},
        {
            "metric": "mention_assignment_rate",
            "value": percentage(assigned_mentions, index_stats.author_mentions),
        },
        {
            "metric": "mention_assignment_rate_pass",
            "value": assignment_rate >= assignment_rate_threshold,
        },
        {"metric": "distinct_name_variants", "value": stats.variants},
        {"metric": "surname_blocks", "value": stats.blocks},
        {"metric": "author_clusters", "value": stats.clusters},
        {
            "metric": "variants_merged_into_clusters",
            "value": stats.variants - stats.clusters,
        },
        {"metric": "records_with_orcid_field", "value": index_stats.records_with_orcid_field},
        {
            "metric": "records_with_position_aligned_orcids",
            "value": index_stats.records_with_aligned_orcids,
        },
        {"metric": "invalid_orcids", "value": index_stats.invalid_orcids},
        {"metric": "author_mentions_with_orcid", "value": index_stats.mentions_with_orcid},
        {
            "metric": "orcid_mention_coverage",
            "value": percentage(index_stats.mentions_with_orcid, index_stats.author_mentions),
        },
        {"metric": "orcid_linked_clusters", "value": orcid_clusters},
        {
            "metric": "orcid_linked_cluster_rate",
            "value": percentage(orcid_clusters, len(result.clusters)),
        },
        {
            "metric": "orcid_linked_cluster_rate_pass",
            "value": orcid_cluster_rate >= orcid_cluster_rate_threshold,
        },
        {
            "metric": "records_with_institution_evidence",
            "value": index_stats.records_with_institution_evidence,
        },
        {"metric": "merges_blocked_by_orcid_conflict", "value": stats.orcid_blocked_merges},
        {"metric": "merges_blocked_by_name_conflict", "value": stats.name_blocked_merges},
        {"metric": "reviewed_merges_applied", "value": stats.decision_merges},
        {"metric": "reviewed_splits_applied", "value": stats.decision_splits},
        {"metric": "reviewed_merges_overriding_orcid", "value": stats.manual_orcid_overrides},
        {"metric": "oversized_surname_blocks", "value": stats.oversized_blocks},
        {"metric": "clusters_needing_review", "value": review_clusters},
        {"metric": "review_pairs", "value": len(result.review_pairs)},
        {
            "metric": "review_pairs_at_or_above_threshold",
            "value": flagged_pairs,
        },
    ]
    rows.extend(
        {"metric": f"merges_by_method:{method}", "value": count}
        for method, count in sorted(stats.merges_by_method.items())
    )
    rows.extend(
        {"metric": f"clusters_by_method:{method}", "value": count}
        for method, count in sorted(stats.clusters_by_method.items())
    )
    rows.extend(
        {"metric": f"clusters_by_confidence:{level}", "value": count}
        for level, count in sorted(stats.clusters_by_confidence.items())
    )

    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(summary_csv, index=False)


def build_author_disambiguated_dataset(
    input_csv: Path,
    output_csv: Path,
    registry_csv: Path,
    summary_csv: Path,
    review_csv: Path,
    *,
    decisions_csv: Path | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_shared_coauthors: int = 1,
    review_mention_threshold: int = AUTHOR_REVIEW_MENTION_THRESHOLD,
) -> tuple[AuthorVariantIndex, AuthorDisambiguationResult]:
    decisions = load_author_decisions(decisions_csv) if decisions_csv else []

    index = build_variant_index(input_csv, chunk_size=chunk_size)
    result = disambiguate_authors(
        index,
        decisions=decisions,
        min_shared_coauthors=min_shared_coauthors,
    )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    wrote_header = False
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        for chunk in iter_assigned_chunks(input_csv, result, chunk_size=chunk_size):
            chunk.to_csv(handle, index=False, header=not wrote_header)
            wrote_header = True

    write_registry(registry_csv, index, result)
    write_review_candidates(
        review_csv, result, review_mention_threshold=review_mention_threshold
    )
    write_summary(
        summary_csv,
        index,
        result,
        input_csv=input_csv,
        output_csv=output_csv,
        decisions_csv=decisions_csv,
        review_mention_threshold=review_mention_threshold,
    )
    return index, result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve author mentions onto stable author identities."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument(
        "--decisions-csv",
        type=Path,
        default=DEFAULT_DECISIONS_CSV,
        help="Reviewed same_author / different_author verdicts. Missing file means none.",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument(
        "--min-shared-coauthors",
        type=int,
        default=1,
        help="Shared coauthors required before coauthor evidence merges two names.",
    )
    parser.add_argument(
        "--review-mention-threshold",
        type=int,
        default=AUTHOR_REVIEW_MENTION_THRESHOLD,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index, result = build_author_disambiguated_dataset(
        args.input_csv,
        args.output_csv,
        args.registry_csv,
        args.summary_csv,
        args.review_csv,
        decisions_csv=args.decisions_csv,
        chunk_size=args.chunk_size,
        min_shared_coauthors=args.min_shared_coauthors,
        review_mention_threshold=args.review_mention_threshold,
    )

    def percentage(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    stats = result.stats
    print("Done.")
    print(f"  Records:            {index.stats.records:,}")
    print(f"  Author mentions:    {index.stats.author_mentions:,}")
    print(f"  Distinct spellings: {stats.variants:,}")
    print(f"  Author identities:  {stats.clusters:,}")
    print(
        "  ORCID coverage:     "
        f"{percentage(index.stats.mentions_with_orcid, index.stats.author_mentions)}"
        " of mentions"
    )
    print("  Merges by evidence:")
    for method, count in stats.merges_by_method.most_common():
        print(f"    {method:12} {count:>8,}")
    print(f"  Merges blocked by conflicting ORCIDs: {stats.orcid_blocked_merges:,}")
    print(f"  Merges blocked by conflicting names:  {stats.name_blocked_merges:,}")
    print(
        "  Review queue: "
        f"{len(result.review_pairs):,} pairs, "
        f"{sum(1 for c in result.clusters.values() if c.needs_review):,} flagged identities"
    )
    print(f"  Dataset:  {args.output_csv}")
    print(f"  Registry: {args.registry_csv}")
    print(f"  Summary:  {args.summary_csv}")
    print(f"  Review:   {args.review_csv}")


if __name__ == "__main__":
    main()
