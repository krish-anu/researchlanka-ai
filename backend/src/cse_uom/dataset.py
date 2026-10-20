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
from typing import Iterable, Mapping, Sequence


UOM_NAMES = {
    "university of moratuwa",
    "university of moratuwa sri lanka",
}

ENRICHMENT_COLUMNS = [
    "uom_cse_authors",
    "uom_cse_researcher_ids",
    "cse_unverified_roster_matches",
    "cse_affiliation_verified",
    "cse_affiliation_source",
    "cse_match_evidence",
    "cse_validation_decision",
    "cse_validation_reason",
    "cse_evidence_url",
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
    openalex_author_id: str = ""
    orcid: str = ""


@dataclass(frozen=True)
class StaffMatch:
    member: StaffMember
    evidence: str


@dataclass(frozen=True)
class PublicationCorrection:
    doi: str
    decision: str
    researcher_ids: tuple[str, ...]
    corrected_authors: str
    corrected_author_affiliations: str
    evidence_url: str
    reason: str


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _alias_uses_only_initials(alias: str) -> bool:
    """Return True when an alias does not contain a full given name.

    Initial-only aliases are useful for finding review candidates, but they are
    not unique enough to establish a staff identity automatically.  This also
    treats compact forms such as ``MSD Fernando`` as initials.
    """

    title_words = {"dr", "miss", "mr", "mrs", "ms", "prof", "professor"}
    if "," in alias:
        given_part = alias.split(",", 1)[1]
        tokens = re.findall(r"[A-Za-z]+", given_part)
    else:
        tokens = re.findall(r"[A-Za-z]+", alias)
        while tokens and tokens[0].casefold() in title_words:
            tokens.pop(0)
        tokens = tokens[:-1]
    if not tokens:
        return True
    return all(
        len(token) == 1 or (token.isupper() and len(token) <= 5)
        for token in tokens
    )


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
                    openalex_author_id=row.get("openalex_author_id", "").strip(),
                    orcid=row.get("orcid", "").strip(),
                )
            )
    if not members:
        raise ValueError(f"CSE staff roster is empty: {path}")
    return members


def _normalized_orcid(value: object) -> str:
    text = str(value or "").strip().casefold()
    return re.sub(r"^https?://orcid\.org/", "", text).strip("/")


def _normalized_openalex_author_id(value: object) -> str:
    text = str(value or "").strip().casefold()
    return re.sub(r"^https?://openalex\.org/", "", text).strip("/")


def matched_staff_with_evidence(
    row: Mapping[str, object], roster: Iterable[StaffMember]
) -> list[StaffMatch]:
    author_names = {normalize_name(author) for author in split_values(row.get("authors"))}
    author_orcids = {
        _normalized_orcid(value) for value in split_values(row.get("author_orcids"))
    }
    author_openalex_ids = {
        _normalized_openalex_author_id(value)
        for value in split_values(row.get("author_openalex_ids"))
    }
    matches: list[StaffMatch] = []
    for member in roster:
        member_openalex_id = _normalized_openalex_author_id(member.openalex_author_id)
        if member_openalex_id and member_openalex_id in author_openalex_ids:
            matches.append(
                StaffMatch(member=member, evidence="verified_openalex_author_id")
            )
            continue
        member_orcid = _normalized_orcid(member.orcid)
        if member_orcid and member_orcid in author_orcids:
            matches.append(StaffMatch(member=member, evidence="verified_orcid"))
            continue
        matched_aliases = [
            alias for alias in member.aliases if normalize_name(alias) in author_names
        ]
        if not matched_aliases:
            continue
        evidence = (
            "initials_only_alias"
            if all(_alias_uses_only_initials(alias) for alias in matched_aliases)
            else "full_name_alias"
        )
        matches.append(StaffMatch(member=member, evidence=evidence))
    return matches


def matched_staff(
    row: Mapping[str, object], roster: Iterable[StaffMember]
) -> list[StaffMember]:
    """Compatibility wrapper returning all roster matches, including review-only matches."""

    return [match.member for match in matched_staff_with_evidence(row, roster)]


def has_uom_affiliation(row: Mapping[str, object]) -> bool:
    institutions = split_values(row.get("institutions"))
    institutions.extend(split_values(row.get("sri_lankan_institutions")))
    institutions.extend(split_values(row.get("raw_affiliation_strings")))
    institutions.extend(split_values(row.get("sri_lankan_raw_affiliation_strings")))
    institutions.extend(split_values(row.get("author_affiliations")))
    return any(
        normalized in UOM_NAMES or "university of moratuwa" in normalized
        for normalized in (normalize_name(value) for value in institutions)
    )


def normalized_doi(row: Mapping[str, object]) -> str:
    value = str(row.get("doi") or "").strip().casefold()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value).rstrip("/.")


def load_publication_corrections(path: Path | None) -> dict[str, PublicationCorrection]:
    if path is None:
        return {}
    corrections: dict[str, PublicationCorrection] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            doi = normalized_doi(row)
            if not doi:
                raise ValueError(f"CSE publication correction has no DOI: {row}")
            if doi in corrections:
                raise ValueError(f"Duplicate CSE publication correction DOI: {doi}")
            decision = row.get("decision", "").strip().upper()
            if decision not in {"INCLUDE_STAFF", "EXCLUDE_STAFF"}:
                raise ValueError(
                    f"Unsupported CSE publication correction decision {decision!r} "
                    f"for DOI {doi}"
                )
            corrections[doi] = PublicationCorrection(
                doi=doi,
                decision=decision,
                researcher_ids=tuple(split_values(row.get("researcher_ids"))),
                corrected_authors=row.get("corrected_authors", "").strip(),
                corrected_author_affiliations=row.get(
                    "corrected_author_affiliations", ""
                ).strip(),
                evidence_url=row.get("evidence_url", "").strip(),
                reason=row.get("reason", "").strip(),
            )
    return corrections


def _apply_metadata_correction(
    row: Mapping[str, object], correction: PublicationCorrection | None
) -> dict[str, str]:
    corrected = {key: str(value or "") for key, value in row.items()}
    if correction is None:
        return corrected
    if correction.corrected_authors:
        corrected["authors"] = correction.corrected_authors
        corrected["authors_clean"] = correction.corrected_authors
        corrected["author_count"] = str(len(split_values(correction.corrected_authors)))
    if correction.corrected_author_affiliations:
        corrected["author_affiliations"] = correction.corrected_author_affiliations
    return corrected


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
        "source_staff_profile": str("staff profile" in joined).upper(),
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
    corrections_path: Path | None = None,
    supplement_paths: Sequence[Path] = (),
    audit_output: Path | None = None,
    year_min: int = 2016,
    year_max: int = 2026,
) -> dict[str, int]:
    roster = load_staff_roster(roster_path)
    roster_by_id = {member.researcher_id: member for member in roster}
    corrections = load_publication_corrections(corrections_path)
    candidates: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    verified_by_key: dict[str, dict[str, str]] = {}
    seen_input_keys: set[str] = set()
    input_columns: list[str] = []

    for current_input in (input_path, *supplement_paths):
        with current_input.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError(f"Publication dataset has no header: {current_input}")
            input_columns.extend(
                column for column in reader.fieldnames if column not in input_columns
            )
            source_rows = list(reader)
        for uncorrected_row in source_rows:
            correction = corrections.get(normalized_doi(uncorrected_row))
            source_row = _apply_metadata_correction(uncorrected_row, correction)
            year = publication_year(source_row)
            if year is None or year < year_min or year > year_max:
                continue
            source_row["publication_year"] = str(year)
            input_key = deduplication_key(source_row)
            if input_key in seen_input_keys:
                continue
            seen_input_keys.add(input_key)
            raw_matches = matched_staff_with_evidence(source_row, roster)
            if correction and correction.decision == "INCLUDE_STAFF":
                forced_ids = set(correction.researcher_ids)
                raw_matches = [
                    StaffMatch(member=match.member, evidence="manual_correction")
                    if match.member.researcher_id in forced_ids
                    else match
                    for match in raw_matches
                ]
                existing_ids = {match.member.researcher_id for match in raw_matches}
                for researcher_id in correction.researcher_ids:
                    if researcher_id not in roster_by_id:
                        raise ValueError(
                            "Unknown CSE researcher_id "
                            f"{researcher_id!r} for DOI {correction.doi}"
                        )
                    if researcher_id not in existing_ids:
                        raw_matches.append(
                            StaffMatch(
                                member=roster_by_id[researcher_id],
                                evidence="manual_correction",
                            )
                        )
            if not raw_matches:
                continue

            excluded_ids = (
                set(correction.researcher_ids)
                if correction and correction.decision == "EXCLUDE_STAFF"
                else set()
            )
            usable_matches = [
                match
                for match in raw_matches
                if match.member.researcher_id not in excluded_ids
            ]
            has_uom = has_uom_affiliation(source_row)
            verified_matches = [
                match
                for match in usable_matches
                if match.evidence == "manual_correction"
                or (
                    match.evidence
                    in {
                        "full_name_alias",
                        "verified_orcid",
                        "verified_openalex_author_id",
                    }
                    and has_uom
                )
            ]
            unverified_matches = [
                match for match in usable_matches if match not in verified_matches
            ]
            verified = bool(verified_matches)
            if correction and correction.decision == "EXCLUDE_STAFF" and not usable_matches:
                decision = "REJECT"
                reason = correction.reason or "manually excluded staff attribution"
            elif verified:
                decision = "VERIFIED"
                reason = (
                    correction.reason
                    if correction and correction.decision == "INCLUDE_STAFF"
                    else "verified staff identity and publication-level UoM/CSE evidence"
                )
            else:
                decision = "REVIEW"
                reason = "initials-only or insufficient publication-level affiliation evidence"

            row = dict(source_row)
            row["publication_year"] = str(year)
            row.update(source_flags(row))
            row.update(
                {
                    "uom_cse_authors": "; ".join(
                        match.member.display_name for match in verified_matches
                    ),
                    "uom_cse_researcher_ids": "; ".join(
                        match.member.researcher_id for match in verified_matches
                    ),
                    "cse_unverified_roster_matches": "; ".join(
                        match.member.display_name for match in unverified_matches
                    ),
                    "cse_affiliation_verified": str(verified).upper(),
                    "cse_affiliation_source": (
                        "official_cse_staff_roster+author_identity+publication_affiliation"
                        if verified
                        else "manual_review_or_exclusion"
                    ),
                    "cse_match_evidence": "; ".join(
                        f"{match.member.researcher_id}:{match.evidence}"
                        for match in raw_matches
                    ),
                    "cse_validation_decision": decision,
                    "cse_validation_reason": reason,
                    "cse_evidence_url": correction.evidence_url if correction else "",
                    "cse_roster_checked_on": max(
                        match.member.roster_checked_on for match in raw_matches
                    ),
                }
            )
            audit_rows.append(row)
            if decision == "REJECT":
                continue
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
    outputs: list[tuple[Path, list[dict[str, str]]]] = [
        (candidate_output, candidates),
        (verified_output, list(verified_by_key.values())),
    ]
    if audit_output is not None:
        outputs.append((audit_output, audit_rows))
    for path, rows in outputs:
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
        "rejected_count": sum(
            row["cse_validation_decision"] == "REJECT" for row in audit_rows
        ),
        "initials_review_count": sum(
            "initials_only_alias" in row["cse_match_evidence"]
            and row["cse_validation_decision"] == "REVIEW"
            for row in audit_rows
        ),
    }
