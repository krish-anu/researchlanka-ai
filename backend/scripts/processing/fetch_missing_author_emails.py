"""Fetch missing author emails from publication landing pages.

The input is expected to be one of the slim publication exports with an
``author_emails`` column. Existing emails are preserved. For rows missing
emails, the script fetches the record URL, extracts email-like strings from the
HTML text, and writes a new CSV with provenance columns for the fetch result.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

import requests


csv.field_size_limit(sys.maxsize)

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,24})(?![A-Za-z0-9._%+-])"
)
EMAIL_BYTES_RE = re.compile(
    rb"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,24})(?![A-Za-z0-9._%+-])"
)
EMAIL_DOMAIN_RE = re.compile(r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}$")
OBFUSCATED_EMAIL_RE = re.compile(
    r"([A-Za-z0-9._%+-]{1,64})\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\bat\b)\s*"
    r"([A-Za-z0-9-]+(?:(?:\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\bdot\b)\s*|\.)[A-Za-z0-9-]+)+)",
    re.IGNORECASE,
)
DOT_TOKEN_RE = re.compile(r"(?:\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\bdot\b)\s*|\.)", re.IGNORECASE)
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next((parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()), Path.cwd())
DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "paper_title_venue_year_authors_emails_institute_available_2016_2026.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "paper_title_venue_year_authors_emails_institute_available_2016_2026_fetched_emails.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "paper_title_venue_year_authors_emails_institute_available_2016_2026_fetched_emails_summary.csv"
)
DEFAULT_METADATA_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_2016_2026.csv"
DEFAULT_USER_AGENT = "researchlanka-email-fetcher/0.1 (metadata quality audit; contact: no-reply@local)"
DEFAULT_URL_COLUMNS = ("url", "pdf_url")
DEFAULT_METADATA_URL_COLUMNS = ("url", "pdf_url")
MAX_RESPONSE_BYTES = 2_500_000

SKIP_HOSTS = {
    "doi.org",
    "dx.doi.org",
}
REPOSITORY_HOST_HINTS = (
    ".lib.",
    "repository.",
    "repo.",
    "archive.",
    "rda.",
    "ir.",
    "dl.",
)
TRAILING_EMAIL_PUNCTUATION = ".,;:) ]}\\\"'"
FALSE_POSITIVE_DOMAINS = {
    "example.com",
    "email.com",
}
FALSE_POSITIVE_TLDS = {
    "aspx",
    "gif",
    "htm",
    "html",
    "jpeg",
    "jpg",
    "jsp",
    "pdf",
    "php",
    "png",
    "txt",
    "xml",
}
FALSE_POSITIVE_LOCAL_PARTS = {
    "admin",
    "administrator",
    "contact",
    "editor",
    "help",
    "helpdesk",
    "info",
    "journal",
    "librarian",
    "library",
    "mail",
    "no-reply",
    "noreply",
    "repository",
    "support",
    "webmaster",
}


@dataclass(frozen=True)
class UrlCandidate:
    url: str
    source: str


@dataclass(frozen=True)
class FetchJob:
    row_index: int
    candidates: tuple[UrlCandidate, ...]


@dataclass(frozen=True)
class FetchResult:
    row_index: int
    url: str
    emails: tuple[str, ...]
    status: str
    method: str


def clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def split_values(value: object) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [part.strip() for part in text.split(";") if clean(part)]


def unique_join(values: Iterable[str]) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = clean(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return "; ".join(output)


def parse_column_names(values: list[str] | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        return default
    columns: list[str] = []
    for value in values:
        columns.extend(part.strip() for part in value.split(",") if part.strip())
    return tuple(columns) if columns else default


def normalize_email(value: str) -> str | None:
    email = value.strip(TRAILING_EMAIL_PUNCTUATION).casefold()
    if email.count("@") != 1 or ".." in email:
        return None
    local, domain = email.rsplit("@", 1)    
    if not local or not domain or "." not in domain:
        return None
    if not EMAIL_DOMAIN_RE.match(domain):
        return None
    if local in FALSE_POSITIVE_LOCAL_PARTS:
        return None
    if domain.rsplit(".", 1)[-1] in FALSE_POSITIVE_TLDS:
        return None
    if domain in FALSE_POSITIVE_DOMAINS or domain.endswith(".example.com"):
        return None
    return email


def deobfuscate_domain(value: str) -> str:
    parts = [part.strip(" -_") for part in DOT_TOKEN_RE.split(value) if part.strip(" -_")]
    return ".".join(parts)


def searchable_text(value: str) -> str:
    return html.unescape(unquote(value))


def extract_emails(text: str) -> tuple[str, ...]:
    emails: list[str] = []
    prepared = searchable_text(text)
    for match in EMAIL_RE.findall(prepared):
        if email := normalize_email(match):
            emails.append(email)
    for local, domain in OBFUSCATED_EMAIL_RE.findall(prepared):
        if email := normalize_email(f"{local}@{deobfuscate_domain(domain)}"):
            emails.append(email)
    return tuple(split_values(unique_join(emails)))


def extract_emails_from_bytes(data: bytes) -> tuple[str, ...]:
    emails: list[str] = []
    for match in EMAIL_BYTES_RE.findall(data):
        if email := normalize_email(match.decode("ascii", errors="ignore")):
            emails.append(email)
    text = data.decode("latin-1", errors="ignore").replace("\x00", "")
    emails.extend(extract_emails(text))
    return tuple(split_values(unique_join(emails)))


def is_pdf_url(url: str) -> bool:
    return urlparse(url).path.casefold().endswith(".pdf")


def is_fetch_candidate(
    url: str,
    *,
    include_all_hosts: bool,
    include_doi_hosts: bool,
    host_contains: tuple[str, ...],
) -> bool:
    if not url:
        return False
    parts = urlparse(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return False
    host = parts.netloc.casefold()
    if host_contains and not any(fragment in host for fragment in host_contains):
        return False
    if host in SKIP_HOSTS:
        return include_doi_hosts
    if include_all_hosts:
        return True
    return any(hint in host for hint in REPOSITORY_HOST_HINTS)


def expanded_candidate_urls(candidate: UrlCandidate) -> list[UrlCandidate]:
    candidates = [candidate]
    parts = urlparse(candidate.url)
    if "/handle/" in parts.path and not parts.query:
        candidates.append(UrlCandidate(f"{candidate.url}?show=full", f"{candidate.source}:dspace_full"))
    return candidates


def read_response_bytes(response: requests.Response, max_bytes: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(chunk_size=65_536):
        if not chunk:
            continue
        remaining = max_bytes - len(body)
        if remaining <= 0:
            break
        body.extend(chunk[:remaining])
        if len(body) >= max_bytes:
            break
    return bytes(body)


def response_kind(url: str, content_type: str, candidate_source: str) -> str:
    normalized_type = content_type.casefold()
    if "pdf" in normalized_type or is_pdf_url(url) or candidate_source == "pdf_url":
        return "pdf"
    if any(kind in normalized_type for kind in ("text", "html", "xml", "json")):
        return "text"
    return "binary"


def decode_response_text(response: requests.Response, body: bytes) -> str:
    encoding = response.encoding or "utf-8"
    return body.decode(encoding, errors="ignore")


def fetch_one(
    job: FetchJob,
    *,
    timeout: float,
    user_agent: str,
    pause_seconds: float,
    max_bytes: int,
) -> FetchResult:
    if pause_seconds > 0:
        time.sleep(pause_seconds)

    last_result = FetchResult(job.row_index, "", (), "not_fetched", "")
    for candidate in job.candidates:
        if pause_seconds > 0 and last_result.url:
            time.sleep(pause_seconds)
        for candidate_url in expanded_candidate_urls(candidate):
            url = candidate_url.url
            source = candidate_url.source
            try:
                response = requests.get(
                    url,
                    headers={
                        "User-Agent": user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.8,*/*;q=0.2",
                    },
                    timeout=timeout,
                    allow_redirects=True,
                    stream=True,
                )
            except requests.RequestException as exc:
                last_result = FetchResult(job.row_index, url, (), f"fetch_error:{exc.__class__.__name__}", source)
                continue

            try:
                content_type = response.headers.get("content-type", "").casefold()
                if response.status_code >= 400:
                    last_result = FetchResult(job.row_index, url, (), f"http_{response.status_code}", source)
                    continue

                kind = response_kind(response.url, content_type, source)
                if kind == "binary":
                    last_result = FetchResult(
                        job.row_index,
                        response.url,
                        (),
                        f"skipped_content_type:{content_type[:60]}",
                        source,
                    )
                    continue

                try:
                    body = read_response_bytes(response, max_bytes)
                except requests.RequestException as exc:
                    last_result = FetchResult(
                        job.row_index,
                        response.url,
                        (),
                        f"fetch_error:{exc.__class__.__name__}",
                        source,
                    )
                    continue
                if kind == "pdf":
                    emails = extract_emails_from_bytes(body)
                else:
                    emails = extract_emails(decode_response_text(response, body))
                last_result = FetchResult(
                    job.row_index,
                    response.url,
                    emails,
                    "fetched_with_email" if emails else "fetched_no_email",
                    f"{source}:{kind}",
                )
                if emails:
                    return last_result
            finally:
                response.close()
    return last_result


def report_progress(done: int, total: int, *, every: int) -> None:
    if every <= 0:
        return
    if done == total or done % every == 0:
        print(f"processed {done}/{total}", flush=True)


def normalize_doi(value: object) -> str:
    text = clean(value).casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if text.startswith(prefix):
            return text.removeprefix(prefix)
    return text


def normalize_url_key(value: object) -> str:
    return clean(value).rstrip("/").casefold()


def row_match_keys(row: dict[str, str]) -> tuple[str, ...]:
    keys: list[str] = []
    if doi := normalize_doi(row.get("doi")):
        keys.append(f"doi:{doi}")
    for source_record_id in split_values(row.get("source_record_id")):
        keys.append(f"source_record_id:{source_record_id.casefold()}")
    for url in split_values(row.get("url")):
        keys.append(f"url:{normalize_url_key(url)}")
    return tuple(dict.fromkeys(keys))


def load_metadata_url_candidates(
    rows: list[dict[str, str]],
    metadata_csv: Path | None,
    *,
    metadata_url_columns: tuple[str, ...],
) -> dict[int, list[UrlCandidate]]:
    if not metadata_csv or not metadata_csv.exists():
        return {}

    lookup: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if clean(row.get("author_emails")):
            continue
        for key in row_match_keys(row):
            lookup.setdefault(key, []).append(index)

    if not lookup:
        return {}

    candidates: dict[int, list[UrlCandidate]] = {}
    with metadata_csv.open(newline="", encoding="utf-8", errors="replace") as metadata_file:
        reader = csv.DictReader(metadata_file)
        for metadata_row in reader:
            matching_indices: set[int] = set()
            for key in row_match_keys(metadata_row):
                matching_indices.update(lookup.get(key, ()))
            if not matching_indices:
                continue
            for column in metadata_url_columns:
                for url in split_values(metadata_row.get(column)):
                    for index in matching_indices:
                        candidates.setdefault(index, []).append(UrlCandidate(url, column))
    return candidates


def append_candidate(
    candidates: list[UrlCandidate],
    seen_urls: set[str],
    candidate: UrlCandidate,
    *,
    include_all_hosts: bool,
    include_doi_hosts: bool,
    host_contains: tuple[str, ...],
) -> None:
    url = clean(candidate.url)
    if not is_fetch_candidate(
        url,
        include_all_hosts=include_all_hosts,
        include_doi_hosts=include_doi_hosts,
        host_contains=host_contains,
    ):
        return
    normalized = normalize_url_key(url)
    if normalized in seen_urls:
        return
    seen_urls.add(normalized)
    candidates.append(UrlCandidate(url, candidate.source))


def row_url_candidates(
    row: dict[str, str],
    *,
    url_columns: tuple[str, ...],
    extra_candidates: list[UrlCandidate],
    try_doi_urls: bool,
) -> list[UrlCandidate]:
    candidates: list[UrlCandidate] = []
    for column in url_columns:
        for url in split_values(row.get(column)):
            candidates.append(UrlCandidate(url, column))
    candidates.extend(extra_candidates)
    if try_doi_urls and (doi := normalize_doi(row.get("doi"))):
        candidates.append(UrlCandidate(f"https://doi.org/{doi}", "doi"))
    return candidates


def build_jobs(
    rows: list[dict[str, str]],
    *,
    url_columns: tuple[str, ...],
    extra_url_candidates: dict[int, list[UrlCandidate]],
    include_all_hosts: bool,
    include_doi_hosts: bool,
    host_contains: tuple[str, ...],
    try_doi_urls: bool,
    limit: int | None,
) -> list[FetchJob]:
    jobs: list[FetchJob] = []
    for index, row in enumerate(rows):
        if clean(row.get("author_emails")):
            continue
        candidates: list[UrlCandidate] = []
        seen_urls: set[str] = set()
        for candidate in row_url_candidates(
            row,
            url_columns=url_columns,
            extra_candidates=extra_url_candidates.get(index, []),
            try_doi_urls=try_doi_urls,
        ):
            append_candidate(
                candidates,
                seen_urls,
                candidate,
                include_all_hosts=include_all_hosts,
                include_doi_hosts=include_doi_hosts,
                host_contains=host_contains,
            )
        if not candidates:
            continue
        jobs.append(FetchJob(index, tuple(candidates)))
        if limit is not None and len(jobs) >= limit:
            break
    return jobs


def write_summary(path: Path, rows: list[dict[str, str]], jobs: list[FetchJob], results: list[FetchResult]) -> None:
    status_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    fetched_email_rows = 0
    fetched_email_values = 0
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        if result.method:
            method_counts[result.method] = method_counts.get(result.method, 0) + 1
        if result.emails:
            fetched_email_rows += 1
            fetched_email_values += len(result.emails)

    rows_with_email = sum(1 for row in rows if clean(row.get("author_emails")))
    with path.open("w", newline="", encoding="utf-8") as summary_file:
        writer = csv.writer(summary_file)
        writer.writerow(["metric", "value"])
        writer.writerow(["rows", len(rows)])
        writer.writerow(["fetch_candidate_rows", len(jobs)])
        writer.writerow(["fetch_candidate_urls", sum(len(job.candidates) for job in jobs)])
        writer.writerow(["fetched_email_rows_added", fetched_email_rows])
        writer.writerow(["fetched_email_values_added", fetched_email_values])
        writer.writerow(["rows_with_author_emails_after_fetch", rows_with_email])
        writer.writerow(["author_email_coverage_after_fetch_percent", f"{rows_with_email / len(rows) * 100:.2f}" if rows else "0.00"])
        for status, count in sorted(status_counts.items()):
            writer.writerow([f"status_{status}", count])
        for method, count in sorted(method_counts.items()):
            writer.writerow([f"method_{method}", count])


def process(
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
    *,
    metadata_csv: Path | None,
    url_columns: tuple[str, ...],
    metadata_url_columns: tuple[str, ...],
    include_all_hosts: bool,
    include_doi_hosts: bool,
    host_contains: tuple[str, ...],
    try_doi_urls: bool,
    limit: int | None,
    workers: int,
    timeout: float,
    pause_seconds: float,
    user_agent: str,
    max_bytes: int,
    progress_every: int,
) -> None:
    with input_csv.open(newline="", encoding="utf-8", errors="replace") as input_file:
        reader = csv.DictReader(input_file)
        rows = list(reader)
        input_fields = reader.fieldnames or []

    extra_url_candidates = load_metadata_url_candidates(
        rows,
        metadata_csv,
        metadata_url_columns=metadata_url_columns,
    )
    jobs = build_jobs(
        rows,
        url_columns=url_columns,
        extra_url_candidates=extra_url_candidates,
        include_all_hosts=include_all_hosts,
        include_doi_hosts=include_doi_hosts,
        host_contains=host_contains,
        try_doi_urls=try_doi_urls,
        limit=limit,
    )
    results: list[FetchResult] = []

    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    fetch_one,
                    job,
                    timeout=timeout,
                    user_agent=user_agent,
                    pause_seconds=pause_seconds,
                    max_bytes=max_bytes,
                )
                for job in jobs
            ]
            done = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                done += 1
                report_progress(done, len(jobs), every=progress_every)
                if result.emails:
                    row = rows[result.row_index]
                    existing = split_values(row.get("author_emails"))
                    row["author_emails"] = unique_join([*existing, *result.emails])
                    row["email_fetch_source_url"] = result.url
                    row["email_fetch_status"] = result.status
                    row["email_fetch_method"] = result.method
                else:
                    rows[result.row_index]["email_fetch_status"] = result.status
                    rows[result.row_index]["email_fetch_source_url"] = result.url
                    rows[result.row_index]["email_fetch_method"] = result.method

    output_fields = [*input_fields]
    for extra_field in ["email_fetch_status", "email_fetch_source_url", "email_fetch_method"]:
        if extra_field not in output_fields:
            output_fields.append(extra_field)

    with output_csv.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)

    write_summary(summary_csv, rows, jobs, results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument(
        "--metadata-csv",
        type=Path,
        default=DEFAULT_METADATA_CSV,
        help="Optional richer CSV to join additional URL candidates from, such as pdf_url.",
    )
    parser.add_argument("--no-metadata-csv", action="store_true", help="Do not join URL candidates from a metadata CSV.")
    parser.add_argument(
        "--url-column",
        action="append",
        default=None,
        help="URL column to fetch from the input CSV. May be comma-separated or repeated. Defaults to url,pdf_url.",
    )
    parser.add_argument(
        "--metadata-url-column",
        action="append",
        default=None,
        help="URL column to fetch from --metadata-csv. May be comma-separated or repeated. Defaults to url,pdf_url.",
    )
    parser.add_argument("--include-all-hosts", action="store_true", help="Fetch non-DOI URLs outside repository-like hosts.")
    parser.add_argument("--include-doi-hosts", action="store_true", help="Allow doi.org URLs to resolve to publisher pages.")
    parser.add_argument("--try-doi-urls", action="store_true", help="Generate a https://doi.org/{doi} candidate when DOI is present.")
    parser.add_argument(
        "--host-contains",
        action="append",
        default=[],
        help="Only fetch hosts containing this text. May be supplied more than once.",
    )
    parser.add_argument("--limit", type=int, default=500, help="Maximum missing-email rows to fetch. Use 0 for no limit.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--pause-seconds", type=float, default=0.0)
    parser.add_argument("--max-bytes", type=int, default=MAX_RESPONSE_BYTES, help="Maximum bytes to read per fetched URL.")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limit = None if args.limit == 0 else args.limit
    metadata_csv = None if args.no_metadata_csv else args.metadata_csv
    process(
        args.input_csv,
        args.output_csv,
        args.summary_csv,
        metadata_csv=metadata_csv,
        url_columns=parse_column_names(args.url_column, DEFAULT_URL_COLUMNS),
        metadata_url_columns=parse_column_names(args.metadata_url_column, DEFAULT_METADATA_URL_COLUMNS),
        include_all_hosts=args.include_all_hosts,
        include_doi_hosts=args.include_doi_hosts,
        host_contains=tuple(fragment.casefold() for fragment in args.host_contains),
        try_doi_urls=args.try_doi_urls,
        limit=limit,
        workers=max(args.workers, 1),
        timeout=args.timeout,
        pause_seconds=max(args.pause_seconds, 0),
        user_agent=args.user_agent,
        max_bytes=max(args.max_bytes, 1),
        progress_every=args.progress_every,
    )


if __name__ == "__main__":
    main()
