"""Validate the institution-level facts in the repository registry.

Week 3 task W03-GISHAN-BANDARA-004. Complements the two existing
validators, which check different things:

- ``validate_repositories.py`` checks whether *endpoints* respond.
- ``validate_harvested_data.py`` checks whether *harvested records* are
  sound.
- this script checks whether the *registry's description of each
  institution* is internally consistent, complete, and consistent with
  what is actually on disk.

Checks performed:

1. ``duplicate_id`` / ``duplicate_name`` - ids and names are unique.
2. ``invalid_enum`` - status, phase and group hold known values.
3. ``missing_required_field`` - the fields a given status implies are
   present (a ``confirmed_live`` target must say how to reach it; a
   dead-end status must say why in ``notes``).
4. ``coverage_gap`` - every institution in
   ``data/config/institutions_reference.json`` still has a registry
   entry. See that file's ``provenance``: this is a regression guard,
   not independent proof of completeness.
5. ``orphan_data`` - processed data exists for an id with no registry
   entry.
6. ``contradicted_by_data`` - an entry declares no repository/no harvest
   while processed records exist for it.
7. ``silent_gap`` - an entry has a working route recorded but no data.
8. ``unsupported_claim`` - ``endpoint_verified_live`` is true but the
   status says the host is unreachable or blocked, or vice versa.
9. ``hosted_by`` - a ``no_own_repository`` entry names its host, and
   that host is a real registry entry.
10. ``incomplete_recovery_config`` - an entry listing ``recovery_routes``
    carries the query fields those routes need.

Exit code is 1 when any error-severity finding is present, so this can
gate CI. Warnings alone exit 0.

Examples:
    python scripts/validate_institutions.py
    python scripts/validate_institutions.py --quiet
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

REGISTRY_PATH = PROJECT_ROOT / "data" / "config" / "repositories.json"
REFERENCE_PATH = PROJECT_ROOT / "data" / "config" / "institutions_reference.json"
PROCESSED_DIRS = {
    "repository": PROJECT_ROOT / "data" / "processed" / "repositories",
    "openalex": PROJECT_ROOT / "data" / "processed" / "openalex",
    "recovery": PROJECT_ROOT / "data" / "processed" / "recovery",
}
REPORT_DIR = PROJECT_ROOT / "data" / "reports"

VALID_STATUSES = {
    "confirmed_live",
    "endpoint_inferred",
    "unreachable",
    "blocked_for_automated_requests",
    "no_repository_found",
    "no_own_repository",
    "skip",
    "pilot_do_not_harvest",
}
VALID_PHASES = {"phase_1", "phase_2", "not_applicable", "deferred"}
VALID_GROUPS = {"A", "B", "C", "D", "E", "shared_platform"}

# Statuses that assert the institution has no harvestable repository of
# its own. Records existing for these ids is a contradiction worth
# flagging -- except where a recovery route legitimately supplied them.
NO_REPOSITORY_STATUSES = {"no_repository_found", "no_own_repository", "skip"}
# Statuses that mean "we know why there is no data", so an empty result
# is expected rather than a silent gap.
EXPECTED_EMPTY_STATUSES = NO_REPOSITORY_STATUSES | {
    "unreachable",
    "blocked_for_automated_requests",
    "pilot_do_not_harvest",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count_records(directory: Path, institution_id: str) -> int:
    path = directory / f"{institution_id}.jsonl"
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def normalise_name(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").split())


def validate(registry: list[dict], reference: dict) -> list[dict]:
    findings: list[dict] = []

    def add(severity: str, check: str, institution_id: str | None, message: str) -> None:
        findings.append(
            {
                "severity": severity,
                "check": check,
                "id": institution_id,
                "message": message,
            }
        )

    ids = [entry.get("id") for entry in registry]
    for duplicate, count in Counter(ids).items():
        if count > 1:
            add("error", "duplicate_id", duplicate, f"id appears {count} times in the registry.")

    names = defaultdict(list)
    for entry in registry:
        names[normalise_name(entry.get("name", ""))].append(entry.get("id"))
    for name, owners in names.items():
        if len(owners) > 1:
            add("error", "duplicate_name", None, f"name {name!r} is shared by ids {owners}.")

    registry_ids = set(ids)

    for entry in registry:
        institution_id = entry.get("id")
        status = entry.get("status")
        notes = entry.get("notes")

        if status not in VALID_STATUSES:
            add("error", "invalid_enum", institution_id, f"unknown status {status!r}.")
        if entry.get("phase") not in VALID_PHASES:
            add("error", "invalid_enum", institution_id, f"unknown phase {entry.get('phase')!r}.")
        if entry.get("group") not in VALID_GROUPS:
            add("warning", "invalid_enum", institution_id, f"unknown group {entry.get('group')!r}.")

        if not entry.get("name"):
            add("error", "missing_required_field", institution_id, "name is missing.")

        if status in {"confirmed_live", "endpoint_inferred"}:
            if not (entry.get("oai_endpoint") or entry.get("rest_api_endpoint")):
                add(
                    "error",
                    "missing_required_field",
                    institution_id,
                    f"status is {status} but neither oai_endpoint nor rest_api_endpoint is recorded.",
                )
            if not entry.get("repository_url"):
                add(
                    "warning",
                    "missing_required_field",
                    institution_id,
                    f"status is {status} but repository_url is missing.",
                )

        if status in EXPECTED_EMPTY_STATUSES and not notes:
            # A warning, not an error: undocumented is incomplete, not
            # provably wrong, and errors here would gate CI on prose
            # nobody can reconstruct after the fact.
            add(
                "warning",
                "missing_required_field",
                institution_id,
                f"status is {status} but notes do not record why.",
            )

        if entry.get("endpoint_verified_live") and status in {
            "unreachable",
            "blocked_for_automated_requests",
        }:
            add(
                "warning",
                "unsupported_claim",
                institution_id,
                f"endpoint_verified_live is true but status is {status}.",
            )

        if status == "no_own_repository" and not entry.get("hosted_by"):
            add(
                "warning",
                "hosted_by",
                institution_id,
                "status is no_own_repository but hosted_by does not name the hosting registry id.",
            )
        hosted_by = entry.get("hosted_by")
        if hosted_by and hosted_by not in registry_ids:
            add(
                "error",
                "hosted_by",
                institution_id,
                f"hosted_by={hosted_by!r} is not a registry id.",
            )

        for route in entry.get("recovery_routes", []) or []:
            required = {
                "crossref_affiliation": "crossref_affiliation_query",
                "pubmed_affiliation": "pubmed_affiliation_query",
            }.get(route)
            if required and not entry.get(required):
                add(
                    "error",
                    "incomplete_recovery_config",
                    institution_id,
                    f"recovery_routes lists {route!r} but {required} is missing.",
                )

        counts = {
            name: count_records(directory, institution_id)
            for name, directory in PROCESSED_DIRS.items()
        }
        total = sum(counts.values())

        if status in NO_REPOSITORY_STATUSES and counts["repository"]:
            add(
                "error",
                "contradicted_by_data",
                institution_id,
                f"status is {status} but {counts['repository']} repository records exist on disk.",
            )

        if total == 0 and status not in EXPECTED_EMPTY_STATUSES:
            add(
                "warning",
                "silent_gap",
                institution_id,
                f"status is {status} but no records exist in any processed namespace.",
            )

        if entry.get("harvest_route") and counts["repository"] == 0:
            add(
                "warning",
                "silent_gap",
                institution_id,
                f"harvest_route={entry['harvest_route']!r} is recorded but no repository records exist.",
            )

    reference_entries = reference.get("institutions", [])
    for item in reference_entries:
        reference_id = item.get("registry_id")
        if reference_id not in registry_ids:
            add(
                "error",
                "coverage_gap",
                reference_id,
                f"{item.get('name')!r} is in the reference list but has no registry entry.",
            )

    for directory in PROCESSED_DIRS.values():
        if not directory.exists():
            continue
        for path in directory.glob("*.jsonl"):
            if path.stem not in registry_ids:
                add(
                    "error",
                    "orphan_data",
                    path.stem,
                    f"{path} holds records for an id with no registry entry.",
                )

    if not reference.get("verified_against_ugc"):
        add(
            "warning",
            "coverage_gap",
            None,
            "institutions_reference.json has never been reconciled against the UGC's published "
            "list (verified_against_ugc is null), so coverage checks are a regression guard only.",
        )

    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate registry institution information.")
    parser.add_argument("--quiet", action="store_true", help="Only print the summary and findings.")
    parser.add_argument("--no-report", action="store_true", help="Skip writing the JSON report.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    registry = load_json(REGISTRY_PATH)["repositories"]
    reference = load_json(REFERENCE_PATH) if REFERENCE_PATH.exists() else {"institutions": []}

    findings = validate(registry, reference)
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    if not args.quiet:
        print(f"Validated {len(registry)} registry entries against {len(reference.get('institutions', []))} reference institutions.\n")

    if findings:
        width = max(len(f["check"]) for f in findings)
        for finding in sorted(findings, key=lambda f: (f["severity"] != "error", f["check"], f["id"] or "")):
            label = "ERROR  " if finding["severity"] == "error" else "warning"
            print(f"{label} {finding['check']:<{width}}  {finding['id'] or '-':<14} {finding['message']}")
    else:
        print("No findings: every institution entry is internally consistent.")

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")

    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_DIR / f"institution_validation_{timestamp}.json"
        report_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "registry_entry_count": len(registry),
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "findings": findings,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Saved institution-validation report to {report_path}")

    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
