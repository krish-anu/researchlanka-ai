"""Apply reviewed Google Maps location evidence to the institution registry.

Google Maps evidence is only used to add safe aliases to existing Sri Lankan
registry entries. It must not create institutions or change ownership evidence.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Iterable

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_analytics.institutions import normalize_lookup_key  # noqa: E402


DEFAULT_EVIDENCE_CSV = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "validation"
    / "google_maps_institution_location_evidence.csv"
)
DEFAULT_REGISTRY_CSV = PROJECT_ROOT / "configurations" / "sri_lanka" / "institutions.csv"
DEFAULT_REPORT_CSV = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "validation"
    / "google_maps_registry_alias_application.csv"
)


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def registry_indexes(
    rows: list[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    names_by_key: dict[str, dict[str, str]] = {}
    aliases_by_institution: dict[str, set[str]] = {}

    for row in rows:
        institution_id = clean_text(row.get("institution_id"))
        preferred_name = clean_text(row.get("preferred_name"))
        alternative_name = clean_text(row.get("alternative_name"))
        for value in (preferred_name, alternative_name):
            key = normalize_lookup_key(value)
            if key:
                names_by_key[key] = row
        if institution_id:
            aliases_by_institution.setdefault(institution_id, set()).add(
                normalize_lookup_key(alternative_name or preferred_name)
            )

    return names_by_key, aliases_by_institution


def report_row(evidence: dict[str, str], action: str, reason: str, institution_id: str = "") -> dict[str, str]:
    return {
        "candidate_name": clean_text(evidence.get("candidate_name")),
        "matched_title": clean_text(evidence.get("matched_title")),
        "status": clean_text(evidence.get("status")),
        "confidence": clean_text(evidence.get("confidence")),
        "institution_id": institution_id,
        "action": action,
        "reason": reason,
    }


def evidence_confidence(row: dict[str, str]) -> float:
    try:
        return float(clean_text(row.get("confidence")))
    except ValueError:
        return 0.0


def apply_evidence_to_registry(
    *,
    evidence_csv: Path,
    registry_csv: Path,
    report_csv: Path,
    statuses: set[str] | None = None,
    min_confidence: float = 0.65,
    dry_run: bool = False,
) -> dict[str, int]:
    """Add non-conflicting confirmed candidate names as registry aliases."""

    selected_statuses = {status.casefold() for status in (statuses or {"confirmed"})}
    registry_fields, registry_rows = read_csv(registry_csv)
    _evidence_fields, evidence_rows = read_csv(evidence_csv)
    names_by_key, aliases_by_institution = registry_indexes(registry_rows)

    report_rows: list[dict[str, str]] = []
    additions: list[dict[str, str]] = []

    for evidence in evidence_rows:
        candidate = clean_text(evidence.get("candidate_name"))
        matched_title = clean_text(evidence.get("matched_title"))
        status = clean_text(evidence.get("status")).casefold()
        candidate_key = normalize_lookup_key(candidate)
        matched_key = normalize_lookup_key(matched_title)

        if status not in selected_statuses:
            report_rows.append(report_row(evidence, "skip", "status_not_selected"))
            continue
        if evidence_confidence(evidence) < min_confidence:
            report_rows.append(report_row(evidence, "skip", "confidence_below_threshold"))
            continue
        if not candidate_key:
            report_rows.append(report_row(evidence, "skip", "blank_candidate_name"))
            continue
        if not matched_key or matched_key not in names_by_key:
            report_rows.append(report_row(evidence, "skip", "matched_title_not_in_registry"))
            continue

        matched_registry_row = names_by_key[matched_key]
        institution_id = clean_text(matched_registry_row.get("institution_id"))
        existing_candidate = names_by_key.get(candidate_key)
        if existing_candidate is not None:
            existing_id = clean_text(existing_candidate.get("institution_id"))
            if existing_id == institution_id:
                report_rows.append(report_row(evidence, "skip", "alias_already_exists", institution_id))
            else:
                report_rows.append(
                    report_row(evidence, "skip", f"alias_conflicts_with:{existing_id}", institution_id)
                )
            continue

        if candidate_key in aliases_by_institution.get(institution_id, set()):
            report_rows.append(report_row(evidence, "skip", "alias_already_exists", institution_id))
            continue

        new_row = dict(matched_registry_row)
        new_row["alternative_name"] = candidate
        additions.append(new_row)
        aliases_by_institution.setdefault(institution_id, set()).add(candidate_key)
        names_by_key[candidate_key] = new_row
        report_rows.append(report_row(evidence, "add_alias", "confirmed_maps_alias", institution_id))

    if additions and not dry_run:
        write_csv(registry_csv, registry_fields, [*registry_rows, *additions])
    write_csv(
        report_csv,
        ["candidate_name", "matched_title", "status", "confidence", "institution_id", "action", "reason"],
        report_rows,
    )

    return {
        "evidence_rows": len(evidence_rows),
        "aliases_added": len(additions),
        "skipped_rows": len(evidence_rows) - len(additions),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote reviewed Google Maps location evidence into registry aliases."
    )
    parser.add_argument("--evidence-csv", type=Path, default=DEFAULT_EVIDENCE_CSV)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--report-csv", type=Path, default=DEFAULT_REPORT_CSV)
    parser.add_argument("--status", action="append", default=None)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = apply_evidence_to_registry(
        evidence_csv=args.evidence_csv,
        registry_csv=args.registry_csv,
        report_csv=args.report_csv,
        statuses=set(args.status) if args.status else {"confirmed"},
        min_confidence=args.min_confidence,
        dry_run=args.dry_run,
    )
    mode = "dry run" if args.dry_run else "applied"
    print(
        f"Done ({mode}). Evidence rows: {result['evidence_rows']:,}; "
        f"aliases added: {result['aliases_added']:,}; skipped: {result['skipped_rows']:,}."
    )
    print(f"Report: {args.report_csv}")


if __name__ == "__main__":
    main()
