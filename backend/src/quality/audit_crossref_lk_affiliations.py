"""Audit Crossref Sri Lanka authorship affiliation quality.

Crossref does not provide OpenAlex-style normalized institution country rows for
each authorship. This audit therefore works from publication-time raw Crossref
author affiliation strings and separates verified LK authorships from review,
exclude, and work-level query-leakage cases.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.quality.audit_openalex_lk_affiliations import (  # noqa: E402
    BRANCH_TERMS,
    SRI_LANKA,
    as_text,
    contains_any,
    detect_explicit_countries,
    detect_locations,
    is_hq_risk,
    is_known_lk_institution,
    is_multinational,
    pct,
    pct_entry,
    unique_join,
    write_csv,
)
from src.utils.doi import normalize_doi  # noqa: E402

LOGGER = logging.getLogger("crossref_lk_affiliation_audit")
RANDOM_SEED = 20260831

ISSUE_FIELDS = [
    "issue_missing_author_affiliation",
    "issue_work_level_to_authorship_leakage",
    "issue_explicit_foreign_location_conflict",
    "issue_lk_location_unverified",
    "issue_possible_institution_match_error",
    "issue_parent_branch_location_ambiguity",
    "issue_lk_multi_affiliated",
    "issue_multinational_institution_ambiguous",
    "issue_hq_branch_conflict",
    "issue_temporal_affiliation_risk",
    "issue_source_metadata_inconsistency",
    "issue_crossref_query_false_positive",
]

POSITIVE_FIELDS = [
    "positive_explicit_lk_country",
    "positive_explicit_lk_location",
    "positive_known_lk_institution",
    "positive_lk_multi_affiliated",
]

PRIMARY_CLASSIFICATIONS = [
    "VERIFIED_LK",
    "LK_MULTI_AFFILIATED",
    "LIKELY_LK",
    "REVIEW_LOCATION_UNKNOWN",
    "REVIEW_LOCATION_CONFLICT",
    "REVIEW_INSTITUTION_MATCH",
    "REVIEW_WORK_LEVEL_ONLY",
    "REVIEW_MISSING_AUTHOR_AFFILIATION",
    "REVIEW_HQ_RISK",
    "NON_LK_AUTHORSHIP",
    "EXCLUDE_CONFIRMED_FOREIGN",
    "EXCLUDE_QUERY_FALSE_POSITIVE",
]

CSV_FIELDS = [
    "crossref_work_id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "publisher",
    "container_title",
    "author_index",
    "author_name",
    "author_sequence",
    "raw_affiliation_strings",
    "detected_explicit_country",
    "detected_city_location",
    "work_lk_evidence",
    "current_crossref_classification",
    "proposed_audit_classification",
    "primary_classification",
    "lk_affiliation_confidence",
    "publishable_strict_lk",
    "issue_flags",
    "audit_explanation",
    *ISSUE_FIELDS,
    *POSITIVE_FIELDS,
]


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                LOGGER.warning("Skipping invalid JSON line %s in %s", line_number, path)
                continue
            if isinstance(value, dict):
                yield value


def list_text(value: Any) -> str:
    if isinstance(value, list):
        return unique_join(value)
    return as_text(value)


def date_parts_from_value(value: Any) -> list[Any] | None:
    if isinstance(value, dict):
        parts = value.get("date-parts")
    else:
        parts = value
    if (
        isinstance(parts, list)
        and parts
        and isinstance(parts[0], list)
        and parts[0]
    ):
        return parts[0]
    return None


def date_parts_year(value: Any) -> int | None:
    parts = date_parts_from_value(value)
    if parts and isinstance(parts[0], int):
        return parts[0]
    return None


def publication_year(work: dict[str, Any]) -> int | None:
    for key in (
        "published",
        "published-print",
        "published-online",
        "issued",
        "created",
        "published.date-parts",
        "published-print.date-parts",
        "published-online.date-parts",
        "issued.date-parts",
        "created.date-parts",
    ):
        year = date_parts_year(work.get(key))
        if year is not None:
            return year
    return None


def publication_date(work: dict[str, Any]) -> str:
    for key in (
        "published",
        "published-print",
        "published-online",
        "issued",
        "created",
        "published.date-parts",
        "published-print.date-parts",
        "published-online.date-parts",
        "issued.date-parts",
        "created.date-parts",
    ):
        parts = date_parts_from_value(work.get(key))
        if parts:
            return "-".join(str(part) for part in parts)
    return ""


def authors(work: dict[str, Any]) -> list[dict[str, Any]]:
    values = work.get("author")
    if isinstance(values, list):
        return [value for value in values if isinstance(value, dict)]
    return []


def author_name(author: dict[str, Any]) -> str:
    parts = [as_text(author.get("given")), as_text(author.get("family"))]
    name = " ".join(part for part in parts if part).strip()
    return name or as_text(author.get("name"))


def author_affiliations(author: dict[str, Any]) -> list[str]:
    affiliations = author.get("affiliation")
    if not isinstance(affiliations, list):
        return []
    names = []
    for affiliation in affiliations:
        if isinstance(affiliation, dict):
            name = as_text(affiliation.get("name"))
        else:
            name = as_text(affiliation)
        if name:
            names.append(name)
    return names


def work_id(work: dict[str, Any], index: int) -> str:
    doi = normalize_doi(work.get("DOI"))
    return doi or as_text(work.get("URL")) or f"missing-crossref-id:{index}"


def work_text(work: dict[str, Any]) -> str:
    pieces = [
        list_text(work.get("title")),
        list_text(work.get("subtitle")),
        as_text(work.get("abstract")),
        as_text(work.get("publisher-location")),
        as_text(work.get("event.location")),
        as_text(work.get("event", {}).get("location") if isinstance(work.get("event"), dict) else ""),
    ]
    return " ; ".join(piece for piece in pieces if piece)


def work_has_lk_evidence(work: dict[str, Any]) -> bool:
    text = work_text(work)
    explicit = detect_explicit_countries(text)
    locations, _ = detect_locations(text)
    return SRI_LANKA in explicit or bool(locations) or "sri lanka" in text.lower()


def classify_crossref_author(
    *,
    work: dict[str, Any],
    author: dict[str, Any],
    author_index: int,
    total_authors: int,
    work_lk: bool,
    work_identifier: str,
) -> dict[str, Any]:
    raw_values = author_affiliations(author)
    raw_text = " ; ".join(raw_values)
    year = publication_year(work)
    explicit_countries = detect_explicit_countries(raw_text)
    lk_locations, foreign_locations = detect_locations(raw_text)
    explicit_foreign = sorted(code for code in explicit_countries if code != SRI_LANKA)
    explicit_lk = SRI_LANKA in explicit_countries
    has_lk_location = bool(lk_locations)
    has_foreign_location = bool(foreign_locations)
    known_lk = is_known_lk_institution("", raw_text)
    multinational = is_multinational("", raw_text)
    hq_risk = is_hq_risk("", raw_text)
    branch_hint = contains_any(raw_text.lower(), BRANCH_TERMS)
    has_any_raw_location = explicit_lk or has_lk_location or explicit_foreign or has_foreign_location
    has_lk_author_evidence = explicit_lk or has_lk_location or known_lk

    issues = {field: False for field in ISSUE_FIELDS}
    positives = {field: False for field in POSITIVE_FIELDS}
    positives["positive_explicit_lk_country"] = explicit_lk
    positives["positive_explicit_lk_location"] = has_lk_location
    positives["positive_known_lk_institution"] = known_lk and not multinational

    if not raw_values:
        issues["issue_missing_author_affiliation"] = True
    if work_lk and not has_lk_author_evidence:
        issues["issue_work_level_to_authorship_leakage"] = True
    if has_lk_author_evidence and (explicit_foreign or has_foreign_location):
        issues["issue_explicit_foreign_location_conflict"] = True
    if known_lk and not (explicit_lk or has_lk_location):
        issues["issue_lk_location_unverified"] = True
    if known_lk and explicit_foreign and not (explicit_lk or has_lk_location):
        issues["issue_possible_institution_match_error"] = True
    if has_lk_author_evidence and branch_hint and (explicit_foreign or has_foreign_location):
        issues["issue_parent_branch_location_ambiguity"] = True
    if has_lk_author_evidence and (explicit_foreign or has_foreign_location):
        issues["issue_lk_multi_affiliated"] = True
        positives["positive_lk_multi_affiliated"] = explicit_lk or has_lk_location or known_lk
    if has_lk_author_evidence and multinational and not (explicit_lk or has_lk_location):
        issues["issue_multinational_institution_ambiguous"] = True
    if has_lk_author_evidence and hq_risk and (explicit_foreign or has_foreign_location):
        issues["issue_hq_branch_conflict"] = True
    if has_lk_author_evidence and not (explicit_lk or has_lk_location):
        issues["issue_temporal_affiliation_risk"] = True
    if explicit_lk and (explicit_foreign or has_foreign_location) and not has_lk_location:
        issues["issue_source_metadata_inconsistency"] = True
    if not work_lk and not has_lk_author_evidence:
        issues["issue_crossref_query_false_positive"] = True

    if not has_lk_author_evidence and not raw_values and work_lk:
        primary = "REVIEW_MISSING_AUTHOR_AFFILIATION"
    elif not has_lk_author_evidence and work_lk:
        primary = "REVIEW_WORK_LEVEL_ONLY"
    elif not has_lk_author_evidence and (explicit_foreign or has_foreign_location):
        primary = "NON_LK_AUTHORSHIP"
    elif not has_lk_author_evidence:
        primary = "EXCLUDE_QUERY_FALSE_POSITIVE"
    elif issues["issue_possible_institution_match_error"]:
        primary = "REVIEW_INSTITUTION_MATCH"
    elif issues["issue_explicit_foreign_location_conflict"]:
        primary = "LK_MULTI_AFFILIATED" if (explicit_lk or has_lk_location) else "REVIEW_LOCATION_CONFLICT"
    elif issues["issue_multinational_institution_ambiguous"] or issues["issue_hq_branch_conflict"]:
        primary = "REVIEW_HQ_RISK"
    elif explicit_lk or has_lk_location:
        primary = "VERIFIED_LK"
    elif known_lk:
        primary = "LIKELY_LK"
    else:
        primary = "REVIEW_LOCATION_UNKNOWN"

    if primary in {"VERIFIED_LK", "LK_MULTI_AFFILIATED"}:
        confidence = "HIGH"
    elif primary == "LIKELY_LK":
        confidence = "MEDIUM"
    elif primary.startswith("EXCLUDE") or primary == "NON_LK_AUTHORSHIP":
        confidence = "NOT_LK"
    elif primary == "REVIEW_LOCATION_CONFLICT":
        confidence = "CONFLICT"
    else:
        confidence = "LOW"

    publishable = primary in {"VERIFIED_LK", "LK_MULTI_AFFILIATED"}
    active_issues = [field.replace("issue_", "").upper() for field, value in issues.items() if value]
    explanation_bits = []
    if explicit_lk:
        explanation_bits.append("raw affiliation explicitly says Sri Lanka")
    if has_lk_location:
        explanation_bits.append(f"raw affiliation contains LK location(s): {unique_join(sorted(lk_locations))}")
    if known_lk:
        explanation_bits.append("raw affiliation contains a known Sri Lankan institution term")
    if explicit_foreign:
        explanation_bits.append(f"raw affiliation contains foreign country: {unique_join(explicit_foreign)}")
    if has_foreign_location:
        explanation_bits.append(f"raw affiliation contains foreign location(s): {unique_join(sorted(foreign_locations))}")
    if not raw_values:
        explanation_bits.append("Crossref author affiliation is missing")
    if work_lk and not has_lk_author_evidence:
        explanation_bits.append("work has Sri Lanka evidence, but this author row does not")
    if not explanation_bits:
        explanation_bits.append("classification is based on deterministic local Crossref evidence")

    return {
        "crossref_work_id": work_identifier,
        "doi": normalize_doi(work.get("DOI")) or "",
        "title": list_text(work.get("title")),
        "publication_year": year or "",
        "publication_date": publication_date(work),
        "type": as_text(work.get("type")),
        "publisher": as_text(work.get("publisher")),
        "container_title": list_text(work.get("container-title")),
        "author_index": author_index,
        "author_name": author_name(author),
        "author_sequence": as_text(author.get("sequence")) or ("first" if author_index == 1 else "additional"),
        "raw_affiliation_strings": unique_join(raw_values),
        "detected_explicit_country": unique_join(sorted(explicit_countries)),
        "detected_city_location": unique_join(sorted(lk_locations | foreign_locations)),
        "work_lk_evidence": work_lk,
        "current_crossref_classification": (
            "WORK_SELECTED_BY_CROSSREF_LK_QUERY" if work_lk else "NO_WORK_LEVEL_LK_EVIDENCE"
        ),
        "proposed_audit_classification": " + ".join(active_issues) if active_issues else primary,
        "primary_classification": primary,
        "lk_affiliation_confidence": confidence,
        "publishable_strict_lk": publishable,
        "issue_flags": unique_join(active_issues),
        "audit_explanation": "; ".join(explanation_bits),
        **issues,
        **positives,
    }


def classify_work_without_authors(work: dict[str, Any], index: int) -> dict[str, Any]:
    wid = work_id(work, index)
    work_lk = work_has_lk_evidence(work)
    issues = {field: False for field in ISSUE_FIELDS}
    positives = {field: False for field in POSITIVE_FIELDS}
    issues["issue_missing_author_affiliation"] = True
    if work_lk:
        issues["issue_work_level_to_authorship_leakage"] = True
    else:
        issues["issue_crossref_query_false_positive"] = True
    active_issues = [field.replace("issue_", "").upper() for field, value in issues.items() if value]
    primary = "REVIEW_MISSING_AUTHOR_AFFILIATION" if work_lk else "EXCLUDE_QUERY_FALSE_POSITIVE"
    return {
        "crossref_work_id": wid,
        "doi": normalize_doi(work.get("DOI")) or "",
        "title": list_text(work.get("title")),
        "publication_year": publication_year(work) or "",
        "publication_date": publication_date(work),
        "type": as_text(work.get("type")),
        "publisher": as_text(work.get("publisher")),
        "container_title": list_text(work.get("container-title")),
        "author_index": "",
        "author_name": "",
        "author_sequence": "",
        "raw_affiliation_strings": "",
        "detected_explicit_country": "",
        "detected_city_location": "",
        "work_lk_evidence": work_lk,
        "current_crossref_classification": (
            "WORK_SELECTED_BY_CROSSREF_LK_QUERY" if work_lk else "NO_WORK_LEVEL_LK_EVIDENCE"
        ),
        "proposed_audit_classification": " + ".join(active_issues),
        "primary_classification": primary,
        "lk_affiliation_confidence": "LOW",
        "publishable_strict_lk": False,
        "issue_flags": unique_join(active_issues),
        "audit_explanation": "Crossref work has no author rows; cannot assign publication-time LK authorship",
        **issues,
        **positives,
    }


def top_issue_combinations(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        active = [field.replace("issue_", "").upper() for field in ISSUE_FIELDS if row[field]]
        if len(active) >= 2:
            counter[" + ".join(active)] += 1
    return [{"combination": key, "count": value} for key, value in counter.most_common(limit)]


def sample_rows(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, int]:
    random.seed(RANDOM_SEED)
    samples_dir = output_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    categories = {
        "verified_lk": [row for row in rows if row["primary_classification"] == "VERIFIED_LK"],
        "manual_review_cases": [
            row for row in rows if str(row["primary_classification"]).startswith("REVIEW_")
        ],
        "missing_author_affiliation": [row for row in rows if row["issue_missing_author_affiliation"]],
        "work_level_only": [row for row in rows if row["issue_work_level_to_authorship_leakage"]],
        "foreign_location_conflict": [
            row for row in rows if row["issue_explicit_foreign_location_conflict"]
        ],
        "normalized_or_known_lk_only": [row for row in rows if row["issue_lk_location_unverified"]],
        "query_false_positive": [row for row in rows if row["issue_crossref_query_false_positive"]],
    }
    counts = {}
    for name, category_rows in categories.items():
        chosen = (
            random.sample(category_rows, min(20, len(category_rows)))
            if len(category_rows) > 20
            else category_rows
        )
        counts[name] = write_csv(samples_dir / f"{name}.csv", chosen, CSV_FIELDS)
    return counts


def write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Crossref LK Affiliation Audit",
        "",
        "Target concept: verified publication-time Sri Lankan institutional authorship from Crossref raw author affiliation strings.",
        "",
        "## Overall",
        f"- Total works: {summary['overall']['total_works']:,}",
        f"- Unique Crossref work IDs: {summary['overall']['unique_crossref_work_ids']:,}",
        f"- Total author rows: {summary['overall']['total_authorship_rows']:,}",
        f"- Works with any verified or likely LK author evidence: {summary['overall']['works_with_any_lk_author_evidence']:,}",
        f"- Candidate LK authorships: {summary['overall']['candidate_lk_authorships']:,}",
        f"- Works with only work-level LK evidence: {summary['overall']['works_with_work_level_only_lk_evidence']:,}",
        "",
        "## Publication Impact",
        f"- Current Crossref dataset size: {summary['publication_impact']['current_dataset_size']:,} works",
        f"- Strict verified dataset size: {summary['publication_impact']['strict_verified_dataset_size']:,} works",
        f"- Records sent to review: {summary['publication_impact']['records_sent_to_review']:,}",
        f"- Records with no LK author evidence: {summary['publication_impact']['records_without_lk_author_evidence']:,}",
        f"- Percentage retained: {summary['publication_impact']['percentage_retained']}%",
        f"- Percentage uncertain: {summary['publication_impact']['percentage_uncertain']}%",
        "",
        "## Authorship Classifications",
    ]
    for classification, data in summary["primary_classification_counts"].items():
        lines.append(
            f"- {classification}: {data['count']:,} "
            f"({data['percent_of_total_author_rows']}% of author rows)"
        )
    lines.extend(["", "## Independent Issue Counts"])
    for issue, data in summary["issue_counts"].items():
        lines.append(
            f"- {issue}: {data['authorship_count']:,} rows "
            f"({data['percent_of_total_author_rows']}% of author rows); "
            f"{data['work_count']:,} works ({data['percent_of_all_works']}% of all works)"
        )
    lines.extend(["", "## Year Breakdown", ""])
    lines.append("| Year | Author rows | Verified | Review | Non-LK/exclude | With issue | Issue % |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for year, row in sorted(summary["year_breakdown"].items()):
        lines.append(
            f"| {year} | {row['author_rows']} | {row['verified']} | {row['review']} | "
            f"{row['exclude_or_non_lk']} | {row['with_issue']} | {row['issue_percent']}% |"
        )
    lines.extend(["", "## Top Issue Combinations"])
    for combo in summary["top_issue_combinations"]:
        lines.append(f"- {combo['combination']}: {combo['count']:,}")
    lines.extend(
        [
            "",
            "## How to Find Crossref Issues",
            "",
            "Open `crossref_lk_affiliation_audit_records.csv` and filter these columns:",
            "",
            "| Goal | Filter |",
            "|---|---|",
            "| Manual review queue | `primary_classification` starts with `REVIEW_` |",
            "| Strict LK authorships | `publishable_strict_lk = True` |",
            "| Work-level leakage | `issue_work_level_to_authorship_leakage = True` |",
            "| Missing author affiliation | `issue_missing_author_affiliation = True` |",
            "| Foreign conflicts | `issue_explicit_foreign_location_conflict = True` |",
            "| Query false positives | `issue_crossref_query_false_positive = True` |",
            "| Known LK institution but no explicit location | `issue_lk_location_unverified = True` |",
            "",
            "Crossref-specific caution: a work can be found by a Sri Lanka affiliation query even when an individual author row has no LK evidence. Use `work_lk_evidence` and `issue_work_level_to_authorship_leakage` to separate work-level evidence from authorship-level evidence.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_audit(input_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    rows_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unique_work_ids: set[str] = set()
    year_counts: Counter[int] = Counter()
    total_works = 0
    total_author_rows = 0

    for index, work in enumerate(iter_jsonl(input_path), 1):
        if index % 5000 == 0:
            LOGGER.info("Audited %s Crossref works", index)
        total_works += 1
        wid = work_id(work, index)
        unique_work_ids.add(wid)
        year = publication_year(work)
        if year is not None:
            year_counts[year] += 1
        work_lk = work_has_lk_evidence(work)
        work_authors = authors(work)
        if not work_authors:
            row = classify_work_without_authors(work, index)
            rows.append(row)
            rows_by_work[wid].append(row)
            continue
        total_author_rows += len(work_authors)
        for author_index, author in enumerate(work_authors, 1):
            row = classify_crossref_author(
                work=work,
                author=author,
                author_index=author_index,
                total_authors=len(work_authors),
                work_lk=work_lk,
                work_identifier=wid,
            )
            rows.append(row)
            rows_by_work[wid].append(row)

    denominator_rows = len(rows)
    issue_counts = {}
    for issue in ISSUE_FIELDS:
        issue_name = issue.replace("issue_", "").upper()
        issue_rows = [row for row in rows if row[issue]]
        issue_works = {row["crossref_work_id"] for row in issue_rows}
        issue_counts[issue_name] = {
            "authorship_count": len(issue_rows),
            "percent_of_total_author_rows": pct(len(issue_rows), denominator_rows),
            "work_count": len(issue_works),
            "percent_of_all_works": pct(len(issue_works), len(unique_work_ids)),
        }

    primary_counts = Counter(row["primary_classification"] for row in rows)
    primary_summary = {
        name: {
            "count": primary_counts.get(name, 0),
            "percent_of_total_author_rows": pct(primary_counts.get(name, 0), denominator_rows),
        }
        for name in PRIMARY_CLASSIFICATIONS
    }
    strict_work_ids = {
        row["crossref_work_id"] for row in rows if row["publishable_strict_lk"] and row["crossref_work_id"]
    }
    review_work_ids = {
        row["crossref_work_id"]
        for row in rows
        if str(row["primary_classification"]).startswith("REVIEW_")
    }
    no_lk_author_works = {
        wid
        for wid, work_rows in rows_by_work.items()
        if not any(
            row["primary_classification"] in {"VERIFIED_LK", "LK_MULTI_AFFILIATED", "LIKELY_LK"}
            for row in work_rows
        )
    }
    work_level_only_works = {
        wid
        for wid, work_rows in rows_by_work.items()
        if any(row["issue_work_level_to_authorship_leakage"] for row in work_rows)
        and not any(row["publishable_strict_lk"] for row in work_rows)
    }
    candidate_lk_rows = [
        row
        for row in rows
        if row["primary_classification"] in {"VERIFIED_LK", "LK_MULTI_AFFILIATED", "LIKELY_LK"}
    ]
    issue_any_rows = [row for row in rows if any(row[issue] for issue in ISSUE_FIELDS)]
    issue_any_works = {row["crossref_work_id"] for row in issue_any_rows}

    year_breakdown: dict[str, dict[str, Any]] = {}
    for row in rows:
        year = as_text(row["publication_year"]) or "unknown"
        entry = year_breakdown.setdefault(
            year,
            {"author_rows": 0, "verified": 0, "review": 0, "exclude_or_non_lk": 0, "with_issue": 0},
        )
        entry["author_rows"] += 1
        if row["publishable_strict_lk"]:
            entry["verified"] += 1
        if str(row["primary_classification"]).startswith("REVIEW_"):
            entry["review"] += 1
        if str(row["primary_classification"]).startswith("EXCLUDE_") or row["primary_classification"] == "NON_LK_AUTHORSHIP":
            entry["exclude_or_non_lk"] += 1
        if any(row[issue] for issue in ISSUE_FIELDS):
            entry["with_issue"] += 1
    for entry in year_breakdown.values():
        entry["issue_percent"] = pct(entry["with_issue"], entry["author_rows"])

    issue_overlap = {}
    for left, right in combinations(ISSUE_FIELDS, 2):
        count = sum(1 for row in rows if row[left] and row[right])
        if count:
            issue_overlap[f"{left.replace('issue_', '').upper()} + {right.replace('issue_', '').upper()}"] = count

    issue_rows_for_csv = [
        row
        for row in rows
        if any(row[issue] for issue in ISSUE_FIELDS)
        or str(row["primary_classification"]).startswith(("REVIEW_", "EXCLUDE_"))
        or row["primary_classification"] == "NON_LK_AUTHORSHIP"
    ]
    manual_review_rows = [
        row for row in rows if str(row["primary_classification"]).startswith("REVIEW_")
    ]
    verified_rows = [row for row in rows if row["publishable_strict_lk"]]
    non_lk_rows = [
        row
        for row in rows
        if row["primary_classification"] in {"NON_LK_AUTHORSHIP", "EXCLUDE_QUERY_FALSE_POSITIVE", "EXCLUDE_CONFIRMED_FOREIGN"}
    ]

    write_csv(output_dir / "crossref_lk_affiliation_all_authorships.csv", rows, CSV_FIELDS)
    write_csv(output_dir / "crossref_lk_affiliation_audit_records.csv", issue_rows_for_csv, CSV_FIELDS)
    write_csv(output_dir / "crossref_lk_affiliation_manual_review.csv", manual_review_rows, CSV_FIELDS)
    write_csv(output_dir / "verified_lk_authorships.csv", verified_rows, CSV_FIELDS)
    write_csv(output_dir / "non_lk_or_excluded_authorships.csv", non_lk_rows, CSV_FIELDS)
    sample_counts = sample_rows(rows, output_dir)

    summary = {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "random_seed": RANDOM_SEED,
        "overall": {
            "total_works": total_works,
            "unique_crossref_work_ids": len(unique_work_ids),
            "total_authorship_rows": total_author_rows,
            "audit_rows_including_authorless_works": denominator_rows,
            "publication_year_distribution": dict(sorted(year_counts.items())),
            "works_with_any_lk_author_evidence": len(
                {
                    row["crossref_work_id"]
                    for row in rows
                    if row["primary_classification"] in {"VERIFIED_LK", "LK_MULTI_AFFILIATED", "LIKELY_LK"}
                }
            ),
            "candidate_lk_authorships": len(candidate_lk_rows),
            "works_with_work_level_only_lk_evidence": len(work_level_only_works),
        },
        "denominators": {
            "work_level_percentages": "unique Crossref work IDs",
            "authorship_level_percentages": "Crossref author rows plus one placeholder row for authorless works",
        },
        "primary_classification_counts": primary_summary,
        "issue_counts": issue_counts,
        "issue_overlap_authorship_counts": dict(sorted(issue_overlap.items(), key=lambda item: item[1], reverse=True)),
        "top_issue_combinations": top_issue_combinations(rows),
        "year_breakdown": dict(sorted(year_breakdown.items())),
        "samples": sample_counts,
        "high_confidence_data": {
            "VERIFIED_LK": pct_entry(primary_counts["VERIFIED_LK"], denominator_rows),
            "LK_MULTI_AFFILIATED": pct_entry(primary_counts["LK_MULTI_AFFILIATED"], denominator_rows),
        },
        "potential_problems": {
            "at_least_one_issue_authorship_rows": pct_entry(len(issue_any_rows), denominator_rows),
            "at_least_one_issue_works": pct_entry(len(issue_any_works), len(unique_work_ids)),
            "requiring_review_authorship_rows": pct_entry(len(manual_review_rows), denominator_rows),
            "work_level_only_works": pct_entry(len(work_level_only_works), len(unique_work_ids)),
            "records_without_lk_author_evidence": pct_entry(len(no_lk_author_works), len(unique_work_ids)),
            "missing_author_affiliation_rows": pct_entry(
                issue_counts["MISSING_AUTHOR_AFFILIATION"]["authorship_count"], denominator_rows
            ),
            "explicit_country_conflict_authorships": pct_entry(
                issue_counts["EXPLICIT_FOREIGN_LOCATION_CONFLICT"]["authorship_count"], denominator_rows
            ),
            "query_false_positive_rows": pct_entry(
                issue_counts["CROSSREF_QUERY_FALSE_POSITIVE"]["authorship_count"], denominator_rows
            ),
        },
        "publication_impact": {
            "current_dataset_size": len(unique_work_ids),
            "strict_verified_dataset_size": len(strict_work_ids),
            "records_sent_to_review": len(review_work_ids),
            "records_without_lk_author_evidence": len(no_lk_author_works),
            "percentage_retained": pct(len(strict_work_ids), len(unique_work_ids)),
            "percentage_uncertain": pct(len(review_work_ids), len(unique_work_ids)),
            "percentage_without_lk_author_evidence": pct(len(no_lk_author_works), len(unique_work_ids)),
        },
        "crossref_limitations": [
            "Crossref has raw author affiliation strings but usually no normalized institution country per authorship.",
            "A work selected by an affiliation query can still contain non-LK coauthors; these are separated as NON_LK_AUTHORSHIP.",
            "Author identity and historical affiliation checks are weaker than OpenAlex because Crossref author rows usually lack stable author IDs.",
        ],
    }
    (output_dir / "crossref_lk_affiliation_audit_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_report(output_dir / "crossref_lk_affiliation_audit_report.md", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "crossref" / "crossref_sri_lanka_works.jsonl",
        help="Path to Crossref works JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "crossref_lk_affiliation_audit",
        help="Directory for Crossref audit artifacts.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    summary = run_audit(args.input, args.output_dir)
    LOGGER.info(
        "Crossref audit complete: %s works, %s author rows, strict works=%s",
        summary["overall"]["unique_crossref_work_ids"],
        summary["overall"]["audit_rows_including_authorless_works"],
        summary["publication_impact"]["strict_verified_dataset_size"],
    )


if __name__ == "__main__":
    main()
