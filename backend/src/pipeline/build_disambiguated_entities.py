"""
Resolve author and institution entities across the merged publication corpus.

Reads the common publication dataset and writes, per run:

    author_clusters.csv           one row per resolved author identity
    author_cluster_members.csv    record/author mention -> cluster
    institution_resolutions.csv   affiliation string -> registry institution
    review_authors.csv            ranked queue of ambiguous author clusters
    review_institutions.csv       ranked queue of unresolved affiliations
    disambiguation_summary.csv    run metrics, for tracking coverage over time

Nothing here mutates the input dataset. Disambiguation is an overlay: the record
stays as harvested, and the entity resolution sits beside it with its own
confidence labels, so a consumer can choose how much of it to trust.

    python -m src.pipeline.build_disambiguated_entities --limit 20000
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.disambiguation import (
    InstitutionResolver,
    build_author_review_queue,
    build_institution_review_queue,
    build_mentions,
    disambiguate_authors,
    extract_record_evidence,
    load_registry,
)
from src.pipeline.build_final_common_dataset import build_publication_key


NEEDED_COLUMNS = [
    "source_dataset",
    "source_record_id",
    "doi",
    "publication_year",
    "authors",
    "author_orcids",
    "author_affiliations",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "primary_field",
]

DEFAULT_REGISTRY = PROJECT_ROOT / "configurations" / "sri_lanka" / "institutions.csv"


def resolve_data_dir() -> Path:
    """
    Find the common-dataset directory.

    The repository keeps `data/` at the top level while the pipeline package
    lives under `backend/`, so check both rather than hard-coding one layout.
    """
    candidates = [
        PROJECT_ROOT / "data" / "processed" / "common",
        PROJECT_ROOT.parent / "data" / "processed" / "common",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def load_records(path: Path, limit: int | None) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    missing = [column for column in NEEDED_COLUMNS if column not in frame.columns]
    for column in missing:
        frame[column] = pd.NA
    if limit:
        frame = frame.head(limit)
    return frame


def build_evidence(frame: pd.DataFrame) -> list:
    records = []
    for row_number, row in enumerate(frame.to_dict("records"), start=1):
        record_key = build_publication_key(pd.Series(row), row_number)
        records.append(extract_record_evidence(row, record_key=record_key))
    return records


def resolve_institutions(records: list, resolver: InstitutionResolver):
    """Resolve every distinct affiliation string once, then count its records."""
    counts: Counter[str] = Counter()
    for record in records:
        for value in record.institutions:
            counts[value] += 1

    resolutions = {raw: resolver.resolve(raw) for raw in counts}
    return resolutions, counts


def write_csv(rows: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    return len(frame)


def main(argv: list[str] | None = None) -> int:
    data_dir = resolve_data_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=data_dir / "common_publications_final.csv",
        help="Merged common publication dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=data_dir / "disambiguation",
        help="Directory for cluster, resolution and review outputs.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="National institution registry CSV.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N records.")
    parser.add_argument(
        "--review-limit",
        type=int,
        default=2000,
        help="Cap on rows written to each review queue.",
    )
    parser.add_argument(
        "--min-review-publications",
        type=int,
        default=1,
        help="Skip author clusters below this publication count in the review queue.",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        parser.error(f"input dataset not found: {args.input}")
    if not args.registry.is_file():
        parser.error(f"institution registry not found: {args.registry}")

    print(f"Reading {args.input}")
    frame = load_records(args.input, args.limit)
    print(f"  {len(frame):,} records")

    records = build_evidence(frame)
    mentions = build_mentions(records)
    print(f"  {len(mentions):,} author mentions")

    fragments_dropped = sum(len(record.fragment_names) for record in records)
    attributable = sum(1 for mention in mentions if mention.orcid)
    records_with_orcid = sum(1 for record in records if record.orcids)

    print("Clustering authors")
    result = disambiguate_authors(mentions)
    print(f"  {result.stats['clusters']:,} clusters")

    print("Resolving institutions")
    resolver = InstitutionResolver(load_registry(args.registry))
    resolutions, institution_counts = resolve_institutions(records, resolver)
    resolved_strings = sum(1 for value in resolutions.values() if value.is_resolved)
    resolved_records = sum(
        count for raw, count in institution_counts.items() if resolutions[raw].is_resolved
    )
    total_affiliation_mentions = sum(institution_counts.values())
    print(f"  {resolved_strings:,}/{len(resolutions):,} distinct affiliation strings resolved")

    output_dir = args.output_dir
    written: dict[str, int] = {}

    written["author_clusters"] = write_csv(
        [
            {
                "cluster_id": cluster.cluster_id,
                "canonical_name": cluster.canonical_name,
                "block": cluster.block,
                "confidence": cluster.confidence,
                "publication_count": cluster.publication_count,
                "mention_count": len(cluster.mention_ids),
                "orcids": "; ".join(cluster.orcids),
                "record_level_orcids": "; ".join(cluster.record_level_orcids[:5]),
                "name_variants": "; ".join(cluster.display_names[:8]),
                "institutions": "; ".join(cluster.institutions[:5]),
                "coauthor_blocks": "; ".join(cluster.coauthor_blocks[:10]),
                "year_min": cluster.year_min,
                "year_max": cluster.year_max,
                "ambiguity_flags": "; ".join(cluster.ambiguity_flags),
            }
            for cluster in result.clusters
        ],
        output_dir / "author_clusters.csv",
    )

    written["author_cluster_members"] = write_csv(
        [
            {
                "cluster_id": cluster.cluster_id,
                "mention_id": mention_id,
                "record_key": mention_id.rsplit("#", 1)[0],
                "author_position": mention_id.rsplit("#", 1)[1],
                "confidence": cluster.confidence,
            }
            for cluster in result.clusters
            for mention_id in cluster.mention_ids
        ],
        output_dir / "author_cluster_members.csv",
    )

    written["institution_resolutions"] = write_csv(
        [
            {
                "raw_affiliation": raw,
                "record_count": institution_counts[raw],
                "institution_id": resolution.institution_id or "",
                "preferred_name": resolution.preferred_name or "",
                "ror_id": resolution.ror_id or "",
                "method": resolution.method,
                "confidence": resolution.confidence,
                "score": resolution.score,
                "matched_on": resolution.matched_on or "",
            }
            for raw, resolution in sorted(
                resolutions.items(), key=lambda item: -institution_counts[item[0]]
            )
        ],
        output_dir / "institution_resolutions.csv",
    )

    author_queue = build_author_review_queue(
        result,
        min_publications=args.min_review_publications,
        limit=args.review_limit,
    )
    written["review_authors"] = write_csv(
        [item.as_row() for item in author_queue], output_dir / "review_authors.csv"
    )

    institution_queue = build_institution_review_queue(
        resolutions, institution_counts, limit=args.review_limit
    )
    written["review_institutions"] = write_csv(
        [item.as_row() for item in institution_queue],
        output_dir / "review_institutions.csv",
    )

    summary = [
        {"metric": "input_records", "value": len(frame)},
        {"metric": "author_mentions", "value": len(mentions)},
        {"metric": "name_fragments_dropped", "value": fragments_dropped},
        {"metric": "records_with_any_orcid", "value": records_with_orcid},
        {"metric": "mentions_with_attributed_orcid", "value": attributable},
        *[{"metric": key, "value": value} for key, value in result.stats.items()],
        {"metric": "affiliation_strings_distinct", "value": len(resolutions)},
        {"metric": "affiliation_strings_resolved", "value": resolved_strings},
        {"metric": "affiliation_mentions_total", "value": total_affiliation_mentions},
        {"metric": "affiliation_mentions_resolved", "value": resolved_records},
        {"metric": "review_queue_authors", "value": len(author_queue)},
        {"metric": "review_queue_institutions", "value": len(institution_queue)},
    ]
    written["disambiguation_summary"] = write_csv(
        summary, output_dir / "disambiguation_summary.csv"
    )

    print(f"\nWrote to {output_dir}")
    for name, count in written.items():
        print(f"  {name + '.csv':<32} {count:,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
