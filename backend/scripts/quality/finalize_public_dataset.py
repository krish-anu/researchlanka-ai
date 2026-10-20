"""Build the adjudicated, distinct-work ResearchLanka public release.

The script consumes the 3,706-row release candidate plus the two audit
worksheets produced from it. It keeps a complete decision trail while applying
three conservative corrections:

* exclude records supported only by known ambiguous Sri Lankan institution
  aliases;
* exclude the adjudicated non-AI Uzbek noun-classification record;
* consolidate exact-title candidate groups to one canonical research work.

Both outputs retain available abstracts. The application output keeps the full
86-column processing schema, while the public release exposes a documented
35-column research-metadata subset. Public redistribution still requires the
source-rights and dataset-license review documented in the release package.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Iterable


AMBIGUOUS_SRI_LANKAN_ALIASES = {
    "Department of Archaeology",
    "Industrial Technology Institute",
    "Information and Communication Technology Agency",
    "Institute for Research and Development",
    "Ladies College",
    "National Institute of Health Sciences",
    "National Research Council",
}

# These records have independent Sri Lankan evidence despite an ambiguous
# institution label. The two IIHS records explicitly name IIHS Sri Lanka in the
# deposited affiliation; the monsoon paper is from Sri Lanka's Industrial
# Technology Institute and was published in the Sri Lankan Journal of Physics.
AMBIGUOUS_ALIAS_EXCEPTIONS = {
    "https://openalex.org/W4391366005",
    "https://openalex.org/W4411034267",
    "https://openalex.org/W4415505982",
}

ADJUDICATED_NON_AI = {
    "https://openalex.org/W7154209169": (
        "The work performs linguistic semantic-field grouping and descriptive "
        "statistics; its abstract does not establish an AI/ML method."
    ),
}

PREPRINT_OR_REPOSITORY_DOI_PREFIXES = (
    "10.1101/",
    "10.21203/",
    "10.2139/",
    "10.31224/",
    "10.36227/",
    "10.48550/",
    "10.5281/",
    "10.6084/",
    "10.7287/peerj.preprints",
)

PUBLIC_RELEASE_FIELDS = [
    "openalex_id",
    "doi",
    "url",
    "pdf_url",
    "source_dataset",
    "source_record_id",
    "title",
    "abstract",
    "keywords",
    "publication_date",
    "type",
    "language",
    "authors",
    "author_orcids",
    "author_affiliations",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "ownership_class",
    "publisher",
    "journal",
    "issn",
    "volume",
    "issue",
    "first_page",
    "last_page",
    "article_number",
    "topics",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "license",
    "license_url",
    "oa_status",
    "ai_classification_label",
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split_values(value: str) -> set[str]:
    return {item.strip() for item in (value or "").split(";") if item.strip()}


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def augment_duplicate_candidates(
    rows: list[dict[str, str]], duplicate_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Add normalized-title groups missed by the supplied exact-title audit."""

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    id_to_group: dict[str, str] = {}
    for row in duplicate_rows:
        copied = deepcopy(row)
        group = copied["title_group"].strip()
        groups[group].append(copied)
        id_to_group[copied.get("openalex_id", "").strip()] = group

    normalized_groups: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for index, row in enumerate(rows, start=2):
        normalized_groups[normalize_title(row.get("title", ""))].append((index, row))

    next_group = 1 + max(
        (int(row["title_group"]) for row in duplicate_rows if row.get("title_group", "").isdigit()),
        default=0,
    )
    for items in normalized_groups.values():
        if len(items) < 2:
            continue
        identifiers = {row.get("openalex_id", "").strip() for _, row in items}
        existing_groups = {id_to_group[item] for item in identifiers if item in id_to_group}
        if identifiers <= set(id_to_group):
            continue
        if existing_groups:
            target_group = min(existing_groups, key=lambda value: int(value))
            for old_group in sorted(existing_groups - {target_group}, key=lambda value: int(value)):
                for old_row in groups.pop(old_group):
                    old_row["title_group"] = target_group
                    groups[target_group].append(old_row)
                    id_to_group[old_row["openalex_id"].strip()] = target_group
        else:
            target_group = str(next_group)
            next_group += 1
        for original_csv_row, row in items:
            identifier = row.get("openalex_id", "").strip()
            if identifier in id_to_group:
                continue
            groups[target_group].append(
                {
                    "title_group": target_group,
                    "original_csv_row": str(original_csv_row),
                    "title": row.get("title", ""),
                    "doi": row.get("doi", ""),
                    "openalex_id": row.get("openalex_id", ""),
                    "publication_date": row.get("publication_date", ""),
                    "authors": row.get("authors", ""),
                    "source_dataset": row.get("source_dataset", ""),
                    "resolution_note": "",
                }
            )
            id_to_group[identifier] = target_group
    return [
        row
        for group in sorted(groups, key=lambda value: int(value))
        for row in groups[group]
    ]


def unsupported_sri_lanka_alias(row: dict[str, str]) -> bool:
    openalex_id = row.get("openalex_id", "").strip()
    if openalex_id in AMBIGUOUS_ALIAS_EXCEPTIONS:
        return False
    institutions = split_values(row.get("sri_lankan_institutions", ""))
    return bool(institutions) and institutions <= AMBIGUOUS_SRI_LANKAN_ALIASES


def completeness_score(row: dict[str, str]) -> int:
    fields = (
        "doi",
        "abstract",
        "keywords",
        "authors",
        "author_affiliations",
        "publisher",
        "journal",
        "issn",
        "license",
        "pdf_url",
    )
    return sum(bool((row.get(field) or "").strip()) for field in fields)


def parsed_date(value: str) -> date:
    text = (value or "").strip()
    for candidate in (text[:10], f"{text[:7]}-01", f"{text[:4]}-01-01"):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return date.min


def canonical_rank(row: dict[str, str]) -> tuple[int, int, int, int, str]:
    """Prefer formal publications, then richer and later records."""

    doi = (row.get("doi") or "").strip().casefold()
    title = (row.get("title") or "").strip().casefold()
    source_type = (row.get("source_type") or "").strip().casefold()
    publication_type = (row.get("type") or "").strip().casefold()
    repository_penalty = int(doi.startswith(PREPRINT_OR_REPOSITORY_DOI_PREFIXES))
    supplemental_penalty = int(
        title.startswith("additional file")
        or title.startswith("repository:")
        or "supplement" in title
    )
    formal_bonus = int(
        source_type in {"journal", "conference"}
        or publication_type in {"article", "journal-article", "proceedings-article"}
    )
    # ISO dates sort chronologically; ordinal avoids lexical surprises for
    # partial dates after normalisation.
    date_rank = parsed_date(row.get("publication_date", "")).toordinal()
    return (
        formal_bonus - repository_penalty - supplemental_penalty,
        completeness_score(row),
        date_rank,
        int(bool(doi)),
        row.get("openalex_id", ""),
    )


def select_duplicate_keepers(
    rows_by_openalex: dict[str, dict[str, str]],
    duplicate_rows: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for item in duplicate_rows:
        openalex_id = item.get("openalex_id", "").strip()
        group = item.get("title_group", "").strip()
        if not openalex_id or openalex_id not in rows_by_openalex:
            raise ValueError(f"Duplicate worksheet contains unknown OpenAlex ID: {openalex_id}")
        groups[group].append(openalex_id)

    keepers: dict[str, str] = {}
    removed: dict[str, str] = {}
    for group, identifiers in groups.items():
        unique_identifiers = list(dict.fromkeys(identifiers))
        keeper = max(unique_identifiers, key=lambda item: canonical_rank(rows_by_openalex[item]))
        keepers[group] = keeper
        for identifier in unique_identifiers:
            if identifier != keeper:
                removed[identifier] = keeper
    return keepers, removed


def public_release_row(row: dict[str, str]) -> dict[str, str]:
    """Return the documented public subset while preserving abstracts."""

    return {field: row.get(field, "") for field in PUBLIC_RELEASE_FIELDS}


def build_release(args: argparse.Namespace) -> dict[str, int]:
    fieldnames, rows = read_csv(args.input)
    review_fields, review_rows = read_csv(args.ai_review)
    duplicate_fields, duplicate_rows = read_csv(args.duplicates)

    rows_by_openalex = {
        row.get("openalex_id", "").strip(): row
        for row in rows
        if row.get("openalex_id", "").strip()
    }
    if len(rows_by_openalex) != len(rows):
        raise ValueError("Input must have one unique nonblank OpenAlex ID per row")
    if len(review_rows) != 214:
        raise ValueError(f"Expected 214 AI review rows, found {len(review_rows)}")

    review_ids = {row.get("openalex_id", "").strip() for row in review_rows}
    source_review_ids = {
        row.get("openalex_id", "").strip()
        for row in rows
        if row.get("a2_pending_decision", "").strip().upper() == "REVIEW"
    }
    if review_ids != source_review_ids:
        raise ValueError("AI review worksheet does not exactly match source REVIEW rows")

    duplicate_rows = augment_duplicate_candidates(rows, duplicate_rows)
    keepers, duplicate_removals = select_duplicate_keepers(rows_by_openalex, duplicate_rows)
    ownership_exclusions = {
        row["openalex_id"].strip(): "unsupported_sri_lanka_ambiguous_institution_alias"
        for row in rows
        if unsupported_sri_lanka_alias(row)
    }
    non_ai_exclusions = dict(ADJUDICATED_NON_AI)

    retained: list[dict[str, str]] = []
    for source in rows:
        openalex_id = source["openalex_id"].strip()
        if openalex_id in ownership_exclusions:
            continue
        if openalex_id in non_ai_exclusions:
            continue
        if openalex_id in duplicate_removals:
            continue
        row = deepcopy(source)
        if openalex_id in review_ids:
            row["a2_pending_decision"] = "ADJUDICATED_AI"
            row["final_resolution_source"] = "release_readiness_adjudication_2026_10_18"
        retained.append(row)

    retained_ids = {row["openalex_id"].strip() for row in retained}
    if len(retained_ids) != len(retained):
        raise ValueError("Final release contains duplicate OpenAlex IDs")

    adjudicated_reviews: list[dict[str, str]] = []
    for source in review_rows:
        row = deepcopy(source)
        openalex_id = row["openalex_id"].strip()
        if openalex_id in non_ai_exclusions:
            row["review_decision"] = "NON_AI"
            row["review_notes"] = non_ai_exclusions[openalex_id]
        elif openalex_id in ownership_exclusions:
            row["review_decision"] = "AI_EXCLUDED_NOT_LK"
            row["review_notes"] = ownership_exclusions[openalex_id]
        elif openalex_id in duplicate_removals:
            row["review_decision"] = "AI_DUPLICATE_VERSION"
            row["review_notes"] = f"canonical_openalex_id={duplicate_removals[openalex_id]}"
        else:
            row["review_decision"] = "AI"
            row["review_notes"] = (
                "AI/ML method, system, resource, evaluation, or AI-focused review is "
                "explicit in the title or abstract; retained after release audit."
            )
        adjudicated_reviews.append(row)

    duplicate_audit: list[dict[str, str]] = []
    for source in duplicate_rows:
        row = deepcopy(source)
        openalex_id = row["openalex_id"].strip()
        group = row["title_group"].strip()
        keeper = keepers[group]
        if openalex_id == keeper:
            row["resolution_note"] = "KEEP_CANONICAL_DISTINCT_WORK"
        else:
            row["resolution_note"] = f"REMOVE_DUPLICATE_VERSION;canonical_openalex_id={keeper}"
        duplicate_audit.append(row)

    exclusion_fields = [
        "openalex_id",
        "doi",
        "title",
        "authors",
        "author_affiliations",
        "sri_lankan_institutions",
        "exclusion_category",
        "exclusion_reason",
    ]
    exclusion_audit: list[dict[str, str]] = []
    all_exclusion_ids = set(ownership_exclusions) | set(non_ai_exclusions) | set(duplicate_removals)
    for openalex_id in sorted(all_exclusion_ids):
        source = rows_by_openalex[openalex_id]
        categories = []
        reasons = []
        if openalex_id in ownership_exclusions:
            categories.append("NOT_LK")
            reasons.append(ownership_exclusions[openalex_id])
        if openalex_id in non_ai_exclusions:
            categories.append("NON_AI")
            reasons.append(non_ai_exclusions[openalex_id])
        if openalex_id in duplicate_removals:
            categories.append("DUPLICATE_VERSION")
            reasons.append(f"canonical_openalex_id={duplicate_removals[openalex_id]}")
        exclusion_audit.append(
            {
                **{field: source.get(field, "") for field in exclusion_fields[:6]},
                "exclusion_category": ";".join(categories),
                "exclusion_reason": "; ".join(reasons),
            }
        )

    write_csv(args.enriched_output, fieldnames, retained)
    write_csv(
        args.public_output,
        PUBLIC_RELEASE_FIELDS,
        (public_release_row(row) for row in retained),
    )
    write_csv(args.review_audit_output, review_fields, adjudicated_reviews)
    write_csv(args.duplicate_audit_output, duplicate_fields, duplicate_audit)
    write_csv(args.exclusion_audit_output, exclusion_fields, exclusion_audit)

    return {
        "input_rows": len(rows),
        "retained_rows": len(retained),
        "excluded_unique_rows": len(all_exclusion_ids),
        "ownership_exclusions": len(ownership_exclusions),
        "non_ai_exclusions": len(non_ai_exclusions),
        "duplicate_version_exclusions": len(duplicate_removals),
        "adjudicated_ai_review_rows": len(review_rows),
        "duplicate_groups": len(keepers),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ai-review", type=Path, required=True)
    parser.add_argument("--duplicates", type=Path, required=True)
    parser.add_argument("--enriched-output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--review-audit-output", type=Path, required=True)
    parser.add_argument("--duplicate-audit-output", type=Path, required=True)
    parser.add_argument("--exclusion-audit-output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = build_release(args)
    for key, value in summary.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
