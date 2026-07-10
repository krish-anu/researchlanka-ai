"""Convert OpenAlex works JSONL into a flat CSV file.

The converter streams one JSON line at a time, so it can handle large files.

Example:
    python scripts/convert_openalex_jsonl_to_csv.py \
        ~/Desktop/researchlanka-data/lk_works.jsonl \
        ~/Desktop/researchlanka-data/lk_works.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "openalex_id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "language",
    "cited_by_count",
    "referenced_works_count",
    "fwci",
    "is_retracted",
    "is_paratext",
    "source_id",
    "source_name",
    "source_type",
    "publisher",
    "journal_issn_l",
    "volume",
    "issue",
    "first_page",
    "last_page",
    "is_oa",
    "oa_status",
    "oa_url",
    "landing_page_url",
    "pdf_url",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
    "keywords",
    "concepts",
    "author_count",
    "authors",
    "sri_lankan_authors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "countries_count",
    "institutions_count",
    "funders",
    "sdgs",
    "created_date",
    "updated_date",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert OpenAlex works JSONL to CSV.")
    parser.add_argument("input", type=Path, help="Input JSONL path.")
    parser.add_argument("output", type=Path, help="Output CSV path.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of records to convert for testing.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10000,
        help="Print progress after this many records. Default: 10000",
    )
    return parser.parse_args()


def get_nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def unique_join(values: list[Any], separator: str = "; ") -> str:
    seen: set[str] = set()
    cleaned: list[str] = []

    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)

    return separator.join(cleaned)


def list_display_names(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return unique_join(
        [item.get("display_name") for item in items if isinstance(item, dict)]
    )


def authorships(work: dict[str, Any]) -> list[dict[str, Any]]:
    value = work.get("authorships")
    return value if isinstance(value, list) else []


def institutions_from_authorships(work: dict[str, Any]) -> list[dict[str, Any]]:
    institutions: list[dict[str, Any]] = []
    for authorship in authorships(work):
        for institution in authorship.get("institutions", []):
            if isinstance(institution, dict):
                institutions.append(institution)
    return institutions


def countries_from_authorships(work: dict[str, Any]) -> str:
    countries: list[str] = []
    for authorship in authorships(work):
        value = authorship.get("countries")
        if isinstance(value, list):
            countries.extend(value)
    return unique_join(countries)


def author_names(work: dict[str, Any]) -> str:
    names: list[str] = []
    for authorship in authorships(work):
        author = authorship.get("author")
        if isinstance(author, dict):
            display_name = author.get("display_name")
            if display_name is not None:
                names.append(display_name)
        else:
            raw_name = authorship.get("raw_author_name")
            if raw_name is not None:
                names.append(raw_name)
    return unique_join(names)


def sri_lankan_author_names(work: dict[str, Any]) -> str:
    names: list[str] = []
    for authorship in authorships(work):
        countries = authorship.get("countries")
        if not isinstance(countries, list) or "LK" not in countries:
            continue

        author = authorship.get("author")
        if isinstance(author, dict):
            display_name = author.get("display_name")
            if display_name is not None:
                names.append(display_name)
        else:
            raw_name = authorship.get("raw_author_name")
            if raw_name is not None:
                names.append(raw_name)

    return unique_join(names)


def sri_lankan_institution_names(work: dict[str, Any]) -> str:
    names = [
        institution.get("display_name")
        for institution in institutions_from_authorships(work)
        if institution.get("country_code") == "LK"
    ]
    return unique_join(names)


def work_to_row(work: dict[str, Any]) -> dict[str, Any]:
    source = get_nested(work, "primary_location", "source") or {}
    biblio = work.get("biblio") or {}
    open_access = work.get("open_access") or {}
    primary_topic = work.get("primary_topic") or {}
    primary_location = work.get("primary_location") or {}

    if not isinstance(source, dict):
        source = {}
    if not isinstance(biblio, dict):
        biblio = {}
    if not isinstance(open_access, dict):
        open_access = {}
    if not isinstance(primary_topic, dict):
        primary_topic = {}
    if not isinstance(primary_location, dict):
        primary_location = {}

    institutions = institutions_from_authorships(work)

    return {
        "openalex_id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title") or work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "language": work.get("language"),
        "cited_by_count": work.get("cited_by_count"),
        "referenced_works_count": work.get("referenced_works_count"),
        "fwci": work.get("fwci"),
        "is_retracted": work.get("is_retracted"),
        "is_paratext": work.get("is_paratext"),
        "source_id": source.get("id"),
        "source_name": source.get("display_name"),
        "source_type": source.get("type"),
        "publisher": source.get("host_organization_name"),
        "journal_issn_l": source.get("issn_l"),
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "first_page": biblio.get("first_page"),
        "last_page": biblio.get("last_page"),
        "is_oa": open_access.get("is_oa"),
        "oa_status": open_access.get("oa_status"),
        "oa_url": open_access.get("oa_url"),
        "landing_page_url": primary_location.get("landing_page_url"),
        "pdf_url": primary_location.get("pdf_url"),
        "primary_topic": primary_topic.get("display_name"),
        "primary_subfield": get_nested(primary_topic, "subfield", "display_name"),
        "primary_field": get_nested(primary_topic, "field", "display_name"),
        "primary_domain": get_nested(primary_topic, "domain", "display_name"),
        "keywords": list_display_names(work.get("keywords")),
        "concepts": list_display_names(work.get("concepts")),
        "author_count": len(authorships(work)),
        "authors": author_names(work),
        "sri_lankan_authors": sri_lankan_author_names(work),
        "institutions": unique_join(
            [institution.get("display_name") for institution in institutions]
        ),
        "sri_lankan_institutions": sri_lankan_institution_names(work),
        "countries": countries_from_authorships(work),
        "countries_count": work.get("countries_distinct_count"),
        "institutions_count": work.get("institutions_distinct_count"),
        "funders": list_display_names(work.get("funders")),
        "sdgs": list_display_names(work.get("sustainable_development_goals")),
        "created_date": work.get("created_date"),
        "updated_date": work.get("updated_date"),
    }


def convert_jsonl_to_csv(
    input_path: Path,
    output_path: Path,
    *,
    limit: int | None = None,
    progress_every: int = 10000,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with input_path.expanduser().open("r", encoding="utf-8") as input_file:
        with output_path.expanduser().open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=CSV_COLUMNS)
            writer.writeheader()

            for line_number, line in enumerate(input_file, start=1):
                if limit is not None and total >= limit:
                    break
                if not line.strip():
                    continue

                try:
                    work = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error

                writer.writerow(work_to_row(work))
                total += 1

                if progress_every > 0 and total % progress_every == 0:
                    print(f"Converted {total} records...")

    return total


def main() -> None:
    args = parse_args()
    total = convert_jsonl_to_csv(
        args.input,
        args.output,
        limit=args.limit,
        progress_every=args.progress_every,
    )
    print(f"Saved {total} records to {args.output.expanduser()}")


if __name__ == "__main__":
    main()
