"""Build a department-scoped publication dataset from the CSE staff roster.

The builder deliberately does not classify AI relevance.  It establishes the
department boundary first so the existing ResearchLanka classifier can run on
the verified CSE records afterwards.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


UOM_NAMES = {
    "university of moratuwa",
    "university of moratuwa sri lanka",
}

ENRICHMENT_COLUMNS = [
    "uom_cse_authors",
    "uom_cse_researcher_ids",
    "cse_affiliation_verified",
    "cse_affiliation_source",
    "cse_roster_checked_on",
    "source_openalex",
    "source_uom_repository",
    "source_staff_profile",
    "source_scopus",
    "source_google_scholar",
]


@dataclass(frozen=True)
class StaffMember:
    researcher_id: str
    official_name: str
    display_name: str
    profile_url: str
    aliases: tuple[str, ...]
    roster_checked_on: str


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def load_staff_roster(path: Path) -> list[StaffMember]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        members = []
        for row in rows:
            aliases = [row["official_name"], row["display_name"]]
            aliases.extend(row.get("author_aliases", "").split("|"))
            normalized_aliases = tuple(
                dict.fromkeys(alias.strip() for alias in aliases if alias.strip())
            )
            members.append(
                StaffMember(
                    researcher_id=row["researcher_id"].strip(),
                    official_name=row["official_name"].strip(),
                    display_name=row["display_name"].strip(),
                    profile_url=row["profile_url"].strip(),
                    aliases=normalized_aliases,
                    roster_checked_on=row["roster_checked_on"].strip(),
                )
            )
    if not members:
        raise ValueError(f"CSE staff roster is empty: {path}")
    return members


def matched_staff(row: Mapping[str, object], roster: Iterable[StaffMember]) -> list[StaffMember]:
    author_names = {normalize_name(author) for author in split_values(row.get("authors"))}
    matches: list[StaffMember] = []
    for member in roster:
        aliases = {normalize_name(alias) for alias in member.aliases}
        if author_names.intersection(aliases):
            matches.append(member)
    return matches


def has_uom_affiliation(row: Mapping[str, object]) -> bool:
    institutions = split_values(row.get("institutions"))
    institutions.extend(split_values(row.get("sri_lankan_institutions")))
    return any(
        normalized in UOM_NAMES or "university of moratuwa" in normalized
        for normalized in (normalize_name(value) for value in institutions)
    )


def normalized_doi(row: Mapping[str, object]) -> str:
    value = str(row.get("doi") or "").strip().casefold()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value).rstrip("/.")


def deduplication_key(row: Mapping[str, object]) -> str:
    doi = normalized_doi(row)
    if doi:
        return f"doi:{doi}"
    title = normalize_name(row.get("title"))
    year = str(row.get("publication_year") or "").strip()
    return f"title-year:{title}:{year}"


def source_flags(row: Mapping[str, object]) -> dict[str, str]:
    sources = {normalize_name(value) for value in split_values(row.get("source_dataset"))}
    joined = " ".join(sorted(sources))
    return {
        "source_openalex": str("openalex" in sources).upper(),
        "source_uom_repository": str(
            "uom" in joined and ("repository" in joined or "moratuwa" in joined)
        ).upper(),
        "source_staff_profile": "FALSE",
        "source_scopus": str("scopus" in sources).upper(),
        "source_google_scholar": str("google scholar" in sources).upper(),
    }


def row_completeness(row: Mapping[str, object]) -> int:
    preferred = (
        "doi",
        "abstract",
        "keywords",
        "openalex_id",
        "author_orcids",
        "topics",
        "primary_topic",
    )
    return sum(bool(str(row.get(column) or "").strip()) for column in preferred)


def publication_year(row: Mapping[str, object]) -> int | None:
    raw_year = str(row.get("publication_year") or "").strip()
    if raw_year:
        try:
            return int(raw_year)
        except ValueError:
            return None
    match = re.match(r"^(\d{4})", str(row.get("publication_date") or "").strip())
    return int(match.group(1)) if match else None


def merge_duplicate(current: dict[str, str], candidate: dict[str, str]) -> dict[str, str]:
    primary, secondary = (
        (candidate, current)
        if row_completeness(candidate) > row_completeness(current)
        else (current, candidate)
    )
    merged = dict(primary)
    for column, value in secondary.items():
        if not merged.get(column) and value:
            merged[column] = value
    for column in ("source_dataset", *ENRICHMENT_COLUMNS[-5:]):
        if column.startswith("source_") and column != "source_dataset":
            merged[column] = str(
                current.get(column) == "TRUE" or candidate.get(column) == "TRUE"
            ).upper()
            continue
        values = split_values(current.get(column)) + split_values(candidate.get(column))
        merged[column] = "; ".join(dict.fromkeys(values))
    return merged


def build_cse_uom_dataset(
    *,
    input_path: Path,
    roster_path: Path,
    candidate_output: Path,
    verified_output: Path,
    year_min: int = 2016,
    year_max: int = 2026,
) -> dict[str, int]:
    roster = load_staff_roster(roster_path)
    candidates: list[dict[str, str]] = []
    verified_by_key: dict[str, dict[str, str]] = {}

    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Publication dataset has no header: {input_path}")
        input_columns = list(reader.fieldnames)
        for source_row in reader:
            year = publication_year(source_row)
            if year is None or year < year_min or year > year_max:
                continue
            matches = matched_staff(source_row, roster)
            if not matches:
                continue

            verified = has_uom_affiliation(source_row)
            row = dict(source_row)
            row["publication_year"] = str(year)
            row.update(source_flags(row))
            row.update(
                {
                    "uom_cse_authors": "; ".join(member.display_name for member in matches),
                    "uom_cse_researcher_ids": "; ".join(
                        member.researcher_id for member in matches
                    ),
                    "cse_affiliation_verified": str(verified).upper(),
                    "cse_affiliation_source": (
                        "official_cse_staff_roster+publication_uom_affiliation"
                        if verified
                        else "official_cse_staff_roster_only; manual_review_required"
                    ),
                    "cse_roster_checked_on": max(
                        member.roster_checked_on for member in matches
                    ),
                }
            )
            candidates.append(row)
            if verified:
                key = deduplication_key(row)
                if key in verified_by_key:
                    verified_by_key[key] = merge_duplicate(verified_by_key[key], row)
                else:
                    verified_by_key[key] = row

    output_columns = [
        *input_columns,
        *(c for c in ("publication_year", *ENRICHMENT_COLUMNS) if c not in input_columns),
    ]
    for path, rows in (
        (candidate_output, candidates),
        (verified_output, list(verified_by_key.values())),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=output_columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    return {
        "staff_count": len(roster),
        "candidate_count": len(candidates),
        "verified_count": len(verified_by_key),
        "manual_review_count": sum(
            row["cse_affiliation_verified"] != "TRUE" for row in candidates
        ),
    }
