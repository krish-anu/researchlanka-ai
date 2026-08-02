"""Validate harvested + mapped repository data and produce a
source-coverage report: per-institution record counts, data-quality
checks, and a cross-check against what the registry claims vs. what was
actually collected.

Examples:
    python scripts/quality/validate_harvested_data.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.repository_registry import harvestable_targets, load_registry

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"

CURRENT_YEAR = datetime.now(timezone.utc).year
PLAUSIBLE_YEAR_RANGE = (1900, CURRENT_YEAR + 1)


@dataclass
class InstitutionValidation:
    id: str
    name: str
    declared_status: str
    raw_record_count: int = 0
    raw_deleted_count: int = 0
    duplicate_source_ids: int = 0
    mapped_record_count: int = 0
    missing_title_count: int = 0
    missing_authors_and_contributors_count: int = 0
    implausible_year_count: int = 0
    identifier_host_mismatches: int = 0
    identifier_host_seen: list[str] = field(default_factory=list)
    malformed_identifier_count: int = 0
    issues: list[str] = field(default_factory=list)


def _oai_identifier_host(oai_identifier: str | None) -> str | None:
    """Extract the host segment from an oai:<host>:<localID> identifier.

    A couple of Sri Lankan DSpace instances (e.g. SEU) misconfigure
    dspace.oai.identifier and embed a full "http://host" URL instead of
    a bare hostname (oai:http://ir.lib.seu.ac.lk:123456789/1029). Strip
    that scheme prefix so the host still compares correctly -- the
    malformed-identifier fact itself is reported separately.
    """

    if not oai_identifier or not oai_identifier.startswith("oai:"):
        return None
    parts = oai_identifier.split(":")
    if len(parts) < 2:
        return None
    host = parts[1]
    if host in ("http", "https") and len(parts) > 2:
        host = parts[2].lstrip("/")
    return host


def _is_malformed_oai_identifier(oai_identifier: str | None) -> bool:
    return bool(oai_identifier) and "://" in oai_identifier


def _latest_harvest_errors() -> dict[str, str]:
    """Read the most recent harvest_summary_*.json (from harvest_all.py)
    and return {institution_id: error} for targets that didn't succeed,
    so zero-record cases can be explained precisely instead of guessed at.
    """

    summaries = sorted(REPORT_DIR.glob("harvest_summary_*.json"))
    if not summaries:
        return {}

    payload = json.loads(summaries[-1].read_text(encoding="utf-8"))
    return {
        r["id"]: r["error"]
        for r in payload.get("results", [])
        if r.get("error") and r.get("status") != "ok"
    }


def validate_institution(target, harvest_errors: dict[str, str]) -> InstitutionValidation:
    result = InstitutionValidation(
        id=target.id,
        name=target.name,
        declared_status=target.status,
    )

    raw_path = RAW_DIR / target.id / "oai_dc.jsonl"
    rest_path = RAW_DIR / target.id / "rest_items.jsonl"
    expected_host = urlparse(target.oai_endpoint).netloc if target.oai_endpoint else None
    seen_ids: set[str] = set()
    hosts_seen: set[str] = set()

    # Mirror map_to_common_schema.py's source choice: when both routes were
    # harvested, only the larger one feeds the mapped output, so only count
    # that one as "raw" here -- counting both would double-count the same
    # items and never reconcile with the mapped total.
    def _line_count(path: Path) -> int:
        with path.open(encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    oai_line_count = _line_count(raw_path) if raw_path.exists() else 0
    rest_line_count = _line_count(rest_path) if rest_path.exists() else 0
    use_rest = rest_line_count > oai_line_count

    if use_rest:
        with rest_path.open(encoding="utf-8") as rest_file:
            for line in rest_file:
                if not line.strip():
                    continue
                record = json.loads(line)
                result.raw_record_count += 1
                record_id = record.get("uuid")
                if record_id:
                    if record_id in seen_ids:
                        result.duplicate_source_ids += 1
                    seen_ids.add(record_id)

    if not use_rest and raw_path.exists():
        with raw_path.open(encoding="utf-8") as raw_file:
            for line in raw_file:
                record = json.loads(line)
                result.raw_record_count += 1

                if record.get("deleted"):
                    result.raw_deleted_count += 1
                    continue

                record_id = record.get("oai_identifier")
                if record_id:
                    if record_id in seen_ids:
                        result.duplicate_source_ids += 1
                    seen_ids.add(record_id)

                    if _is_malformed_oai_identifier(record_id):
                        result.malformed_identifier_count += 1

                    host = _oai_identifier_host(record_id)
                    if host:
                        hosts_seen.add(host)
                        if expected_host and host not in expected_host and expected_host not in host:
                            result.identifier_host_mismatches += 1

    result.identifier_host_seen = sorted(hosts_seen)
    if result.malformed_identifier_count:
        result.issues.append(
            f"{result.malformed_identifier_count} record(s) have a non-standard oai_identifier "
            f"(embeds a full URL instead of a bare host -- a source-side DSpace config quirk, "
            f"still unique per item, just not spec-compliant)."
        )
    if expected_host and hosts_seen and result.identifier_host_mismatches:
        result.issues.append(
            f"{result.identifier_host_mismatches} record(s) have an OAI identifier host that doesn't "
            f"match the registry's declared endpoint host ({expected_host}); seen hosts: {result.identifier_host_seen}"
        )

    mapped_path = PROCESSED_DIR / f"{target.id}.jsonl"
    if mapped_path.exists():
        with mapped_path.open(encoding="utf-8") as mapped_file:
            for line in mapped_file:
                record = json.loads(line)
                result.mapped_record_count += 1

                if not record.get("title"):
                    result.missing_title_count += 1

                if not record.get("authors") and not record.get("contributors"):
                    result.missing_authors_and_contributors_count += 1

                year = record.get("publication_year")
                if year is not None and not (PLAUSIBLE_YEAR_RANGE[0] <= year <= PLAUSIBLE_YEAR_RANGE[1]):
                    result.implausible_year_count += 1

    if result.mapped_record_count:
        if result.missing_title_count:
            result.issues.append(f"{result.missing_title_count} mapped record(s) missing a title.")
        if result.implausible_year_count:
            result.issues.append(
                f"{result.implausible_year_count} mapped record(s) have an implausible publication_year "
                f"(outside {PLAUSIBLE_YEAR_RANGE[0]}-{PLAUSIBLE_YEAR_RANGE[1]})."
            )

    if target.status in {"confirmed_live"} and target.oai_endpoint and result.raw_record_count == 0:
        known_error = harvest_errors.get(target.id)
        if known_error:
            result.issues.append(
                f"Registry marks this target confirmed_live, but the last harvest run failed: {known_error}"
            )
        else:
            result.issues.append(
                "Registry marks this target confirmed_live with an OAI endpoint, but no raw records were "
                "harvested -- likely an empty/stale OAI index (see repositories.json notes) or harvest wasn't run."
            )

    return result


def main() -> None:
    targets = harvestable_targets(load_registry())
    harvest_errors = _latest_harvest_errors()

    results = [validate_institution(target, harvest_errors) for target in targets]

    print(f"{'ID':<16}{'Raw':<8}{'Dup':<6}{'Mapped':<8}{'NoTitle':<9}{'BadYear':<9}Issues")
    print("-" * 100)
    for r in results:
        issue_summary = "; ".join(r.issues)[:60]
        print(
            f"{r.id:<16}{r.raw_record_count:<8}{r.duplicate_source_ids:<6}"
            f"{r.mapped_record_count:<8}{r.missing_title_count:<9}{r.implausible_year_count:<9}{issue_summary}"
        )

    total_raw = sum(r.raw_record_count for r in results)
    total_mapped = sum(r.mapped_record_count for r in results)
    institutions_with_data = sum(1 for r in results if r.raw_record_count > 0)
    institutions_with_issues = sum(1 for r in results if r.issues)

    print(
        f"\n{institutions_with_data}/{len(results)} institutions have harvested data. "
        f"{total_raw} raw records, {total_mapped} mapped to the common schema. "
        f"{institutions_with_issues} institutions flagged with data-quality issues."
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"source_coverage_{timestamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "institutions_checked": len(results),
        "institutions_with_data": institutions_with_data,
        "institutions_with_issues": institutions_with_issues,
        "total_raw_records": total_raw,
        "total_mapped_records": total_mapped,
        "results": [asdict(r) for r in results],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved source-coverage report to {report_path}")


if __name__ == "__main__":
    main()
