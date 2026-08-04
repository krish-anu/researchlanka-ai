"""Build a publication dataset with standardized institutions, affiliations and countries.

Applies the national institution registry to every record and derives the
collaboration fields. Records are never dropped: an institution that cannot be
resolved is kept in ``unresolved_institutions`` so the registry can be improved
from evidence rather than guesswork.

Institution values are recovered in three passes, in decreasing order of
confidence:

1. ``institutions`` as supplied by the source metadata.
2. ``source_institution_id`` -- the repository a record was harvested from,
   which identifies its institution exactly. This recovers the repository-only
   records, which carry no institution metadata of their own.
3. ``author_affiliations`` -- parsed for institution names, used only to add
   institutions the first two passes missed.

``institution_source`` records which pass supplied the value, so downstream
analysis can weight or exclude the inferred ones.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
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

from research_analytics.institutions import (  # noqa: E402
    NationalInstitutionRegistry,
    classify_collaboration,
    collaboration_scope,
    parse_affiliation,
    split_multi_value,
    standardize_countries,
    standardize_institution_name,
)


DEFAULT_INPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_institution_normalized.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_institution_normalized_summary.csv"
)
DEFAULT_REGISTRY_CSV = PROJECT_ROOT / "configurations" / "sri_lanka" / "institutions.csv"
DEFAULT_UNRESOLVED_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_unresolved_institutions.csv"
)

NATIONAL_COUNTRY_CODE = "LK"
DEFAULT_CHUNK_SIZE = 25_000

ADDED_COLUMNS = (
    "national_institution_ids",
    "national_institutions",
    "unresolved_institutions",
    "institution_source",
    "collaboration_type",
    "collaboration_scope",
)

MULTI_VALUE_SEPARATOR = "; "


class NormalizationStats:
    """Counters describing what the run changed, for the summary report."""

    def __init__(self) -> None:
        self.rows = 0
        self.rows_with_institution_before = 0
        self.rows_with_institution_after = 0
        self.rows_with_country_before = 0
        self.rows_with_country_after = 0
        self.institution_mentions = 0
        self.institution_mentions_resolved = 0
        self.national_mentions_expected = 0
        self.national_mentions_resolved = 0
        self.backfilled_from_source_id = 0
        self.backfilled_from_affiliation = 0
        self.countries_inferred = 0
        self.collaboration_types: Counter[str] = Counter()
        self.collaboration_scopes: Counter[str] = Counter()
        self.institution_sources: Counter[str] = Counter()
        self.unresolved: Counter[str] = Counter()
        self.unrecognised_countries: Counter[str] = Counter()


def normalize_row(
    row: dict[str, Any],
    registry: NationalInstitutionRegistry,
    stats: NormalizationStats,
    *,
    national_country_code: str = NATIONAL_COUNTRY_CODE,
) -> dict[str, Any]:
    """Standardize one record's institution, affiliation and country fields."""

    stats.rows += 1
    output = dict(row)

    metadata_names = [
        name
        for name in (
            standardize_institution_name(value)
            for value in split_multi_value(row.get("institutions"))
        )
        if name
    ]
    if metadata_names:
        stats.rows_with_institution_before += 1

    affiliation_names, affiliation_countries = parse_affiliation(row.get("author_affiliations"))

    names: list[str] = list(metadata_names)
    institution_source = "metadata" if names else ""

    # Pass 2: the harvesting repository identifies the institution exactly.
    if not names:
        source_institutions = registry.resolve_from_source_id(row.get("source_institution_id"))
        if source_institutions:
            names = [institution.preferred_name for institution in source_institutions]
            institution_source = "source_institution_id"
            stats.backfilled_from_source_id += 1

    # Pass 3: affiliations fill remaining gaps and add co-affiliations.
    if not names and affiliation_names:
        names = list(affiliation_names)
        institution_source = "author_affiliations"
        stats.backfilled_from_affiliation += 1
    elif affiliation_names:
        for name in affiliation_names:
            if name not in names:
                names.append(name)

    resolved, unresolved = registry.resolve_names(names)
    stats.institution_mentions += len(names)
    stats.institution_mentions_resolved += len(names) - len(unresolved)
    for name in unresolved:
        stats.unresolved[name] += 1

    # Registry quality is measured against the names already confirmed national,
    # not against all mentions: foreign institutions are outside a national
    # registry by design and can never resolve.
    for name in split_multi_value(row.get("sri_lankan_institutions")):
        stats.national_mentions_expected += 1
        if registry.resolve_name(name) is not None:
            stats.national_mentions_resolved += 1

    national_institution_ids = [institution.institution_id for institution in resolved]
    national_institutions = [institution.preferred_name for institution in resolved]

    # Display names prefer the registry's canonical spelling.
    standardized_names = national_institutions + [
        name for name in names if registry.resolve_name(name) is None
    ]

    country_codes, unrecognised = standardize_countries(row.get("countries"))
    if country_codes:
        stats.rows_with_country_before += 1
    for value in unrecognised:
        stats.unrecognised_countries[value] += 1

    for code in affiliation_countries:
        if code not in country_codes:
            country_codes.append(code)
    if national_institution_ids and national_country_code not in country_codes:
        country_codes.append(national_country_code)
        stats.countries_inferred += 1

    output["institutions"] = _join(standardized_names)
    output["countries"] = _join(country_codes)
    output["author_affiliations"] = _join(affiliation_names or standardized_names)
    output["national_institution_ids"] = _join(national_institution_ids)
    output["national_institutions"] = _join(national_institutions)
    output["unresolved_institutions"] = _join(unresolved)
    output["institution_source"] = institution_source or "none"

    collaboration_type = classify_collaboration(
        {"countries": country_codes},
        national_institution_ids=national_institution_ids,
        unresolved_institutions=unresolved,
        national_country_code=national_country_code,
    )
    output["collaboration_type"] = collaboration_type
    output["collaboration_scope"] = collaboration_scope(collaboration_type)

    if standardized_names:
        stats.rows_with_institution_after += 1
    if country_codes:
        stats.rows_with_country_after += 1
    stats.collaboration_types[collaboration_type] += 1
    stats.collaboration_scopes[output["collaboration_scope"]] += 1
    stats.institution_sources[output["institution_source"]] += 1

    return output


def _join(values: list[str]) -> str:
    return MULTI_VALUE_SEPARATOR.join(values)


def iter_normalized_chunks(
    input_csv: Path,
    registry: NationalInstitutionRegistry,
    stats: NormalizationStats,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    national_country_code: str = NATIONAL_COUNTRY_CODE,
) -> Iterator[pd.DataFrame]:
    """Stream the dataset in chunks so memory stays flat on the full corpus."""

    reader = pd.read_csv(
        input_csv,
        dtype="object",
        low_memory=False,
        chunksize=chunk_size,
        keep_default_na=False,
    )
    for chunk in reader:
        normalized = [
            normalize_row(
                row,
                registry,
                stats,
                national_country_code=national_country_code,
            )
            for row in chunk.to_dict("records")
        ]
        yield pd.DataFrame(normalized, columns=list(chunk.columns) + list(ADDED_COLUMNS))


def write_summary(summary_csv: Path, stats: NormalizationStats, *, input_csv: Path, output_csv: Path) -> None:
    def percentage(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    rows: list[dict[str, Any]] = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "rows", "value": stats.rows},
        {"metric": "rows_with_institution_before", "value": stats.rows_with_institution_before},
        {"metric": "rows_with_institution_after", "value": stats.rows_with_institution_after},
        {
            "metric": "institution_coverage_before",
            "value": percentage(stats.rows_with_institution_before, stats.rows),
        },
        {
            "metric": "institution_coverage_after",
            "value": percentage(stats.rows_with_institution_after, stats.rows),
        },
        {"metric": "rows_with_country_before", "value": stats.rows_with_country_before},
        {"metric": "rows_with_country_after", "value": stats.rows_with_country_after},
        {
            "metric": "country_coverage_before",
            "value": percentage(stats.rows_with_country_before, stats.rows),
        },
        {
            "metric": "country_coverage_after",
            "value": percentage(stats.rows_with_country_after, stats.rows),
        },
        {"metric": "institution_mentions", "value": stats.institution_mentions},
        {"metric": "institution_mentions_resolved", "value": stats.institution_mentions_resolved},
        {
            "metric": "institution_resolution_rate",
            "value": percentage(stats.institution_mentions_resolved, stats.institution_mentions),
        },
        {"metric": "national_mentions_expected", "value": stats.national_mentions_expected},
        {"metric": "national_mentions_resolved", "value": stats.national_mentions_resolved},
        {
            "metric": "national_resolution_rate",
            "value": percentage(stats.national_mentions_resolved, stats.national_mentions_expected),
        },
        {"metric": "backfilled_from_source_id", "value": stats.backfilled_from_source_id},
        {"metric": "backfilled_from_affiliation", "value": stats.backfilled_from_affiliation},
        {"metric": "countries_inferred_from_institution", "value": stats.countries_inferred},
        {"metric": "distinct_unresolved_institutions", "value": len(stats.unresolved)},
        {"metric": "distinct_unrecognised_countries", "value": len(stats.unrecognised_countries)},
    ]
    rows.extend(
        {"metric": f"collaboration_type:{name}", "value": count}
        for name, count in sorted(stats.collaboration_types.items())
    )
    rows.extend(
        {"metric": f"collaboration_scope:{name}", "value": count}
        for name, count in sorted(stats.collaboration_scopes.items())
    )
    rows.extend(
        {"metric": f"institution_source:{name}", "value": count}
        for name, count in sorted(stats.institution_sources.items())
    )

    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(summary_csv, index=False)


def write_unresolved(unresolved_csv: Path, stats: NormalizationStats) -> None:
    """Write unresolved institution names by frequency, to drive registry work."""

    rows = [
        {"institution_name": name, "mentions": count}
        for name, count in stats.unresolved.most_common()
    ]
    unresolved_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["institution_name", "mentions"]).to_csv(
        unresolved_csv, index=False
    )


def build_institution_normalized_dataset(
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
    registry_csv: Path,
    unresolved_csv: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    national_country_code: str = NATIONAL_COUNTRY_CODE,
) -> NormalizationStats:
    registry = NationalInstitutionRegistry.from_csv(
        registry_csv, country_code=national_country_code
    )
    stats = NormalizationStats()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    wrote_header = False
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        for chunk in iter_normalized_chunks(
            input_csv,
            registry,
            stats,
            chunk_size=chunk_size,
            national_country_code=national_country_code,
        ):
            chunk.to_csv(handle, index=False, header=not wrote_header)
            wrote_header = True

    write_summary(summary_csv, stats, input_csv=input_csv, output_csv=output_csv)
    write_unresolved(unresolved_csv, stats)
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a dataset with standardized institutions, affiliations and countries."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--unresolved-csv", type=Path, default=DEFAULT_UNRESOLVED_CSV)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = build_institution_normalized_dataset(
        args.input_csv,
        args.output_csv,
        args.summary_csv,
        args.registry_csv,
        args.unresolved_csv,
        chunk_size=args.chunk_size,
    )

    def percentage(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    print("Done.")
    print(f"  Rows: {stats.rows:,}")
    print(
        "  Institution coverage: "
        f"{percentage(stats.rows_with_institution_before, stats.rows)}"
        f" -> {percentage(stats.rows_with_institution_after, stats.rows)}"
    )
    print(
        "  Country coverage:     "
        f"{percentage(stats.rows_with_country_before, stats.rows)}"
        f" -> {percentage(stats.rows_with_country_after, stats.rows)}"
    )
    print(
        "  National institution mentions resolved: "
        f"{percentage(stats.national_mentions_resolved, stats.national_mentions_expected)}"
        f" ({stats.national_mentions_resolved:,} of {stats.national_mentions_expected:,})"
    )
    print(
        "  All institution mentions resolved:      "
        f"{percentage(stats.institution_mentions_resolved, stats.institution_mentions)}"
        f" ({stats.institution_mentions_resolved:,} of {stats.institution_mentions:,})"
        "  [foreign institutions are outside the national registry]"
    )
    print("  Collaboration scope:")
    for name, count in stats.collaboration_scopes.most_common():
        print(f"    {name:14} {count:>8,}  ({percentage(count, stats.rows)})")
    print(f"  Dataset: {args.output_csv}")
    print(f"  Summary: {args.summary_csv}")
    print(f"  Unresolved institutions: {args.unresolved_csv}")


if __name__ == "__main__":
    main()
