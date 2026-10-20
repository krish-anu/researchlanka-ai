#!/usr/bin/env python3
"""Fetch current OpenAlex works for the verified UoM CSE staff roster."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.openalex_collector import OpenAlexCollector
from src.cse_uom.dataset import load_staff_roster
from src.preprocessing.openalex_normalizer import CSV_COLUMNS, as_list, work_to_row


DEFAULT_ROSTER = PROJECT_ROOT / "data/config/cse_uom_staff.tsv"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "outputs/cse_uom/cse_uom_openalex_staff_publications_2016_2026.csv"
)
DEFAULT_MANIFEST = (
    PROJECT_ROOT / "outputs/cse_uom/cse_uom_openalex_staff_publications_manifest.json"
)
UOM_OPENALEX_ID = "I195740183"


def normalized_openalex_id(value: object) -> str:
    return re.sub(
        r"^https?://openalex\.org/", "", str(value or "").strip(), flags=re.I
    ).strip("/")


def usable_full_name_aliases(aliases: Iterable[str]) -> list[str]:
    usable: list[str] = []
    for alias in aliases:
        if "," in alias:
            continue
        tokens = re.findall(r"[A-Za-z]+", alias)
        long_tokens = [token for token in tokens if len(token) > 1]
        if len(long_tokens) >= 2:
            usable.append(alias)
    return list(dict.fromkeys(usable))


def reconstruct_abstract(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index")
    if not isinstance(inverted, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for token, positions in inverted.items():
        if not isinstance(positions, list):
            continue
        positioned.extend((int(position), str(token)) for position in positions)
    return " ".join(token for _position, token in sorted(positioned))


def author_values(work: dict[str, Any], key: str) -> str:
    values: list[str] = []
    for authorship in as_list(work.get("authorships")):
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        if not isinstance(author, dict):
            continue
        value = author.get(key)
        if value and str(value) not in values:
            values.append(str(value))
    return "; ".join(values)


def keyword_values(work: dict[str, Any]) -> str:
    return "; ".join(
        dict.fromkeys(
            str(keyword["display_name"])
            for keyword in as_list(work.get("keywords"))
            if isinstance(keyword, dict) and keyword.get("display_name")
        )
    )


def iter_pages(
    collector: OpenAlexCollector,
    *,
    filters: list[str],
    per_page: int,
) -> Iterable[dict[str, Any]]:
    if not collector.api_key:
        page = 1
        while True:
            params: dict[str, Any] = {
                "filter": ",".join(filters),
                "page": page,
                "per-page": per_page,
            }
            if collector.email:
                params["mailto"] = collector.email
            response = collector.session.get(
                f"{collector.base_url}/works",
                params=params,
                timeout=collector.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            results = as_list(payload.get("results"))
            if not results:
                return
            for work in results:
                if isinstance(work, dict):
                    yield work
            meta = payload.get("meta")
            total = int(meta.get("count") or 0) if isinstance(meta, dict) else 0
            if page * per_page >= total:
                return
            if page * per_page >= 10_000:
                raise RuntimeError(
                    "OpenAlex basic paging is limited to 10,000 results; provide --api-key."
                )
            page += 1

    cursor: str | None = "*"
    seen_cursors: set[str] = set()
    while cursor:
        if cursor in seen_cursors:
            raise RuntimeError(f"OpenAlex cursor repeated: {cursor}")
        seen_cursors.add(cursor)
        response = collector.fetch_works(
            filters=filters,
            cursor=cursor,
            per_page=per_page,
        )
        for work in as_list(response.get("results")):
            if isinstance(work, dict):
                yield work
        meta = response.get("meta")
        cursor = meta.get("next_cursor") if isinstance(meta, dict) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--year-min", type=int, default=2016)
    parser.add_argument("--year-max", type=int, default=date.today().year)
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--email")
    parser.add_argument("--api-key")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    roster = load_staff_roster(args.roster)
    author_ids = sorted(
        {
            normalized_openalex_id(value)
            for member in roster
            for value in member.openalex_author_id.split("|")
            if normalized_openalex_id(value)
        }
    )
    if not author_ids:
        raise SystemExit("The CSE roster has no verified OpenAlex author IDs.")

    collector = OpenAlexCollector(email=args.email, api_key=args.api_key)
    filters = [
        f"authorships.author.id:{'|'.join(author_ids)}",
        f"publication_year:{args.year_min}-{args.year_max}",
    ]
    works_by_id: dict[str, dict[str, Any]] = {}
    for work in iter_pages(collector, filters=filters, per_page=args.per_page):
        work_id = str(work.get("id") or "").strip()
        if work_id:
            works_by_id[work_id] = work

    fallback_queries: dict[str, list[str]] = {}
    for member in roster:
        if member.openalex_author_id:
            continue
        aliases = usable_full_name_aliases(member.aliases)
        fallback_queries[member.researcher_id] = aliases
        for alias in aliases:
            fallback_filters = [
                f"raw_author_name.search:{alias}",
                f"authorships.institutions.id:{UOM_OPENALEX_ID}",
                f"publication_year:{args.year_min}-{args.year_max}",
            ]
            for work in iter_pages(
                collector,
                filters=fallback_filters,
                per_page=args.per_page,
            ):
                work_id = str(work.get("id") or "").strip()
                if work_id:
                    works_by_id[work_id] = work

    rows: list[dict[str, Any]] = []
    for work in works_by_id.values():
        row = work_to_row(work)
        row.update(
            {
                "abstract": reconstruct_abstract(work),
                "keywords": keyword_values(work),
                "author_openalex_ids": author_values(work, "id"),
                "author_orcids": author_values(work, "orcid"),
                "source_dataset": "openalex_cse_staff_fresh",
                "source_record_id": work.get("id") or "",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        rows.append(row)

    rows.sort(
        key=lambda row: (
            int(row.get("publication_year") or 0),
            str(row.get("title") or "").casefold(),
        )
    )
    columns = [
        *CSV_COLUMNS,
        "abstract",
        "keywords",
        "author_openalex_ids",
        "author_orcids",
        "source_dataset",
        "source_record_id",
        "fetched_at",
    ]
    columns = list(dict.fromkeys(columns))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "OpenAlex API",
        "year_min": args.year_min,
        "year_max": args.year_max,
        "roster_count": len(roster),
        "resolved_openalex_author_count": len(author_ids),
        "unresolved_researcher_ids": [
            member.researcher_id for member in roster if not member.openalex_author_id
        ],
        "unresolved_full_name_fallback_queries": fallback_queries,
        "fetched_distinct_work_count": len(rows),
        "filters": filters,
        "output": str(args.output),
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
