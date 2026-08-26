"""Build a publication dataset with standardized publication types and venues.

Publication types are mapped onto a controlled vocabulary, splitting out the
record form and thesis degree level so that standardizing does not discard the
facts the raw value encoded.

Venue names are canonicalized from corpus evidence rather than from a fixed
list. A first pass counts every spelling and every ISSN-to-name pairing; a
second pass rewrites each record to the dominant spelling of its venue. Two
passes are needed because the dominant spelling is only knowable after the whole
corpus has been read.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
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

from research_analytics.venues import (  # noqa: E402
    classify_venue,
    standardize_journal_name,
    standardize_publication_type,
    strip_trailing_parenthetical,
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
    / "common_publications_final_type_journal_normalized.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_type_journal_normalized_summary.csv"
)
DEFAULT_TYPE_MAPPING_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "publication_type_mapping.csv"
)
DEFAULT_JOURNAL_MAPPING_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "journal_name_mapping.csv"
)

DEFAULT_CHUNK_SIZE = 25_000

ADDED_COLUMNS = (
    "publication_type_standardized",
    "record_form",
    "thesis_degree_level",
    "is_research_output",
    "journal_standardized",
    "venue_type",
)


class VenueIndex:
    """Corpus-wide venue evidence, collected in the first pass."""

    def __init__(self) -> None:
        self.name_counts: Counter[str] = Counter()
        self.casefold_groups: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.issn_groups: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self._canonical_by_casefold: dict[str, str] = {}
        self._canonical_by_issn: dict[str, str] = {}

    def observe(self, name: str | None, issn: str | None) -> None:
        if not name:
            return
        self.name_counts[name] += 1
        self.casefold_groups[name.casefold()][name] += 1
        if issn:
            self.issn_groups[issn][name] += 1

    def finalize(self) -> None:
        """Choose the dominant spelling for each casefold group and each ISSN."""

        for key, spellings in self.casefold_groups.items():
            self._canonical_by_casefold[key] = _dominant(spellings)
        for issn, spellings in self.issn_groups.items():
            self._canonical_by_issn[issn] = _dominant(spellings)

    def canonical(self, name: str | None, issn: str | None) -> str | None:
        """Resolve a venue name to its canonical spelling.

        ISSN is authoritative when present: it is an identifier, so records
        sharing one are the same venue however the name was written. Otherwise
        the dominant spelling of the casefold group wins, and a trailing
        "(Publisher)" qualifier is dropped only when a shorter spelling of the
        same venue is already attested in the corpus.
        """

        if not name:
            return None

        if issn:
            by_issn = self._canonical_by_issn.get(issn)
            if by_issn:
                return by_issn

        canonical = self._canonical_by_casefold.get(name.casefold(), name)

        stripped = strip_trailing_parenthetical(canonical)
        if stripped != canonical:
            attested = self._canonical_by_casefold.get(stripped.casefold())
            if attested:
                return attested
        return canonical


def _dominant(spellings: Counter[str]) -> str:
    """Most frequent spelling of a venue.

    Ties are broken towards natural title case. Without this, an equal split
    between "Journal of the Postgraduate Institute of Medicine" and "Journal Of
    The Postgraduate Institute of Medicine" resolves alphabetically, and
    uppercase sorts first -- so the worse spelling would win.
    """

    def rank(item: tuple[str, int]) -> tuple[int, int, str]:
        name, count = item
        lowercase_letters = sum(1 for character in name if character.islower())
        return (count, lowercase_letters, name)

    return max(spellings.items(), key=lambda item: rank((item[0], item[1])))[0]


def primary_issn(row: dict[str, Any]) -> str | None:
    """Prefer the linking ISSN, which is stable across a venue's formats."""

    issn_l = str(row.get("issn_l") or "").strip()
    if issn_l and issn_l.lower() != "nan":
        return issn_l
    issn = str(row.get("issn") or "").strip()
    if not issn or issn.lower() == "nan":
        return None
    first = issn.split(";")[0].strip()
    return first or None


class TypeJournalStats:
    def __init__(self) -> None:
        self.rows = 0
        self.raw_types: Counter[str] = Counter()
        self.standardized_types: Counter[str] = Counter()
        self.record_forms: Counter[str] = Counter()
        self.degree_levels: Counter[str] = Counter()
        self.venue_types: Counter[str] = Counter()
        self.research_outputs = 0
        self.rows_with_journal = 0
        self.journal_renamed = 0
        self.type_mapping: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.journal_mapping: defaultdict[str, Counter[str]] = defaultdict(Counter)


def build_venue_index(
    input_csv: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> VenueIndex:
    """First pass: count every venue spelling and ISSN pairing."""

    index = VenueIndex()
    for chunk in pd.read_csv(
        input_csv, dtype="object", low_memory=False, chunksize=chunk_size, keep_default_na=False
    ):
        for row in chunk.to_dict("records"):
            index.observe(standardize_journal_name(row.get("journal")), primary_issn(row))
    index.finalize()
    return index


def normalize_row(
    row: dict[str, Any], index: VenueIndex, stats: TypeJournalStats
) -> dict[str, Any]:
    """Standardize one record's type and venue fields."""

    stats.rows += 1
    output = dict(row)

    raw_type = str(row.get("publication_type") or row.get("type") or "").strip()
    standardized = standardize_publication_type(raw_type)

    output["publication_type_standardized"] = standardized.publication_type
    output["record_form"] = standardized.record_form
    output["thesis_degree_level"] = standardized.thesis_degree_level
    output["is_research_output"] = standardized.is_research_output

    if raw_type:
        stats.raw_types[raw_type] += 1
        stats.type_mapping[raw_type][standardized.publication_type] += 1
    stats.standardized_types[standardized.publication_type] += 1
    stats.record_forms[standardized.record_form] += 1
    stats.degree_levels[standardized.thesis_degree_level] += 1
    if standardized.is_research_output:
        stats.research_outputs += 1

    name = standardize_journal_name(row.get("journal"))
    issn = primary_issn(row)
    canonical = index.canonical(name, issn)
    venue_type = classify_venue(canonical, has_issn=bool(issn))

    output["journal_standardized"] = canonical or ""
    output["venue_type"] = venue_type

    if name:
        stats.rows_with_journal += 1
        if canonical and canonical != name:
            stats.journal_renamed += 1
            stats.journal_mapping[name][canonical] += 1
    stats.venue_types[venue_type] += 1

    return output


def iter_normalized_chunks(
    input_csv: Path,
    index: VenueIndex,
    stats: TypeJournalStats,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[pd.DataFrame]:
    for chunk in pd.read_csv(
        input_csv, dtype="object", low_memory=False, chunksize=chunk_size, keep_default_na=False
    ):
        normalized = [normalize_row(row, index, stats) for row in chunk.to_dict("records")]
        yield pd.DataFrame(normalized, columns=list(chunk.columns) + list(ADDED_COLUMNS))


def write_summary(
    summary_csv: Path, stats: TypeJournalStats, *, input_csv: Path, output_csv: Path
) -> None:
    def percentage(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    rows: list[dict[str, Any]] = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "rows", "value": stats.rows},
        {"metric": "distinct_raw_types", "value": len(stats.raw_types)},
        {"metric": "distinct_standardized_types", "value": len(stats.standardized_types)},
        {"metric": "research_outputs", "value": stats.research_outputs},
        {
            "metric": "research_output_share",
            "value": percentage(stats.research_outputs, stats.rows),
        },
        {"metric": "rows_with_journal", "value": stats.rows_with_journal},
        {"metric": "journal_names_rewritten", "value": stats.journal_renamed},
        {"metric": "distinct_journal_rewrites", "value": len(stats.journal_mapping)},
    ]
    rows.extend(
        {"metric": f"publication_type:{name}", "value": count}
        for name, count in stats.standardized_types.most_common()
    )
    rows.extend(
        {"metric": f"record_form:{name}", "value": count}
        for name, count in stats.record_forms.most_common()
    )
    rows.extend(
        {"metric": f"thesis_degree_level:{name}", "value": count}
        for name, count in stats.degree_levels.most_common()
        if name != "unknown"
    )
    rows.extend(
        {"metric": f"venue_type:{name}", "value": count}
        for name, count in stats.venue_types.most_common()
    )

    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(summary_csv, index=False)


def write_type_mapping(mapping_csv: Path, stats: TypeJournalStats) -> None:
    """Every raw type value and what it became, for review."""

    rows = [
        {
            "raw_type": raw,
            "standardized_type": standardized,
            "rows": count,
        }
        for raw, targets in stats.type_mapping.items()
        for standardized, count in targets.items()
    ]
    rows.sort(key=lambda item: (-item["rows"], item["raw_type"]))
    mapping_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["raw_type", "standardized_type", "rows"]).to_csv(
        mapping_csv, index=False
    )


def write_journal_mapping(mapping_csv: Path, stats: TypeJournalStats) -> None:
    rows = [
        {"raw_journal": raw, "standardized_journal": canonical, "rows": count}
        for raw, targets in stats.journal_mapping.items()
        for canonical, count in targets.items()
    ]
    rows.sort(key=lambda item: (-item["rows"], item["raw_journal"]))
    mapping_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        rows, columns=["raw_journal", "standardized_journal", "rows"]
    ).to_csv(mapping_csv, index=False)


def build_type_journal_normalized_dataset(
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
    type_mapping_csv: Path,
    journal_mapping_csv: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> TypeJournalStats:
    index = build_venue_index(input_csv, chunk_size=chunk_size)
    stats = TypeJournalStats()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    wrote_header = False
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        for chunk in iter_normalized_chunks(input_csv, index, stats, chunk_size=chunk_size):
            chunk.to_csv(handle, index=False, header=not wrote_header)
            wrote_header = True

    write_summary(summary_csv, stats, input_csv=input_csv, output_csv=output_csv)
    write_type_mapping(type_mapping_csv, stats)
    write_journal_mapping(journal_mapping_csv, stats)
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a dataset with standardized publication types and venues."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--type-mapping-csv", type=Path, default=DEFAULT_TYPE_MAPPING_CSV)
    parser.add_argument("--journal-mapping-csv", type=Path, default=DEFAULT_JOURNAL_MAPPING_CSV)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = build_type_journal_normalized_dataset(
        args.input_csv,
        args.output_csv,
        args.summary_csv,
        args.type_mapping_csv,
        args.journal_mapping_csv,
        chunk_size=args.chunk_size,
    )

    def percentage(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    print("Done.")
    print(f"  Rows: {stats.rows:,}")
    print(
        f"  Publication types: {len(stats.raw_types):,} raw"
        f" -> {len(stats.standardized_types):,} standardized"
    )
    print(
        f"  Research outputs: {stats.research_outputs:,}"
        f" ({percentage(stats.research_outputs, stats.rows)})"
    )
    print("  Top types:")
    for name, count in stats.standardized_types.most_common(8):
        print(f"    {name:24} {count:>8,}")
    print("  Venue types:")
    for name, count in stats.venue_types.most_common():
        print(f"    {name:24} {count:>8,}")
    print(
        f"  Journal names rewritten: {stats.journal_renamed:,}"
        f" across {len(stats.journal_mapping):,} distinct spellings"
    )
    print(f"  Dataset: {args.output_csv}")
    print(f"  Summary: {args.summary_csv}")
    print(f"  Type mapping: {args.type_mapping_csv}")
    print(f"  Journal mapping: {args.journal_mapping_csv}")


if __name__ == "__main__":
    main()
