"""Kaggle-ready OpenAlex collector for Sri Lankan-affiliated works.

Run in Kaggle:
    python kaggle_collect_openalex_sri_lanka.py --max-records 1000

This script keeps a work when at least one authorship has a Sri Lankan
affiliation in OpenAlex. OpenAlex provides affiliation countries, not author
nationality, so "Sri Lankan author" here means an author with country code LK
or an LK institution in that work's authorship metadata.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import requests


OPENALEX_BASE_URL = "https://api.openalex.org"
SRI_LANKA_COUNTRY_CODE = "LK"
LK_AUTHORSHIP_FILTER = "authorships.institutions.country_code:LK"
DEFAULT_OUTPUT_DIR = Path("/kaggle/working")
DEFAULT_JSONL_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.jsonl"
DEFAULT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.csv"

CSV_COLUMNS = [
    "openalex_id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "cited_by_count",
    "author_count",
    "authors",
    "sri_lankan_authors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "source_name",
    "publisher",
    "is_oa",
    "landing_page_url",
    "pdf_url",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect OpenAlex works with at least one Sri Lankan affiliation."
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=DEFAULT_JSONL_OUTPUT,
        help=f"Raw JSONL output path. Default: {DEFAULT_JSONL_OUTPUT}",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=DEFAULT_CSV_OUTPUT,
        help=f"Flat CSV output path. Default: {DEFAULT_CSV_OUTPUT}",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Only save JSONL; do not save the flat CSV.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[LK_AUTHORSHIP_FILTER],
        help=(
            "OpenAlex filter. Default: authorships.institutions.country_code:LK. "
            "Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="Optional first publication year, for example 2015.",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Optional final publication year, for example 2025.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Records per OpenAlex request. Default: 100",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional safety limit for testing before collecting everything.",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Optional email for OpenAlex request metadata.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENALEX_API_KEY"),
        help="Optional OpenAlex API key. Defaults to OPENALEX_API_KEY.",
    )
    args, _unknown = parser.parse_known_args()
    return args


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_join(values: list[Any], separator: str = "; ") -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return separator.join(output)


def authorships(work: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        authorship
        for authorship in as_list(work.get("authorships"))
        if isinstance(authorship, dict)
    ]


def country_codes_from_authorship(authorship: dict[str, Any]) -> set[str]:
    codes = {
        str(country).upper()
        for country in as_list(authorship.get("countries"))
        if country
    }
    for institution in as_list(authorship.get("institutions")):
        if isinstance(institution, dict) and institution.get("country_code"):
            codes.add(str(institution["country_code"]).upper())
    return codes


def is_sri_lankan_authorship(authorship: dict[str, Any]) -> bool:
    return SRI_LANKA_COUNTRY_CODE in country_codes_from_authorship(authorship)


def has_sri_lankan_author(work: dict[str, Any]) -> bool:
    if any(is_sri_lankan_authorship(authorship) for authorship in authorships(work)):
        return True

    for institution in as_list(work.get("institutions")):
        if (
            isinstance(institution, dict)
            and str(institution.get("country_code", "")).upper()
            == SRI_LANKA_COUNTRY_CODE
        ):
            return True

    return False


def author_name(authorship: dict[str, Any]) -> str | None:
    author = authorship.get("author")
    if isinstance(author, dict) and author.get("display_name"):
        return str(author["display_name"])
    if authorship.get("raw_author_name"):
        return str(authorship["raw_author_name"])
    return None


def author_names(work: dict[str, Any], *, sri_lankan_only: bool = False) -> str:
    names: list[str] = []
    for authorship in authorships(work):
        if sri_lankan_only and not is_sri_lankan_authorship(authorship):
            continue
        names.append(author_name(authorship))
    return unique_join(names)


def institution_names(work: dict[str, Any], *, sri_lankan_only: bool = False) -> str:
    names: list[str] = []
    for authorship in authorships(work):
        for institution in as_list(authorship.get("institutions")):
            if not isinstance(institution, dict):
                continue
            country_code = str(institution.get("country_code", "")).upper()
            if sri_lankan_only and country_code != SRI_LANKA_COUNTRY_CODE:
                continue
            names.append(institution.get("display_name"))
    return unique_join(names)


def country_codes(work: dict[str, Any]) -> str:
    codes: list[str] = []
    for authorship in authorships(work):
        codes.extend(sorted(country_codes_from_authorship(authorship)))
    return unique_join(codes)


def get_nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def work_to_row(work: dict[str, Any]) -> dict[str, Any]:
    source = get_nested(work, "primary_location", "source") or {}
    primary_location = work.get("primary_location") or {}
    open_access = work.get("open_access") or {}

    if not isinstance(source, dict):
        source = {}
    if not isinstance(primary_location, dict):
        primary_location = {}
    if not isinstance(open_access, dict):
        open_access = {}

    return {
        "openalex_id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title") or work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "author_count": len(authorships(work)),
        "authors": author_names(work),
        "sri_lankan_authors": author_names(work, sri_lankan_only=True),
        "institutions": institution_names(work),
        "sri_lankan_institutions": institution_names(work, sri_lankan_only=True),
        "countries": country_codes(work),
        "source_name": source.get("display_name"),
        "publisher": source.get("host_organization_name"),
        "is_oa": open_access.get("is_oa"),
        "landing_page_url": primary_location.get("landing_page_url"),
        "pdf_url": primary_location.get("pdf_url"),
    }


def build_filters(args: argparse.Namespace) -> list[str]:
    filters = list(args.filter)

    if args.from_year is not None or args.to_year is not None:
        start = args.from_year if args.from_year is not None else "*"
        end = args.to_year if args.to_year is not None else "*"
        filters.append(f"publication_year:{start}-{end}")

    return filters


def fetch_works(
    *,
    filters: list[str],
    cursor: str,
    per_page: int,
    email: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "filter": ",".join(filters),
        "cursor": cursor,
        "per-page": per_page,
    }
    if email:
        params["mailto"] = email
    if api_key:
        params["api_key"] = api_key

    response = requests.get(
        f"{OPENALEX_BASE_URL}/works",
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def iter_sri_lankan_works(args: argparse.Namespace):
    filters = build_filters(args)
    cursor = "*"
    saved = 0

    while cursor:
        response = fetch_works(
            filters=filters,
            cursor=cursor,
            per_page=args.per_page,
            email=args.email,
            api_key=args.api_key,
        )
        results = as_list(response.get("results"))
        if not results:
            break

        for work in results:
            if args.max_records is not None and saved >= args.max_records:
                return
            if not isinstance(work, dict) or not has_sri_lankan_author(work):
                continue

            saved += 1
            yield work

        cursor = response.get("meta", {}).get("next_cursor")


def main() -> None:
    args = parse_args()
    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_csv:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    csv_file = None
    writer = None

    try:
        if not args.no_csv:
            csv_file = args.csv_output.open("w", encoding="utf-8", newline="")
            writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
            writer.writeheader()

        with args.jsonl_output.open("w", encoding="utf-8") as jsonl_file:
            for work in iter_sri_lankan_works(args):
                jsonl_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                if writer is not None:
                    writer.writerow(work_to_row(work))
                total += 1
                if total % 100 == 0:
                    print(f"Saved {total:,} Sri Lankan-affiliated works...")
    finally:
        if csv_file is not None:
            csv_file.close()

    print(f"Saved {total:,} records to {args.jsonl_output}")
    if not args.no_csv:
        print(f"Saved flat CSV to {args.csv_output}")


if __name__ == "__main__":
    main()
