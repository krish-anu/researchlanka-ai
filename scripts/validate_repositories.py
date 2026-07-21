"""Validate live OAI-PMH, REST API, robots.txt and sitemap access for
the Sri Lankan repository targets listed in data/config/repositories.json.

This implements Recommendation 3 and 8 from the repository target
inventory: confirm every inferred endpoint with a live ?verb=Identify /
?verb=ListMetadataFormats request before it is used for ingestion, and
respect robots.txt / rate limits while doing so.

Examples:
    python scripts/validate_repositories.py
    python scripts/validate_repositories.py --phase phase_1
    python scripts/validate_repositories.py --ids uom,nsf,sljol --raw
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
import urllib3

# We deliberately retry with verify=False when a site's TLS setup is broken,
# to tell a misconfigured-but-live server apart from a dead one. Suppress the
# resulting per-request warning noise; the finding is still recorded in the
# report via ssl_verify_failed.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.repository_registry import (
    RepositoryTarget,
    harvestable_targets,
    load_registry,
)

OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "reports"
DEFAULT_TIMEOUT = 20
DEFAULT_DELAY = 1.0
USER_AGENT = "researchlanka-ai-repository-validator/1.0 (+https://github.com/)"

# Alternate OAI paths to retry, per the inventory's decision thresholds:
# XMLUI/JSPUI DSpace sites sometimes need /xmlui or /jspui in the path.
ALTERNATE_OAI_SUFFIXES = [
    "/server/oai/request",
    "/oai/request",
    "/xmlui/oai/request",
    "/jspui/oai/request",
]


@dataclass
class OaiCheckResult:
    endpoint_tried: str
    reachable: bool = False
    repository_name: str | None = None
    base_url: str | None = None
    protocol_version: str | None = None
    earliest_datestamp: str | None = None
    granularity: str | None = None
    deleted_record: str | None = None
    metadata_formats: list[str] = field(default_factory=list)
    error: str | None = None
    ssl_verify_failed: bool = False
    attempts: list[dict[str, str]] = field(default_factory=list)
    has_records: bool | None = None
    list_records_error: str | None = None


@dataclass
class TargetReport:
    id: str
    name: str
    group: str
    phase: str
    declared_status: str
    checked_at: str
    oai: dict[str, Any] | None = None
    rest_api_ok: bool | None = None
    rest_api_error: str | None = None
    rest_api_ssl_verify_failed: bool = False
    robots_txt: dict[str, Any] | None = None
    sitemap: dict[str, Any] | None = None


def alternate_oai_urls(oai_endpoint: str) -> list[str]:
    """Build a list of candidate OAI URLs to try, starting with the given one.

    A number of Sri Lankan DSpace sites turned out to only serve OAI-PMH
    over plain HTTP (broken/expired HTTPS certs or no TLS listener at all),
    and a couple only resolve under a "www." host. So beyond the documented
    path, we also try: the same path over http://, and a www.-prefixed host
    variant, before falling back to other common DSpace OAI path patterns.
    """

    parsed = urlparse(oai_endpoint)
    hosts = [parsed.netloc]
    if not parsed.netloc.startswith("www."):
        hosts.append("www." + parsed.netloc)

    schemes = [parsed.scheme] + [s for s in ("https", "http") if s != parsed.scheme]

    candidates = [oai_endpoint]
    for host in hosts:
        for scheme in schemes:
            candidate = f"{scheme}://{host}{parsed.path}"
            if candidate not in candidates:
                candidates.append(candidate)

    for host in hosts:
        for scheme in schemes:
            origin = f"{scheme}://{host}"
            for suffix in ALTERNATE_OAI_SUFFIXES:
                candidate = origin + suffix
                if candidate not in candidates:
                    candidates.append(candidate)

    return candidates


def parse_identify(xml_text: str) -> dict[str, Any]:
    root = ElementTree.fromstring(xml_text)
    identify = root.find(f"{OAI_NS}Identify")
    if identify is None:
        error = root.find(f"{OAI_NS}error")
        message = error.text if error is not None else "No <Identify> element in response."
        raise ValueError(message)

    def text_of(tag: str) -> str | None:
        el = identify.find(f"{OAI_NS}{tag}")
        return el.text if el is not None else None

    return {
        "repository_name": text_of("repositoryName"),
        "base_url": text_of("baseURL"),
        "protocol_version": text_of("protocolVersion"),
        "earliest_datestamp": text_of("earliestDatestamp"),
        "granularity": text_of("granularity"),
        "deleted_record": text_of("deletedRecord"),
    }


def parse_list_metadata_formats(xml_text: str) -> list[str]:
    root = ElementTree.fromstring(xml_text)
    list_formats = root.find(f"{OAI_NS}ListMetadataFormats")
    if list_formats is None:
        return []
    prefixes = []
    for fmt in list_formats.findall(f"{OAI_NS}metadataFormat"):
        prefix_el = fmt.find(f"{OAI_NS}metadataPrefix")
        if prefix_el is not None and prefix_el.text:
            prefixes.append(prefix_el.text)
    return prefixes


def _request_with_ssl_fallback(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int,
    params: dict[str, str] | None = None,
) -> tuple[requests.Response | None, bool, str | None]:
    """Make a request. Returns (response, ssl_fallback_used, error).

    If the secure request fails with an SSL error, retries once with
    certificate verification disabled so a misconfigured-but-live server
    can be told apart from a genuinely unreachable one.
    """

    try:
        response = session.request(method, url, params=params, timeout=timeout)
        return response, False, None
    except requests.exceptions.SSLError:
        try:
            response = session.request(
                method, url, params=params, timeout=timeout, verify=False
            )
            return response, True, None
        except requests.RequestException as retry_exc:
            return None, False, f"SSL error, insecure retry also failed: {retry_exc}"
    except requests.RequestException as exc:
        return None, False, str(exc)


def _get_identify(
    session: requests.Session, url: str, *, timeout: int
) -> tuple[requests.Response | None, bool, str | None]:
    return _request_with_ssl_fallback(
        session, "GET", url, timeout=timeout, params={"verb": "Identify"}
    )


def check_oai(
    session: requests.Session,
    oai_endpoint: str,
    *,
    timeout: int,
    try_alternates: bool,
) -> OaiCheckResult:
    candidates = alternate_oai_urls(oai_endpoint) if try_alternates else [oai_endpoint]

    attempts: list[dict[str, str]] = []
    for candidate in candidates:
        response, ssl_fallback_used, error = _get_identify(session, candidate, timeout=timeout)

        if error is not None:
            attempts.append({"url": candidate, "error": error})
            continue

        if response.status_code != 200:
            attempts.append({"url": candidate, "error": f"HTTP {response.status_code}"})
            continue

        try:
            parsed = parse_identify(response.text)
        except (ElementTree.ParseError, ValueError) as exc:
            attempts.append({"url": candidate, "error": f"Invalid OAI response: {exc}"})
            continue

        result = OaiCheckResult(
            endpoint_tried=candidate,
            reachable=True,
            ssl_verify_failed=ssl_fallback_used,
            attempts=attempts,
            **parsed,
        )

        try:
            formats_response = session.get(
                candidate,
                params={"verb": "ListMetadataFormats"},
                timeout=timeout,
                verify=not ssl_fallback_used,
            )
            if formats_response.status_code == 200:
                result.metadata_formats = parse_list_metadata_formats(formats_response.text)
        except requests.RequestException as exc:
            result.error = f"Identify OK, ListMetadataFormats failed: {exc}"

        # Identify/ListMetadataFormats only prove the endpoint responds --
        # they're static. Some DSpace sites answer those fine but have a
        # stale/unbuilt OAI record index, so ListRecords/ListIdentifiers
        # return noRecordsMatch even though the repository has real content
        # (confirmed via ListSets on several "empty" sites). Check for that
        # directly, since it silently defeats a real harvest otherwise.
        try:
            list_ids_response = session.get(
                candidate,
                params={"verb": "ListIdentifiers", "metadataPrefix": "oai_dc"},
                timeout=timeout,
                verify=not ssl_fallback_used,
            )
            if list_ids_response.status_code == 200:
                list_ids_root = ElementTree.fromstring(list_ids_response.text)
                oai_error = list_ids_root.find(f"{OAI_NS}error")
                if oai_error is not None:
                    result.has_records = False
                    result.list_records_error = f"[{oai_error.get('code')}] {oai_error.text}"
                else:
                    result.has_records = True
            else:
                result.list_records_error = f"HTTP {list_ids_response.status_code}"
        except (requests.RequestException, ElementTree.ParseError) as exc:
            result.list_records_error = str(exc)

        return result

    return OaiCheckResult(
        endpoint_tried=candidates[0],
        reachable=False,
        error=attempts[0]["error"] if attempts else None,
        attempts=attempts,
    )


def check_rest_api(
    session: requests.Session, rest_endpoint: str, *, timeout: int
) -> tuple[bool, str | None, bool]:
    response, ssl_fallback_used, error = _request_with_ssl_fallback(
        session, "GET", rest_endpoint, timeout=timeout
    )
    if error is not None:
        return False, error, ssl_fallback_used
    if response.status_code == 200:
        return True, None, ssl_fallback_used
    return False, f"HTTP {response.status_code}", ssl_fallback_used


def check_robots_txt(
    session: requests.Session, repository_url: str, *, timeout: int
) -> dict[str, Any]:
    parsed = urlparse(repository_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = urljoin(origin + "/", "robots.txt")

    response, ssl_fallback_used, error = _request_with_ssl_fallback(
        session, "GET", robots_url, timeout=timeout
    )
    if error is not None:
        return {"url": robots_url, "found": False, "error": error}

    if response.status_code != 200:
        return {"url": robots_url, "found": False, "http_status": response.status_code}

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())

    oai_path = urljoin(origin, "/oai/request")
    server_oai_path = urljoin(origin, "/server/oai/request")

    return {
        "url": robots_url,
        "found": True,
        "ssl_verify_failed": ssl_fallback_used,
        "oai_request_allowed": parser.can_fetch(USER_AGENT, oai_path),
        "server_oai_request_allowed": parser.can_fetch(USER_AGENT, server_oai_path),
        "discover_allowed": parser.can_fetch(USER_AGENT, urljoin(origin, "/discover")),
    }


def check_sitemap(
    session: requests.Session, repository_url: str, *, timeout: int
) -> dict[str, Any]:
    parsed = urlparse(repository_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    found = {}
    for name in ("sitemap_index.xml", "sitemap.xml"):
        url = urljoin(origin + "/", name)
        response, _ssl_fallback_used, error = _request_with_ssl_fallback(
            session, "HEAD", url, timeout=timeout
        )
        if error is not None:
            found[name] = False
            continue
        if response.status_code == 405:
            response, _ssl_fallback_used, error = _request_with_ssl_fallback(
                session, "GET", url, timeout=timeout
            )
            if error is not None:
                found[name] = False
                continue
        found[name] = response.status_code == 200

    return {"origin": origin, **found}


def validate_target(
    session: requests.Session,
    target: RepositoryTarget,
    *,
    timeout: int,
    try_alternates: bool,
    check_rest: bool,
    check_robots: bool,
    check_sitemap_flag: bool,
) -> TargetReport:
    report = TargetReport(
        id=target.id,
        name=target.name,
        group=target.group,
        phase=target.phase,
        declared_status=target.status,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    if target.oai_endpoint:
        oai_result = check_oai(
            session,
            target.oai_endpoint,
            timeout=timeout,
            try_alternates=try_alternates,
        )
        report.oai = asdict(oai_result)

    if check_rest and target.rest_api_endpoint:
        ok, error, ssl_fallback_used = check_rest_api(
            session, target.rest_api_endpoint, timeout=timeout
        )
        report.rest_api_ok = ok
        report.rest_api_error = error
        report.rest_api_ssl_verify_failed = ssl_fallback_used

    if check_robots and target.repository_url:
        report.robots_txt = check_robots_txt(session, target.repository_url, timeout=timeout)

    if check_sitemap_flag and target.repository_url:
        report.sitemap = check_sitemap(session, target.repository_url, timeout=timeout)

    return report


def print_summary(reports: list[TargetReport]) -> None:
    print(f"\n{'ID':<16}{'OAI live':<10}{'Has data':<10}{'Formats':<9}{'REST':<7}{'Robots OK':<11}Notes")
    print("-" * 90)
    for r in reports:
        reachable = bool(r.oai and r.oai.get("reachable"))
        oai_live = "yes" if reachable else "NO"
        if reachable and r.oai.get("ssl_verify_failed"):
            oai_live = "yes*"
        has_records = r.oai.get("has_records") if r.oai else None
        has_data = "-" if has_records is None else ("yes" if has_records else "NO (empty)")
        formats = str(len(r.oai.get("metadata_formats", []))) if reachable else "-"
        rest = "-" if r.rest_api_ok is None else ("yes" if r.rest_api_ok else "NO")
        robots_ok = "-"
        if r.robots_txt and r.robots_txt.get("found"):
            robots_ok = "yes" if r.robots_txt.get("server_oai_request_allowed") or r.robots_txt.get("oai_request_allowed") else "NO"
        note = ""
        if not reachable and r.oai:
            note = (r.oai.get("error") or "")[:50]
        elif reachable and has_records is False:
            note = (r.oai.get("list_records_error") or "")[:50]
        print(f"{r.id:<16}{oai_live:<10}{has_data:<10}{formats:<9}{rest:<7}{robots_ok:<11}{note}")

    live_count = sum(1 for r in reports if r.oai and r.oai.get("reachable"))
    harvestable_now = sum(1 for r in reports if r.oai and r.oai.get("has_records"))
    print(f"\n{live_count}/{len(reports)} targets have a live, reachable OAI-PMH endpoint.")
    print(f"{harvestable_now}/{len(reports)} of those actually return records right now (rest have empty/stale OAI indexes).")
    print("(yes* = reachable but with an invalid/misconfigured TLS certificate -- flag for IT, don't skip.)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate OAI-PMH, REST, robots.txt and sitemap access for repository targets."
    )
    parser.add_argument("--phase", default=None, help="Only validate targets in this phase, e.g. phase_1.")
    parser.add_argument("--ids", default=None, help="Comma-separated target ids to validate. Overrides --phase.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between targets, in seconds.")
    parser.add_argument("--no-alternates", action="store_true", help="Do not retry alternate OAI URL patterns.")
    parser.add_argument("--skip-rest", action="store_true", help="Skip REST API checks.")
    parser.add_argument("--skip-robots", action="store_true", help="Skip robots.txt checks.")
    parser.add_argument("--skip-sitemap", action="store_true", help="Skip sitemap checks.")
    parser.add_argument("--output", type=Path, default=None, help="Report output path (JSON).")
    parser.add_argument("--raw", action="store_true", help="Print the full JSON report to stdout as well.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    all_targets = load_registry()
    if args.ids:
        wanted = {t.strip() for t in args.ids.split(",") if t.strip()}
        targets = [t for t in all_targets if t.id in wanted]
    else:
        targets = harvestable_targets(all_targets, phase=args.phase)

    if not targets:
        print("No matching harvestable targets found.")
        return

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    reports: list[TargetReport] = []
    for i, target in enumerate(targets):
        print(f"[{i + 1}/{len(targets)}] Validating {target.id} ({target.name})...")
        report = validate_target(
            session,
            target,
            timeout=args.timeout,
            try_alternates=not args.no_alternates,
            check_rest=not args.skip_rest,
            check_robots=not args.skip_robots,
            check_sitemap_flag=not args.skip_sitemap,
        )
        reports.append(report)
        if i < len(targets) - 1:
            time.sleep(args.delay)

    print_summary(reports)

    output_path = args.output
    if output_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_REPORT_DIR / f"repository_validation_{timestamp}.json"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_count": len(reports),
        "results": [asdict(r) for r in reports],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved validation report to {output_path}")

    if args.raw:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
