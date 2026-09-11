"""Work the ambiguous-author review queue.

The disambiguation run writes every author pair its rules could not settle to
``author_review_candidates.csv`` with empty ``decision`` / ``reviewer`` / ``note``
columns. A reviewer fills those in; this script turns the filled-in rows into
the decisions file the next run reads, and checks that file before it is used.

    # what is waiting, and which pairs are worth opening first
    python -m src.quality.review_ambiguous_authors

    # promote the filled-in rows to reviewed decisions
    python -m src.quality.review_ambiguous_authors --extract-decisions

    # check the decisions file before re-running the pipeline
    python -m src.quality.review_ambiguous_authors --validate

Decisions are keyed on name-variant keys rather than author identifiers, because
a variant key is stable across runs while an identifier moves when its cluster
changes.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_analytics.authors import (  # noqa: E402
    DECISION_COLUMNS,
    DECISION_DIFFERENT,
    DECISION_SAME,
    DECISION_VALUES,
    load_author_decisions,
)


DEFAULT_REVIEW_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "author_review_candidates.csv"
)
DEFAULT_REGISTRY_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "author_registry.csv"
)
DEFAULT_DECISIONS_CSV = (
    PROJECT_ROOT / "configurations" / "sri_lanka" / "author_decisions.csv"
)

DEFAULT_LIMIT = 20


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist. Run the disambiguation pipeline first.")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def queue_summary(rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    """Count what is waiting, split by reason and by whether it is flagged."""

    rows = list(rows)
    reasons: Counter[str] = Counter()
    for row in rows:
        for reason in (row.get("reasons") or "").split(";"):
            reason = reason.strip()
            if reason:
                reasons[reason] += 1

    decided = [row for row in rows if (row.get("decision") or "").strip()]
    flagged = [row for row in rows if _is_true(row.get("needs_review"))]
    return {
        "pairs": len(rows),
        "flagged_pairs": len(flagged),
        "decided_pairs": len(decided),
        "undecided_flagged_pairs": sum(
            1 for row in flagged if not (row.get("decision") or "").strip()
        ),
        "mentions_in_queue": sum(_as_int(row.get("mentions_total")) for row in rows),
        "reasons": reasons,
        "decisions": Counter(
            (row.get("decision") or "").strip().casefold() for row in decided
        ),
    }


def top_pairs(rows: Iterable[dict[str, str]], *, limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
    """Undecided pairs, heaviest first -- the order a reviewer should work in."""

    undecided = [row for row in rows if not (row.get("decision") or "").strip()]
    undecided.sort(key=lambda row: -_as_int(row.get("mentions_total")))
    return undecided[:limit]


def extract_decisions(rows: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """Turn filled-in queue rows into decision rows, reporting bad values."""

    decisions: list[dict[str, str]] = []
    problems: list[str] = []
    for line_number, row in enumerate(rows, start=2):
        decision = (row.get("decision") or "").strip().casefold()
        if not decision:
            continue
        if decision not in DECISION_VALUES:
            problems.append(
                f"row {line_number}: decision {decision!r} is not one of {sorted(DECISION_VALUES)}"
            )
            continue
        key_a = (row.get("variant_key_a") or "").strip()
        key_b = (row.get("variant_key_b") or "").strip()
        if not key_a or not key_b:
            problems.append(f"row {line_number}: both variant keys are required")
            continue
        decisions.append(
            {
                "decision": decision,
                "variant_key_a": key_a,
                "variant_key_b": key_b,
                "reviewer": (row.get("reviewer") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
        )
    return decisions, problems


def merge_decisions(
    existing: list[dict[str, str]], new_rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], int, int]:
    """Add new verdicts to the decisions file, letting the newest win a pair."""

    by_pair: dict[tuple[str, str], dict[str, str]] = {
        _pair(row): row for row in existing
    }
    added = updated = 0
    for row in new_rows:
        key = _pair(row)
        if key not in by_pair:
            added += 1
        elif by_pair[key]["decision"] != row["decision"]:
            updated += 1
        by_pair[key] = row
    ordered = sorted(by_pair.values(), key=lambda row: (row["variant_key_a"], row["variant_key_b"]))
    return ordered, added, updated


def write_decisions(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DECISION_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def validate_decisions(
    decisions_csv: Path, *, known_variant_keys: set[str] | None = None
) -> list[str]:
    """Report anything that would make the next run behave unexpectedly."""

    problems: list[str] = []
    try:
        decisions = load_author_decisions(decisions_csv)
    except ValueError as error:
        return [str(error)]

    seen: dict[tuple[str, str], str] = {}
    for decision in decisions:
        pair = decision.pair
        if pair in seen and seen[pair] != decision.decision:
            problems.append(
                f"{pair[0]} / {pair[1]}: recorded as both {seen[pair]} and {decision.decision}"
            )
        seen[pair] = decision.decision
        if known_variant_keys is not None:
            for key in pair:
                if key not in known_variant_keys:
                    problems.append(
                        f"{key}: not a name variant in the current registry -- "
                        "the spelling may have changed or the decision may be stale"
                    )
    return problems


def registry_variant_keys(registry_csv: Path) -> set[str]:
    keys: set[str] = set()
    for row in read_rows(registry_csv):
        for key in (row.get("name_variants") or "").split(";"):
            key = key.strip()
            if key:
                keys.add(key)
    return keys


def _pair(row: dict[str, str]) -> tuple[str, str]:
    return tuple(sorted((row["variant_key_a"], row["variant_key_b"])))  # type: ignore[return-value]


def _is_true(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _as_int(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def print_summary(rows: list[dict[str, str]], *, limit: int) -> None:
    summary = queue_summary(rows)
    print("Ambiguous author review queue")
    print(f"  Pairs:                    {summary['pairs']:,}")
    print(f"  Flagged (above threshold):{summary['flagged_pairs']:>8,}")
    print(f"  Decided:                  {summary['decided_pairs']:,}")
    print(f"  Flagged and undecided:    {summary['undecided_flagged_pairs']:,}")
    print(f"  Mentions represented:     {summary['mentions_in_queue']:,}")
    if summary["reasons"]:
        print("  Reasons:")
        for reason, count in summary["reasons"].most_common():
            print(f"    {reason:42} {count:>8,}")
    if summary["decisions"]:
        print("  Recorded decisions:")
        for decision, count in summary["decisions"].most_common():
            print(f"    {decision:42} {count:>8,}")

    pairs = top_pairs(rows, limit=limit)
    if pairs:
        print(f"\n  Next {len(pairs)} pairs to review:")
        for row in pairs:
            print(
                f"    [{_as_int(row.get('mentions_total')):>4}] "
                f"{row.get('name_a', '')} ({row.get('mentions_a')})"
                f"  <->  {row.get('name_b', '')} ({row.get('mentions_b')})"
            )
            print(f"           {row.get('variant_key_a')} | {row.get('variant_key_b')}")
            shared = row.get("shared_coauthors") or row.get("shared_institutions")
            if shared:
                print(f"           shared: {shared}")
        print(
            f"\n  Fill in decision ({DECISION_SAME} / {DECISION_DIFFERENT}), reviewer and note"
            f" in {DEFAULT_REVIEW_CSV.name}, then run --extract-decisions."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review ambiguous author records.")
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--decisions-csv", type=Path, default=DEFAULT_DECISIONS_CSV)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--extract-decisions",
        action="store_true",
        help="Write filled-in queue rows into the decisions file.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Check the decisions file for contradictions and stale variant keys.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.validate:
        known = registry_variant_keys(args.registry_csv) if args.registry_csv.is_file() else None
        problems = validate_decisions(args.decisions_csv, known_variant_keys=known)
        if problems:
            print(f"{len(problems)} problem(s) in {args.decisions_csv}:")
            for problem in problems:
                print(f"  - {problem}")
            raise SystemExit(1)
        print(f"{args.decisions_csv}: no problems found.")
        return

    rows = read_rows(args.review_csv)

    if args.extract_decisions:
        new_rows, problems = extract_decisions(rows)
        if problems:
            print(f"{len(problems)} problem(s) in {args.review_csv}:")
            for problem in problems:
                print(f"  - {problem}")
            raise SystemExit(1)
        existing = [
            {
                "decision": decision.decision,
                "variant_key_a": decision.variant_key_a,
                "variant_key_b": decision.variant_key_b,
                "reviewer": decision.reviewer or "",
                "note": decision.note or "",
            }
            for decision in load_author_decisions(args.decisions_csv)
        ]
        merged, added, updated = merge_decisions(existing, new_rows)
        write_decisions(args.decisions_csv, merged)
        print(f"{args.decisions_csv}: {len(merged)} decisions ({added} added, {updated} changed).")
        print("Re-run the disambiguation pipeline to apply them.")
        return

    print_summary(rows, limit=args.limit)


if __name__ == "__main__":
    main()
