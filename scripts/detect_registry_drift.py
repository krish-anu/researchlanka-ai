"""Reconcile the registry's claims about each repository against the
evidence in the latest validation, harvest and coverage reports.

Week 3 task W03-GISHAN-BANDARA-005. The registry is hand-curated, and
15 university servers change underneath it without telling anyone: hosts
go offline, OAI indexes get rebuilt, endpoints move. Nothing previously
noticed when a recorded claim stopped being true -- the Ruhuna outage on
2026-07-25 was caught by a human reading a report, which does not scale.

This script compares, per institution:

| Registry claim | Evidence |
|---|---|
| ``status`` | whether the endpoint answered in the latest validation run |
| ``endpoint_verified_live`` | the same run's ``reachable`` result |
| ``oai_endpoint`` | the URL that actually worked, if a fallback was used |
| ``harvest_route`` | which raw file on disk is actually the largest |
| has records | the OAI ``has_records`` probe |

It reads reports rather than making network requests, so it is cheap and
safe to run in CI. Run ``validate_repositories.py`` first for fresh
evidence; this script reports how old the evidence is.

Exit code is 1 when drift is found, 0 when the registry matches reality.

Examples:
    python scripts/detect_registry_drift.py
    python scripts/detect_registry_drift.py --max-age-days 14
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

REGISTRY_PATH = PROJECT_ROOT / "data" / "config" / "repositories.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"

RAW_FILES = {
    "oai": "oai_dc.jsonl",
    "rest": "rest_items.jsonl",
    "html": "html_meta.jsonl",
    "crossref": "crossref_works.jsonl",
}
LIVE_STATUSES = {"confirmed_live", "endpoint_inferred"}
DEAD_STATUSES = {"unreachable", "blocked_for_automated_requests"}


def latest_report(prefix: str) -> tuple[Path | None, dict | None]:
    candidates = sorted(REPORT_DIR.glob(f"{prefix}_*.json"))
    if not candidates:
        return None, None
    path = candidates[-1]
    return path, json.loads(path.read_text(encoding="utf-8"))


def report_age_days(report: dict) -> float | None:
    stamp = report.get("generated_at")
    if not stamp:
        return None
    try:
        generated = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - generated).total_seconds() / 86400


def normalise_url(url: str | None) -> str:
    """Strip the noise that makes two spellings of one URL compare unequal.

    Explicit default ports and trailing slashes are cosmetic; without
    this, ``http://host/oai/request`` and ``http://host:80/oai/request``
    read as an endpoint change.
    """

    if not url:
        return ""
    parsed = urlparse(url.strip().rstrip("/"))
    host = parsed.hostname or ""
    port = parsed.port
    if (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443):
        port = None
    netloc = f"{host}:{port}" if port else host
    return f"{parsed.scheme}://{netloc}{parsed.path}".rstrip("/").lower()


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def actual_route(institution_id: str) -> tuple[str | None, int]:
    counts = {
        route: line_count(RAW_DIR / institution_id / filename)
        for route, filename in RAW_FILES.items()
    }
    best = max(counts, key=lambda route: counts[route])
    return (best, counts[best]) if counts[best] else (None, 0)


def detect(registry: list[dict], validation: dict | None) -> list[dict]:
    findings: list[dict] = []

    def add(institution_id: str, kind: str, claim: str, evidence: str) -> None:
        findings.append(
            {"id": institution_id, "drift": kind, "registry_claims": claim, "evidence": evidence}
        )

    results = {r["id"]: r for r in (validation or {}).get("results", [])}

    for entry in registry:
        institution_id = entry.get("id")
        status = entry.get("status")
        result = results.get(institution_id)

        if result:
            oai = result.get("oai") or {}
            reachable = oai.get("reachable")

            if status in LIVE_STATUSES and reachable is False:
                add(
                    institution_id,
                    "endpoint_died",
                    f"status={status}",
                    f"latest validation could not reach the endpoint: {str(oai.get('error'))[:120]}",
                )

            if status in DEAD_STATUSES and reachable is True:
                add(
                    institution_id,
                    "endpoint_recovered",
                    f"status={status}",
                    "latest validation reached the endpoint successfully -- the status may be stale.",
                )

            if entry.get("endpoint_verified_live") is True and reachable is False:
                add(
                    institution_id,
                    "stale_verification",
                    "endpoint_verified_live=true",
                    "latest validation could not reach the endpoint.",
                )

            # Compare against the URL that actually worked, never against
            # the server's self-reported <baseURL>: DSpace instances
            # routinely advertise a canonical hostname they are not
            # served from (busl self-reports repo.busl.ac.lk while
            # answering on dl-busl.nsf.gov.lk). That is a source-side
            # config quirk, not evidence that the endpoint moved.
            recorded = normalise_url(entry.get("oai_endpoint"))
            worked = normalise_url(oai.get("endpoint_tried"))
            if reachable and recorded and worked and recorded != worked:
                add(
                    institution_id,
                    "endpoint_moved",
                    f"oai_endpoint={entry.get('oai_endpoint')}",
                    f"validation had to fall back to {oai.get('endpoint_tried')}",
                )

            has_records = oai.get("has_records")
            route, count = actual_route(institution_id)
            if reachable and has_records is False and route == "oai" and count:
                add(
                    institution_id,
                    "index_emptied",
                    "OAI is the largest raw route on disk",
                    f"the OAI index now returns no records, but {count} OAI records are stored -- "
                    "a re-harvest would lose them.",
                )

        route, count = actual_route(institution_id)
        claimed_route = entry.get("harvest_route")
        if route and claimed_route and claimed_route != route:
            add(
                institution_id,
                "route_mismatch",
                f"harvest_route={claimed_route}",
                f"the largest raw file on disk is the {route} route ({count} records).",
            )
        if route and not claimed_route and route != "oai":
            add(
                institution_id,
                "route_undeclared",
                "harvest_route is unset, implying OAI",
                f"the largest raw file on disk is the {route} route ({count} records).",
            )

    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect drift between the registry and reality.")
    parser.add_argument(
        "--max-age-days",
        type=float,
        default=7.0,
        help="Warn when the latest validation report is older than this. Default: 7",
    )
    parser.add_argument("--no-report", action="store_true", help="Skip writing the JSON report.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["repositories"]
    validation_path, validation = latest_report("repository_validation")

    if validation is None:
        print(
            "No repository_validation_*.json report found. Run "
            "scripts/validate_repositories.py first -- without it only route drift can be checked."
        )
    else:
        age = report_age_days(validation)
        age_note = f"{age:.1f} days old" if age is not None else "age unknown"
        print(f"Evidence: {validation_path.name} ({age_note})")
        if age is not None and age > args.max_age_days:
            print(
                f"WARNING: that evidence is older than {args.max_age_days} days. "
                "Re-run scripts/validate_repositories.py before trusting these results."
            )

    findings = detect(registry, validation)

    print()
    if findings:
        for finding in sorted(findings, key=lambda f: (f["drift"], f["id"])):
            print(f"{finding['drift']:<20} {finding['id']:<14} {finding['registry_claims']}")
            print(f"{'':<20} {'':<14} -> {finding['evidence']}")
        print(f"\n{len(findings)} drift finding(s): the registry disagrees with the evidence.")
    else:
        print("No drift: every registry claim matches the latest evidence.")

    if not args.no_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_DIR / f"registry_drift_{timestamp}.json"
        report_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "evidence_report": validation_path.name if validation_path else None,
                    "drift_count": len(findings),
                    "findings": findings,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Saved drift report to {report_path}")

    raise SystemExit(1 if findings else 0)


if __name__ == "__main__":
    main()
