"""Audit OpenAlex Sri Lanka authorship affiliation quality.

This script does not change collection or production filtering rules. It reads
stored OpenAlex works and emits authorship-level audit artifacts for evaluating
whether current LK classifications are supported by publication-time evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import re
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

from src.preprocessing.openalex_normalizer import (  # noqa: E402
    authorships,
    classify_sri_lanka_ownership,
    corresponding_author_country_codes,
    country_codes_from_authorship,
    first_author_country_codes,
    is_sri_lankan_authorship,
    keep_in_sri_lanka_owned_dataset,
    normalize_publication_date,
    normalize_publication_year,
    openalex_work_id,
)
from src.utils.doi import normalize_doi  # noqa: E402

LOGGER = logging.getLogger("openalex_lk_affiliation_audit")
SRI_LANKA = "LK"
RANDOM_SEED = 20260831

ISSUE_FIELDS = [
    "issue_hq_branch_conflict",
    "issue_multinational_institution_ambiguous",
    "issue_explicit_foreign_location_conflict",
    "issue_lk_location_unverified",
    "issue_possible_institution_match_error",
    "issue_parent_branch_location_ambiguity",
    "issue_lk_multi_affiliated",
    "issue_possible_author_identity_error",
    "issue_author_year_location_conflict",
    "issue_temporal_affiliation_risk",
    "issue_corresponding_author_lk_weak_evidence",
    "issue_work_level_to_authorship_leakage",
    "issue_historical_institution_ambiguity",
    "issue_source_metadata_inconsistency",
    "issue_normalized_lk_only",
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
    "REVIEW_HQ_RISK",
    "REVIEW_LOCATION_UNKNOWN",
    "REVIEW_LOCATION_CONFLICT",
    "REVIEW_INSTITUTION_MATCH",
    "REVIEW_AUTHOR_IDENTITY",
    "EXCLUDE_CONFIRMED_FOREIGN",
    "EXCLUDE_MATCH_ERROR",
]

COUNTRY_NAMES = {
    "AF": ["Afghanistan"],
    "AL": ["Albania"],
    "DZ": ["Algeria"],
    "AR": ["Argentina"],
    "AU": ["Australia"],
    "AT": ["Austria"],
    "BD": ["Bangladesh"],
    "BE": ["Belgium"],
    "BR": ["Brazil"],
    "KH": ["Cambodia"],
    "CM": ["Cameroon"],
    "CA": ["Canada"],
    "CL": ["Chile"],
    "CN": ["China", "P. R. China", "People's Republic of China"],
    "CO": ["Colombia"],
    "CR": ["Costa Rica"],
    "CU": ["Cuba"],
    "CZ": ["Czech Republic", "Czechia"],
    "DK": ["Denmark"],
    "EG": ["Egypt"],
    "ET": ["Ethiopia"],
    "FI": ["Finland"],
    "FR": ["France"],
    "DE": ["Germany"],
    "GH": ["Ghana"],
    "GR": ["Greece"],
    "HK": ["Hong Kong"],
    "HU": ["Hungary"],
    "IN": ["India"],
    "ID": ["Indonesia"],
    "IR": ["Iran"],
    "IQ": ["Iraq"],
    "IE": ["Ireland"],
    "IL": ["Israel"],
    "IT": ["Italy"],
    "JP": ["Japan"],
    "JO": ["Jordan"],
    "KE": ["Kenya"],
    "KR": ["Korea", "South Korea", "Republic of Korea"],
    "LA": ["Laos", "Lao PDR"],
    "MY": ["Malaysia"],
    "MX": ["Mexico"],
    "MM": ["Myanmar"],
    "NP": ["Nepal"],
    "NL": ["Netherlands", "The Netherlands"],
    "NZ": ["New Zealand"],
    "NG": ["Nigeria"],
    "NO": ["Norway"],
    "PK": ["Pakistan"],
    "PH": ["Philippines"],
    "PL": ["Poland"],
    "PT": ["Portugal"],
    "QA": ["Qatar"],
    "RU": ["Russia", "Russian Federation"],
    "SA": ["Saudi Arabia"],
    "SG": ["Singapore"],
    "ZA": ["South Africa"],
    "ES": ["Spain"],
    "SE": ["Sweden"],
    "CH": ["Switzerland"],
    "TW": ["Taiwan"],
    "TZ": ["Tanzania"],
    "TH": ["Thailand"],
    "TR": ["Turkey", "Türkiye"],
    "UG": ["Uganda"],
    "AE": ["United Arab Emirates", "UAE"],
    "GB": ["United Kingdom", "UK", "England", "Scotland", "Wales"],
    "US": ["United States", "USA", "U.S.A.", "United States of America"],
    "VN": ["Vietnam", "Viet Nam"],
    "ZW": ["Zimbabwe"],
}

SRI_LANKA_LOCATIONS = [
    "Anuradhapura",
    "Badulla",
    "Battaramulla",
    "Colombo",
    "Galle",
    "Hambantota",
    "Homagama",
    "Jaffna",
    "Kalutara",
    "Kandy",
    "Katubedda",
    "Kelaniya",
    "Kurunegala",
    "Matara",
    "Moratuwa",
    "Nawala",
    "Nugegoda",
    "Peradeniya",
    "Peradeniya",
    "Ratmalana",
    "Ruhuna",
    "Sri Jayewardenepura",
    "Sri Lanka Institute of Information Technology",
    "Sabaragamuwa",
    "Vavuniya",
]

FOREIGN_LOCATIONS = {
    "EG": ["Cairo", "Alexandria", "Giza"],
    "IN": ["Bangalore", "Bengaluru", "Chennai", "Delhi", "Hyderabad", "Mumbai", "Pune"],
    "GB": ["London", "Oxford", "Cambridge", "Edinburgh", "Manchester"],
    "US": ["California", "New York", "Boston", "Maryland", "Washington", "Texas"],
    "AU": ["Sydney", "Melbourne", "Brisbane", "Canberra", "Perth"],
    "MY": ["Kuala Lumpur", "Selangor", "Penang"],
    "SG": ["Singapore"],
    "CN": ["Beijing", "Shanghai", "Wuhan", "Guangzhou"],
    "JP": ["Tokyo", "Kyoto", "Osaka"],
    "TH": ["Bangkok"],
    "ZA": ["Cape Town", "Johannesburg", "Pretoria"],
    "KE": ["Nairobi"],
    "NP": ["Kathmandu"],
    "BD": ["Dhaka"],
    "PK": ["Karachi", "Lahore", "Islamabad"],
}

KNOWN_LK_INSTITUTION_TERMS = [
    "university of colombo",
    "university of peradeniya",
    "university of jaffna",
    "university of moratuwa",
    "university of kelaniya",
    "university of sri jayewardenepura",
    "university of ruhuna",
    "open university of sri lanka",
    "sabaragamuwa university",
    "rajarata university",
    "uva wellassa university",
    "wayamba university",
    "eastern university",
    "south eastern university of sri lanka",
    "national science foundation",
    "medical research institute",
    "industrial technology institute",
    "sri lanka institute of information technology",
    "sri lanka technological campus",
    "national institute of fundamental studies",
    "postgraduate institute of agriculture",
    "general sir john kotelawala defence university",
    "teaching hospital",
    "national hospital of sri lanka",
]

MULTINATIONAL_TERMS = [
    "international water management institute",
    "iwmi",
    "cgiar",
    "world health organization",
    "who",
    "unicef",
    "united nations",
    "university of the united nations",
    "world bank",
    "asian development bank",
    "international union for conservation of nature",
    "iucn",
    "food and agriculture organization",
    "fao",
    "international rice research institute",
    "irri",
    "world agroforestry",
    "international center",
    "international centre",
    "red cross",
    "save the children",
]

HQ_RISK_TERMS = [
    "international water management institute",
    "iwmi",
    "cgiar",
    "united nations",
    "world health organization",
    "unicef",
    "world bank",
    "asian development bank",
]

BRANCH_TERMS = [
    "campus",
    "branch",
    "office",
    "regional office",
    "country office",
    "centre",
    "center",
    "station",
]

CSV_FIELDS = [
    "openalex_work_id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "openalex_author_id",
    "author_name",
    "author_position",
    "is_corresponding",
    "raw_affiliation_strings",
    "openalex_institution_id",
    "institution_name",
    "openalex_institution_country_code",
    "authorship_countries",
    "first_author_countries",
    "corresponding_author_countries",
    "ror",
    "detected_explicit_country",
    "detected_city_location",
    "institution_appears_multinational",
    "institution_considered_hq_risk",
    "current_researchlanka_classification",
    "proposed_audit_classification",
    "primary_classification",
    "lk_affiliation_confidence",
    "publishable_strict_lk",
    "issue_flags",
    "audit_explanation",
    *ISSUE_FIELDS,
    *POSITIVE_FIELDS,
]


def compile_terms(terms: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    return [
        (term, re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.I))
        for term in terms
    ]


COUNTRY_PATTERNS = [
    (code, name, pattern)
    for code, names in COUNTRY_NAMES.items()
    for name, pattern in compile_terms(names)
]
LK_COUNTRY_PATTERNS = compile_terms(["Sri Lanka", "Ceylon"])
LK_LOCATION_PATTERNS = compile_terms(SRI_LANKA_LOCATIONS)
FOREIGN_LOCATION_PATTERNS = [
    (code, name, pattern)
    for code, names in FOREIGN_LOCATIONS.items()
    for name, pattern in compile_terms(names)
]


def as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def unique_join(values: Iterable[Any], sep: str = "; ") -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = as_text(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return sep.join(out)


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


def raw_affiliations(authorship: dict[str, Any]) -> list[str]:
    values = authorship.get("raw_affiliation_strings")
    if isinstance(values, list):
        return [as_text(value) for value in values if as_text(value)]
    value = as_text(authorship.get("raw_affiliation_string"))
    return [value] if value else []


def author_id(authorship: dict[str, Any]) -> str:
    author = authorship.get("author")
    if isinstance(author, dict):
        return as_text(author.get("id"))
    return ""


def author_name(authorship: dict[str, Any]) -> str:
    author = authorship.get("author")
    if isinstance(author, dict) and author.get("display_name"):
        return as_text(author.get("display_name"))
    return as_text(authorship.get("raw_author_name"))


def institution_dicts(authorship: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        institution
        for institution in authorship.get("institutions", []) or []
        if isinstance(institution, dict)
    ]


def merge_institutions(institutions: list[dict[str, Any]]) -> dict[str, Any]:
    """Create one audit view for an authorship with one or more LK institutions."""
    return {
        "id": unique_join(inst.get("id") for inst in institutions),
        "display_name": unique_join(inst.get("display_name") for inst in institutions),
        "country_code": unique_join(inst.get("country_code") for inst in institutions),
        "ror": unique_join(inst.get("ror") for inst in institutions),
    }


def detect_explicit_countries(text: str) -> set[str]:
    codes = {SRI_LANKA for _, pattern in LK_COUNTRY_PATTERNS if pattern.search(text)}
    for code, _, pattern in COUNTRY_PATTERNS:
        if pattern.search(text):
            codes.add(code)
    return codes


def detect_locations(text: str) -> tuple[set[str], set[str]]:
    lk_locations = {name for name, pattern in LK_LOCATION_PATTERNS if pattern.search(text)}
    foreign = {
        f"{name} ({code})"
        for code, name, pattern in FOREIGN_LOCATION_PATTERNS
        if pattern.search(text)
    }
    return lk_locations, foreign


def contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def is_known_lk_institution(institution_name: str, raw_text: str) -> bool:
    combined = f"{institution_name} {raw_text}".lower()
    return contains_any(combined, KNOWN_LK_INSTITUTION_TERMS)


def is_multinational(institution_name: str, raw_text: str) -> bool:
    return contains_any(f"{institution_name} {raw_text}".lower(), MULTINATIONAL_TERMS)


def is_hq_risk(institution_name: str, raw_text: str) -> bool:
    return contains_any(f"{institution_name} {raw_text}".lower(), HQ_RISK_TERMS)


def build_author_history(path: Path) -> dict[str, Any]:
    history: dict[str, Any] = defaultdict(
        lambda: {
            "names": Counter(),
            "year_codes": defaultdict(Counter),
            "orcid_values": set(),
            "records": 0,
        }
    )
    for index, work in enumerate(iter_jsonl(path), 1):
        if index % 10000 == 0:
            LOGGER.info("Pass 1 read %s works", index)
        year = normalize_publication_year(work.get("publication_year"))
        if year is None:
            continue
        for authorship in authorships(work):
            aid = author_id(authorship)
            if not aid:
                continue
            item = history[aid]
            item["records"] += 1
            name = author_name(authorship)
            if name:
                item["names"][name] += 1
            author = authorship.get("author")
            if isinstance(author, dict) and author.get("orcid"):
                item["orcid_values"].add(as_text(author.get("orcid")))
            if authorship.get("raw_orcid"):
                item["orcid_values"].add(as_text(authorship.get("raw_orcid")))
            for code in country_codes_from_authorship(authorship):
                item["year_codes"][year][code] += 1
    return history


def author_year_conflict(aid: str, year: int | None, history: dict[str, Any]) -> bool:
    if not aid or year is None or aid not in history:
        return False
    nearby_codes: Counter[str] = Counter()
    current_lk = False
    for check_year in range(year - 2, year + 3):
        codes = history[aid]["year_codes"].get(check_year, Counter())
        nearby_codes.update(codes)
        if check_year == year and codes.get(SRI_LANKA):
            current_lk = True
    foreign_total = sum(count for code, count in nearby_codes.items() if code != SRI_LANKA)
    lk_total = nearby_codes.get(SRI_LANKA, 0)
    return current_lk and foreign_total >= 3 and lk_total <= 1


def possible_author_identity_error(aid: str, history: dict[str, Any]) -> bool:
    if not aid or aid not in history:
        return False
    item = history[aid]
    name_count = len(item["names"])
    orcid_count = len(item["orcid_values"])
    all_codes = set()
    for counter in item["year_codes"].values():
        all_codes.update(counter)
    return orcid_count > 1 or (name_count >= 6 and len(all_codes) >= 4 and item["records"] >= 10)


def classify_row(
    *,
    work: dict[str, Any],
    authorship: dict[str, Any],
    institution: dict[str, Any],
    current_classification: str,
    first_codes: set[str],
    corresponding_codes: set[str],
    author_history: dict[str, Any],
    work_level_lk_without_authorship: bool,
) -> dict[str, Any]:
    raw_values = raw_affiliations(authorship)
    raw_text = " ; ".join(raw_values)
    inst_name = as_text(institution.get("display_name"))
    inst_country = as_text(institution.get("country_code")).upper()
    inst_id = as_text(institution.get("id"))
    aid = author_id(authorship)
    year = normalize_publication_year(work.get("publication_year"))
    authorship_codes = country_codes_from_authorship(authorship)
    explicit_countries = detect_explicit_countries(raw_text)
    lk_locations, foreign_locations = detect_locations(raw_text)
    explicit_foreign = sorted(code for code in explicit_countries if code != SRI_LANKA)
    explicit_lk = SRI_LANKA in explicit_countries
    has_lk_location = bool(lk_locations)
    has_foreign_location = bool(foreign_locations)
    multinational = is_multinational(inst_name, raw_text)
    hq_risk = is_hq_risk(inst_name, raw_text)
    known_lk = is_known_lk_institution(inst_name, raw_text)
    branch_hint = contains_any(raw_text.lower(), BRANCH_TERMS)
    raw_location_evidence = explicit_lk or has_lk_location or explicit_foreign or has_foreign_location
    is_lk_normalized = inst_country == SRI_LANKA or SRI_LANKA in authorship_codes

    issues = {field: False for field in ISSUE_FIELDS}
    positives = {field: False for field in POSITIVE_FIELDS}

    positives["positive_explicit_lk_country"] = explicit_lk
    positives["positive_explicit_lk_location"] = has_lk_location
    positives["positive_known_lk_institution"] = known_lk and not multinational

    if is_lk_normalized and multinational and (explicit_foreign or has_foreign_location):
        issues["issue_hq_branch_conflict"] = True
    if is_lk_normalized and multinational and not (explicit_lk or has_lk_location):
        issues["issue_multinational_institution_ambiguous"] = True
    if is_lk_normalized and (explicit_foreign or has_foreign_location):
        issues["issue_explicit_foreign_location_conflict"] = True
    if is_lk_normalized and not raw_location_evidence:
        issues["issue_lk_location_unverified"] = True
    if is_lk_normalized and explicit_foreign and not (explicit_lk or has_lk_location):
        issues["issue_possible_institution_match_error"] = True
    if is_lk_normalized and branch_hint and (explicit_foreign or has_foreign_location or not raw_location_evidence):
        issues["issue_parent_branch_location_ambiguity"] = True
    if SRI_LANKA in authorship_codes and len(authorship_codes) > 1:
        issues["issue_lk_multi_affiliated"] = True
        positives["positive_lk_multi_affiliated"] = explicit_lk or has_lk_location or known_lk
    if possible_author_identity_error(aid, author_history):
        issues["issue_possible_author_identity_error"] = True
    if author_year_conflict(aid, year, author_history) and not (explicit_lk or has_lk_location):
        issues["issue_author_year_location_conflict"] = True
    if is_lk_normalized and not (explicit_lk or has_lk_location):
        issues["issue_temporal_affiliation_risk"] = True
    if (
        authorship.get("is_corresponding") is True
        and is_lk_normalized
        and not (explicit_lk or has_lk_location)
    ):
        issues["issue_corresponding_author_lk_weak_evidence"] = True
    if work_level_lk_without_authorship:
        issues["issue_work_level_to_authorship_leakage"] = True
    if year is not None and year < 2020 and is_lk_normalized and not (explicit_lk or has_lk_location):
        issues["issue_historical_institution_ambiguity"] = True
    if (
        aid
        and author_year_conflict(aid, year, author_history)
        and (explicit_foreign or has_foreign_location)
    ):
        issues["issue_source_metadata_inconsistency"] = True
    if is_lk_normalized and not (explicit_lk or has_lk_location or known_lk):
        issues["issue_normalized_lk_only"] = True

    if issues["issue_possible_institution_match_error"] and not (explicit_lk or has_lk_location):
        primary = "EXCLUDE_MATCH_ERROR" if explicit_foreign else "REVIEW_INSTITUTION_MATCH"
    elif issues["issue_explicit_foreign_location_conflict"] and not (explicit_lk or has_lk_location):
        primary = "EXCLUDE_CONFIRMED_FOREIGN"
    elif issues["issue_explicit_foreign_location_conflict"]:
        primary = "REVIEW_LOCATION_CONFLICT"
    elif issues["issue_possible_author_identity_error"]:
        primary = "REVIEW_AUTHOR_IDENTITY"
    elif issues["issue_author_year_location_conflict"]:
        primary = "REVIEW_AUTHOR_IDENTITY"
    elif issues["issue_hq_branch_conflict"] or issues["issue_multinational_institution_ambiguous"]:
        primary = "REVIEW_HQ_RISK"
    elif issues["issue_possible_institution_match_error"] or issues["issue_parent_branch_location_ambiguity"]:
        primary = "REVIEW_INSTITUTION_MATCH"
    elif positives["positive_lk_multi_affiliated"]:
        primary = "LK_MULTI_AFFILIATED"
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
    elif primary.startswith("EXCLUDE") or primary == "REVIEW_LOCATION_CONFLICT":
        confidence = "CONFLICT"
    else:
        confidence = "LOW"

    publishable = primary in {"VERIFIED_LK", "LK_MULTI_AFFILIATED"}
    active_issues = [field.replace("issue_", "").upper() for field, value in issues.items() if value]
    proposed = (
        " + ".join(active_issues)
        if active_issues
        else ("LK_MULTI_AFFILIATED" if primary == "LK_MULTI_AFFILIATED" else primary)
    )
    explanation_bits = []
    if explicit_lk:
        explanation_bits.append("raw affiliation explicitly says Sri Lanka")
    if has_lk_location:
        explanation_bits.append(f"raw affiliation contains LK location(s): {unique_join(sorted(lk_locations))}")
    if explicit_foreign:
        explanation_bits.append(f"raw affiliation contains foreign country: {unique_join(explicit_foreign)}")
    if has_foreign_location:
        explanation_bits.append(f"raw affiliation contains foreign location(s): {unique_join(sorted(foreign_locations))}")
    if multinational:
        explanation_bits.append("institution is in the multinational/HQ-risk dictionary")
    if not raw_values:
        explanation_bits.append("raw affiliation string is missing")
    if issues["issue_normalized_lk_only"]:
        explanation_bits.append("LK support comes only from normalized OpenAlex affiliation metadata")
    if not explanation_bits:
        explanation_bits.append("classification is based on deterministic local OpenAlex evidence")

    return {
        "openalex_work_id": openalex_work_id(work) or "",
        "doi": normalize_doi(work.get("doi")) or "",
        "title": as_text(work.get("title") or work.get("display_name")),
        "publication_year": year or "",
        "publication_date": normalize_publication_date(work.get("publication_date")) or "",
        "openalex_author_id": aid,
        "author_name": author_name(authorship),
        "author_position": as_text(authorship.get("author_position")),
        "is_corresponding": authorship.get("is_corresponding") is True,
        "raw_affiliation_strings": unique_join(raw_values),
        "openalex_institution_id": inst_id,
        "institution_name": inst_name,
        "openalex_institution_country_code": inst_country,
        "authorship_countries": unique_join(sorted(authorship_codes)),
        "first_author_countries": unique_join(sorted(first_codes)),
        "corresponding_author_countries": unique_join(sorted(corresponding_codes)),
        "ror": as_text(institution.get("ror")),
        "detected_explicit_country": unique_join(
            ["LK" if code == SRI_LANKA else code for code in sorted(explicit_countries)]
        ),
        "detected_city_location": unique_join(sorted(lk_locations | foreign_locations)),
        "institution_appears_multinational": multinational,
        "institution_considered_hq_risk": hq_risk,
        "current_researchlanka_classification": current_classification,
        "proposed_audit_classification": proposed,
        "primary_classification": primary,
        "lk_affiliation_confidence": confidence,
        "publishable_strict_lk": publishable,
        "issue_flags": unique_join(active_issues),
        "audit_explanation": "; ".join(explanation_bits),
        **issues,
        **positives,
    }


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 4) if denominator else 0.0


def pct_entry(count: int, denominator: int) -> dict[str, Any]:
    return {"count": count, "percent": pct(count, denominator)}


def classify_work_level_issue_sets(rows_by_work: dict[str, list[dict[str, Any]]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for work_id, rows in rows_by_work.items():
        for row in rows:
            for issue in ISSUE_FIELDS:
                if row[issue]:
                    result[issue].add(work_id)
    return result


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
        "hq_ambiguity": [
            row
            for row in rows
            if row["issue_hq_branch_conflict"] or row["issue_multinational_institution_ambiguous"]
        ],
        "foreign_location_conflict": [
            row for row in rows if row["issue_explicit_foreign_location_conflict"]
        ],
        "normalized_lk_only": [row for row in rows if row["issue_normalized_lk_only"]],
        "author_year_conflict": [row for row in rows if row["issue_author_year_location_conflict"]],
        "institution_match_error": [
            row for row in rows if row["issue_possible_institution_match_error"]
        ],
        "manual_review_cases": [
            row
            for row in rows
            if row["primary_classification"].startswith("REVIEW_")
        ],
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


def implementation_plan() -> list[dict[str, str]]:
    details = {
        "HQ_BRANCH_CONFLICT": (
            "An LK-headquartered institution is assigned to an authorship whose raw publication affiliation points to a foreign branch.",
            "Require institution.country_code=LK, a maintained HQ-risk/multinational institution registry, and explicit foreign country/city evidence in the raw authorship affiliation.",
            "MOSTLY_AUTOMATABLE",
        ),
        "MULTINATIONAL_INSTITUTION_AMBIGUOUS": (
            "A global organization with LK metadata is present, but the raw affiliation does not prove the Sri Lankan office.",
            "Use a configurable multinational institution registry and require explicit Sri Lanka country/city evidence before high-confidence LK classification.",
            "MOSTLY_AUTOMATABLE",
        ),
        "EXPLICIT_FOREIGN_LOCATION_CONFLICT": (
            "Raw affiliation contains a foreign country or city while OpenAlex assigns LK.",
            "Parse raw affiliation country and city names and let publication-specific foreign evidence override lower-priority normalized headquarters evidence.",
            "FULLY_AUTOMATABLE",
        ),
        "LK_LOCATION_UNVERIFIED": (
            "OpenAlex says LK, but the raw affiliation contains only an institution name or incomplete address.",
            "Flag LK-normalized authorships with no explicit Sri Lanka country, Sri Lankan city, branch, department, or address evidence.",
            "MOSTLY_AUTOMATABLE",
        ),
        "POSSIBLE_INSTITUTION_MATCH_ERROR": (
            "OpenAlex may have matched the raw string to the wrong Sri Lankan institution.",
            "Flag foreign-only raw affiliations paired with LK institutions, acronym ambiguity, parent/branch ambiguity, and severe raw-name/normalized-name mismatch.",
            "MANUAL_REVIEW_NEEDED",
        ),
        "PARENT_BRANCH_LOCATION_AMBIGUITY": (
            "A branch/campus location is being conflated with a parent organization's country.",
            "Detect branch/campus/office terms and compare raw location evidence with the normalized parent institution country.",
            "MOSTLY_AUTOMATABLE",
        ),
        "LK_MULTI_AFFILIATED": (
            "An author genuinely lists both Sri Lankan and foreign affiliations on the same publication.",
            "Keep as a positive class only when at least one publication-specific LK affiliation is verified and separate it from Sri Lanka-only statistics.",
            "FULLY_AUTOMATABLE",
        ),
        "POSSIBLE_AUTHOR_IDENTITY_ERROR": (
            "A single OpenAlex author ID may merge multiple people or incompatible profiles.",
            "Use local author ID histories to flag multiple ORCIDs, many incompatible names, and unusually broad simultaneous affiliation-country patterns.",
            "MANUAL_REVIEW_NEEDED",
        ),
        "AUTHOR_YEAR_LOCATION_CONFLICT": (
            "The publication-year affiliation is unusual relative to nearby publications for the same OpenAlex author ID.",
            "Compare author-country histories from publication_year-2 through publication_year+2 and flag isolated LK classifications surrounded by foreign-only evidence.",
            "MANUAL_REVIEW_NEEDED",
        ),
        "TEMPORAL_AFFILIATION_RISK": (
            "Current institution metadata may be interpreted as historical publication-time evidence.",
            "Flag LK-normalized authorships lacking explicit publication-time Sri Lanka location evidence, especially older records.",
            "MOSTLY_AUTOMATABLE",
        ),
        "CORRESPONDING_AUTHOR_LK_WEAK_EVIDENCE": (
            "A corresponding author is treated as LK using only normalized institution country.",
            "Flag corresponding LK authorships with no explicit raw Sri Lanka country or city evidence.",
            "MOSTLY_AUTOMATABLE",
        ),
        "WORK_LEVEL_TO_AUTHORSHIP_LEAKAGE": (
            "A work-level LK institution could be applied to every author instead of a specific authorship.",
            "Compare work-level institutions against authorship-level country codes and flag works with LK only at work level.",
            "FULLY_AUTOMATABLE",
        ),
        "HISTORICAL_INSTITUTION_AMBIGUITY": (
            "Institution names, locations, campuses, or headquarters may have changed over time.",
            "Flag older LK-normalized records without explicit publication-time location evidence for manual or registry-backed validation.",
            "MANUAL_REVIEW_NEEDED",
        ),
        "SOURCE_METADATA_INCONSISTENCY": (
            "Publication metadata may disagree with nearby publications or author history.",
            "Use author-year histories and raw affiliation conflicts to identify records where the source itself may be inconsistent.",
            "MANUAL_REVIEW_NEEDED",
        ),
        "NORMALIZED_LK_ONLY": (
            "The only LK support is OpenAlex/ROR-normalized country metadata.",
            "Require absence of explicit Sri Lanka raw text/location and absence of a known unambiguous Sri Lankan institution signal.",
            "FULLY_AUTOMATABLE",
        ),
    }
    plans = []
    for issue in [field.replace("issue_", "").upper() for field in ISSUE_FIELDS]:
        problem, detection, automation = details[issue]
        plans.append(
            {
                "issue": issue,
                "problem": problem,
                "detection_method": detection,
                "required_data": (
                    "Stage A uses existing OpenAlex work JSON, authorships, raw affiliations, institutions, ROR/OpenAlex IDs, and publication year. "
                    "Stage B adds OpenAlex author-history enrichment for ambiguous cases. Stage C adds ORCID or external publication metadata for unresolved high-risk cases."
                ),
                "automation_level": automation,
                "proposed_code_changes": (
                    "Keep this audit script separate until reviewed; then move reusable dictionaries/parsers into src/preprocessing or src/quality helpers, "
                    "and update src/preprocessing/openalex_normalizer.py classification to consume authorship-level verified LK evidence."
                ),
                "false_positive_risk": (
                    "Raw affiliations can be incomplete, city names can be ambiguous, and multiple affiliations may be collapsed into one string; "
                    "manual review remains necessary for conflict and identity classes."
                ),
                "tests": (
                    "Add focused OpenAlex-shaped fixtures for this issue, plus regression tests proving explicit raw publication-time evidence outranks normalized institution country."
                ),
                "migration_strategy": (
                    "Re-run raw JSONL through a versioned classifier, write strict/review/excluded outputs, compare against current CSV/parquet exports, "
                    "then backfill database tables only after acceptance of audit thresholds."
                ),
            }
        )
    return plans


def write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# OpenAlex LK Affiliation Audit",
        "",
        "Target concept: verified publication-time Sri Lankan institutional authorship. The audit does not infer nationality.",
        "",
        "## Overall",
        f"- Total works: {summary['overall']['total_works']:,}",
        f"- Unique OpenAlex work IDs: {summary['overall']['unique_openalex_work_ids']:,}",
        f"- Total authorships: {summary['overall']['total_authorships']:,}",
        f"- Unique authors: {summary['overall']['unique_authors']:,}",
        f"- Currently LK authorships: {summary['overall']['currently_lk_authorships']:,}",
        f"- Works passing current `keep_in_sri_lanka_owned_dataset`: {summary['overall']['works_passing_keep_in_sri_lanka_owned_dataset']:,}",
        "",
        "## Publication Impact",
        f"- Current dataset size: {summary['publication_impact']['current_dataset_size']:,} works",
        f"- Strict verified dataset size: {summary['publication_impact']['strict_verified_dataset_size']:,} works",
        f"- Records removed: {summary['publication_impact']['records_removed']:,}",
        f"- Records sent to review: {summary['publication_impact']['records_sent_to_review']:,}",
        f"- Percentage retained: {summary['publication_impact']['percentage_retained']}%",
        f"- Percentage excluded: {summary['publication_impact']['percentage_excluded']}%",
        f"- Percentage uncertain: {summary['publication_impact']['percentage_uncertain']}%",
        "",
        "## Authorship Classifications",
    ]
    for classification, data in summary["primary_classification_counts"].items():
        lines.append(
            f"- {classification}: {data['count']:,} "
            f"({data['percent_of_currently_lk_authorships']}% of currently LK authorships)"
        )
    lines.extend(["", "## Independent Issue Counts"])
    for issue, data in summary["issue_counts"].items():
        lines.append(
            f"- {issue}: {data['authorship_count']:,} authorships "
            f"({data['percent_of_currently_lk_authorships']}% of currently LK authorships); "
            f"{data['work_count']:,} works ({data['percent_of_all_works']}% of all works)"
        )
    lines.extend(["", "## Top Suspicious Institutions", ""])
    lines.append("| Institution | Current LK records | Verified | Review | Foreign/conflict | Error rate |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in summary["top_suspicious_institutions"][:25]:
        lines.append(
            f"| {row['institution']} | {row['current_lk_records']} | {row['verified']} | "
            f"{row['review']} | {row['foreign_conflict']} | {row['error_rate']}% |"
        )
    lines.extend(["", "## Year Breakdown", ""])
    lines.append("| Year | Current LK authorships | Verified | Review | Exclude | Issue % |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: |")
    for year, row in sorted(summary["year_breakdown"].items()):
        lines.append(
            f"| {year} | {row['currently_lk_authorships']} | {row['verified']} | "
            f"{row['review']} | {row['exclude']} | {row['issue_percent']}% |"
        )
    lines.extend(["", "## Top Issue Combinations"])
    for combo in summary["top_issue_combinations"]:
        lines.append(f"- {combo['combination']}: {combo['count']:,}")
    lines.extend(
        [
            "",
            "## Staged Use",
            "- Stage A: local deterministic audit completed by this script.",
            "- Stage B: enrich only ambiguous author/year cases through OpenAlex author history or works-by-author requests.",
            "- Stage C: use ORCID or external publication metadata only for the remaining high-risk subset.",
            "",
            "## Proposed Architecture",
            "OpenAlex collection -> raw work storage -> authorship-level affiliation extraction -> raw location parsing -> institution risk detection -> conflict detection -> optional author-year validation -> confidence classification -> strict publishable dataset plus separate review/exclusion queues.",
            "",
            "## Fix Plan",
        ]
    )
    for plan in summary["implementation_plan"]:
        lines.extend(
            [
                f"### {plan['issue']}",
                f"- Problem: {plan['problem']}",
                f"- Detection method: {plan['detection_method']}",
                f"- Required data: {plan['required_data']}",
                f"- Automation level: {plan['automation_level']}",
                f"- Proposed code changes: {plan['proposed_code_changes']}",
                f"- False-positive risk: {plan['false_positive_risk']}",
                f"- Tests: {plan['tests']}",
                f"- Migration strategy: {plan['migration_strategy']}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_audit(input_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Building local author history from %s", input_path)
    author_history = build_author_history(input_path)
    LOGGER.info("Author history contains %s authors", len(author_history))

    total_works = 0
    total_authorships = 0
    unique_work_ids: set[str] = set()
    unique_authors: set[str] = set()
    year_counts: Counter[int] = Counter()
    works_currently_lk_owned: set[str] = set()
    works_currently_keep: set[str] = set()
    works_first_author_lk: set[str] = set()
    works_corresponding_author_lk: set[str] = set()
    works_any_lk_authorship: set[str] = set()
    works_work_level_leakage: set[str] = set()
    rows: list[dict[str, Any]] = []
    rows_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, work in enumerate(iter_jsonl(input_path), 1):
        if index % 5000 == 0:
            LOGGER.info("Pass 2 audited %s works", index)
        total_works += 1
        work_id = openalex_work_id(work) or f"missing:{index}"
        unique_work_ids.add(work_id)
        year = normalize_publication_year(work.get("publication_year"))
        if year is not None:
            year_counts[year] += 1
        work_authorships = authorships(work)
        total_authorships += len(work_authorships)
        for authorship in work_authorships:
            aid = author_id(authorship)
            if aid:
                unique_authors.add(aid)

        ownership = classify_sri_lanka_ownership(work)
        if ownership.get("country_owner") == SRI_LANKA or str(ownership.get("ownership_class", "")).startswith("SL"):
            works_currently_lk_owned.add(work_id)
        if keep_in_sri_lanka_owned_dataset(work):
            works_currently_keep.add(work_id)
        first_codes = first_author_country_codes(work)
        corresponding_codes = corresponding_author_country_codes(work)
        if SRI_LANKA in first_codes:
            works_first_author_lk.add(work_id)
        if SRI_LANKA in corresponding_codes:
            works_corresponding_author_lk.add(work_id)

        authorship_lk_count = sum(1 for authorship in work_authorships if is_sri_lankan_authorship(authorship))
        work_level_lk_without_authorship = authorship_lk_count == 0 and any(
            isinstance(inst, dict) and as_text(inst.get("country_code")).upper() == SRI_LANKA
            for inst in work.get("institutions", []) or []
        )
        if work_level_lk_without_authorship:
            works_work_level_leakage.add(work_id)

        if authorship_lk_count:
            works_any_lk_authorship.add(work_id)

        for authorship in work_authorships:
            if not is_sri_lankan_authorship(authorship):
                continue
            institutions = institution_dicts(authorship)
            lk_institutions = [
                inst
                for inst in institutions
                if as_text(inst.get("country_code")).upper() == SRI_LANKA
            ]
            if not lk_institutions and SRI_LANKA in country_codes_from_authorship(authorship):
                lk_institutions = [{}]
            row = classify_row(
                work=work,
                authorship=authorship,
                institution=merge_institutions(lk_institutions),
                current_classification=as_text(ownership.get("ownership_class")),
                first_codes=first_codes,
                corresponding_codes=corresponding_codes,
                author_history=author_history,
                work_level_lk_without_authorship=work_level_lk_without_authorship,
            )
            rows.append(row)
            rows_by_work[work_id].append(row)

    currently_lk_authorships = len(rows)
    issue_work_sets = classify_work_level_issue_sets(rows_by_work)
    issue_counts = {}
    for issue in ISSUE_FIELDS:
        issue_name = issue.replace("issue_", "").upper()
        authorship_count = sum(1 for row in rows if row[issue])
        work_count = len(issue_work_sets.get(issue, set()))
        issue_counts[issue_name] = {
            "authorship_count": authorship_count,
            "percent_of_currently_lk_authorships": pct(authorship_count, currently_lk_authorships),
            "work_count": work_count,
            "percent_of_all_works": pct(work_count, len(unique_work_ids)),
        }

    primary_counts = Counter(row["primary_classification"] for row in rows)
    primary_summary = {
        name: {
            "count": primary_counts.get(name, 0),
            "percent_of_currently_lk_authorships": pct(primary_counts.get(name, 0), currently_lk_authorships),
        }
        for name in PRIMARY_CLASSIFICATIONS
    }
    strict_work_ids = {
        row["openalex_work_id"]
        for row in rows
        if row["publishable_strict_lk"] and row["openalex_work_id"]
    }
    review_work_ids = {
        row["openalex_work_id"]
        for row in rows
        if str(row["primary_classification"]).startswith("REVIEW_")
    }
    exclude_work_ids = {
        row["openalex_work_id"]
        for row in rows
        if str(row["primary_classification"]).startswith("EXCLUDE_")
    }
    issue_any_rows = [row for row in rows if any(row[issue] for issue in ISSUE_FIELDS)]
    issue_any_works = {row["openalex_work_id"] for row in issue_any_rows}

    inst_stats: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        inst = row["institution_name"] or "(missing institution)"
        inst_stats[inst]["current_lk_records"] += 1
        if row["publishable_strict_lk"]:
            inst_stats[inst]["verified"] += 1
        if str(row["primary_classification"]).startswith("REVIEW_"):
            inst_stats[inst]["review"] += 1
        if (
            str(row["primary_classification"]).startswith("EXCLUDE_")
            or row["issue_explicit_foreign_location_conflict"]
        ):
            inst_stats[inst]["foreign_conflict"] += 1
        if any(row[issue] for issue in ISSUE_FIELDS):
            inst_stats[inst]["suspicious"] += 1
    top_institutions = []
    for inst, counter in inst_stats.items():
        suspicious = counter["suspicious"]
        current = counter["current_lk_records"]
        if suspicious == 0:
            continue
        top_institutions.append(
            {
                "institution": inst,
                "current_lk_records": current,
                "verified": counter["verified"],
                "review": counter["review"],
                "foreign_conflict": counter["foreign_conflict"],
                "suspicious": suspicious,
                "error_rate": pct(suspicious, current),
            }
        )
    top_institutions.sort(key=lambda row: (row["suspicious"], row["error_rate"]), reverse=True)

    year_breakdown: dict[str, dict[str, Any]] = {}
    for row in rows:
        year = as_text(row["publication_year"]) or "unknown"
        entry = year_breakdown.setdefault(
            year,
            {
                "currently_lk_authorships": 0,
                "verified": 0,
                "review": 0,
                "exclude": 0,
                "with_issue": 0,
            },
        )
        entry["currently_lk_authorships"] += 1
        if row["publishable_strict_lk"]:
            entry["verified"] += 1
        if str(row["primary_classification"]).startswith("REVIEW_"):
            entry["review"] += 1
        if str(row["primary_classification"]).startswith("EXCLUDE_"):
            entry["exclude"] += 1
        if any(row[issue] for issue in ISSUE_FIELDS):
            entry["with_issue"] += 1
    for entry in year_breakdown.values():
        entry["issue_percent"] = pct(entry["with_issue"], entry["currently_lk_authorships"])

    issue_overlap = {}
    for left, right in combinations(ISSUE_FIELDS, 2):
        count = sum(1 for row in rows if row[left] and row[right])
        if count:
            issue_overlap[f"{left.replace('issue_', '').upper()} + {right.replace('issue_', '').upper()}"] = count

    suspicious_rows = [row for row in rows if any(row[issue] for issue in ISSUE_FIELDS)]
    manual_review_rows = [
        row for row in rows if str(row["primary_classification"]).startswith("REVIEW_")
    ]
    verified_rows = [row for row in rows if row["publishable_strict_lk"]]

    write_csv(output_dir / "lk_affiliation_audit_records.csv", suspicious_rows, CSV_FIELDS)
    write_csv(output_dir / "lk_affiliation_manual_review.csv", manual_review_rows, CSV_FIELDS)
    write_csv(output_dir / "verified_lk_authorships.csv", verified_rows, CSV_FIELDS)
    sample_counts = sample_rows(rows, output_dir)

    summary = {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "random_seed": RANDOM_SEED,
        "overall": {
            "total_works": total_works,
            "unique_openalex_work_ids": len(unique_work_ids),
            "total_authorships": total_authorships,
            "unique_authors": len(unique_authors),
            "publication_year_distribution": dict(sorted(year_counts.items())),
            "works_currently_marked_sri_lanka_owned": len(works_currently_lk_owned),
            "works_passing_keep_in_sri_lanka_owned_dataset": len(works_currently_keep),
            "works_with_first_author_lk": len(works_first_author_lk),
            "works_with_corresponding_author_lk": len(works_corresponding_author_lk),
            "works_with_any_lk_affiliation": len(works_any_lk_authorship),
            "currently_lk_authorships": currently_lk_authorships,
            "work_level_to_authorship_leakage_works": len(works_work_level_leakage),
        },
        "denominators": {
            "work_level_percentages": "unique OpenAlex work IDs",
            "authorship_level_percentages": "authorship rows currently classified as LK",
        },
        "primary_classification_counts": primary_summary,
        "issue_counts": issue_counts,
        "issue_overlap_authorship_counts": dict(sorted(issue_overlap.items(), key=lambda item: item[1], reverse=True)),
        "top_issue_combinations": top_issue_combinations(rows),
        "top_suspicious_institutions": top_institutions[:100],
        "year_breakdown": dict(sorted(year_breakdown.items())),
        "samples": sample_counts,
        "high_confidence_data": {
            "VERIFIED_LK": pct_entry(primary_counts["VERIFIED_LK"], currently_lk_authorships),
            "LK_MULTI_AFFILIATED": pct_entry(primary_counts["LK_MULTI_AFFILIATED"], currently_lk_authorships),
        },
        "potential_problems": {
            "at_least_one_issue_authorships": pct_entry(len(issue_any_rows), currently_lk_authorships),
            "at_least_one_issue_works": pct_entry(len(issue_any_works), len(unique_work_ids)),
            "requiring_review_authorships": pct_entry(len(manual_review_rows), currently_lk_authorships),
            "likely_false_positive_authorships": pct_entry(
                primary_counts["EXCLUDE_MATCH_ERROR"] + primary_counts["EXCLUDE_CONFIRMED_FOREIGN"],
                currently_lk_authorships,
            ),
            "confirmed_foreign_authorships": pct_entry(primary_counts["EXCLUDE_CONFIRMED_FOREIGN"], currently_lk_authorships),
            "normalized_lk_only_authorships": pct_entry(
                issue_counts["NORMALIZED_LK_ONLY"]["authorship_count"],
                currently_lk_authorships,
            ),
            "multinational_hq_ambiguity_authorships": pct_entry(
                issue_counts["HQ_BRANCH_CONFLICT"]["authorship_count"]
                + issue_counts["MULTINATIONAL_INSTITUTION_AMBIGUOUS"]["authorship_count"],
                currently_lk_authorships,
            ),
            "explicit_country_conflict_authorships": pct_entry(
                issue_counts["EXPLICIT_FOREIGN_LOCATION_CONFLICT"]["authorship_count"],
                currently_lk_authorships,
            ),
            "author_year_location_conflict_authorships": pct_entry(
                issue_counts["AUTHOR_YEAR_LOCATION_CONFLICT"]["authorship_count"],
                currently_lk_authorships,
            ),
            "possible_institution_matching_errors_authorships": pct_entry(
                issue_counts["POSSIBLE_INSTITUTION_MATCH_ERROR"]["authorship_count"],
                currently_lk_authorships,
            ),
            "missing_raw_affiliation_location_evidence_authorships": pct_entry(
                issue_counts["LK_LOCATION_UNVERIFIED"]["authorship_count"],
                currently_lk_authorships,
            ),
        },
        "publication_impact": {
            "current_dataset_size": len(unique_work_ids),
            "strict_verified_dataset_size": len(strict_work_ids),
            "records_removed": len(unique_work_ids - strict_work_ids),
            "records_sent_to_review": len(review_work_ids),
            "percentage_retained": pct(len(strict_work_ids), len(unique_work_ids)),
            "percentage_excluded": pct(len(exclude_work_ids), len(unique_work_ids)),
            "percentage_uncertain": pct(len(review_work_ids), len(unique_work_ids)),
        },
        "stage_classification": {
            "stage_a_local_deterministic_authorships": currently_lk_authorships,
            "stage_b_openalex_author_history_candidates": issue_counts["AUTHOR_YEAR_LOCATION_CONFLICT"]["authorship_count"]
            + issue_counts["POSSIBLE_AUTHOR_IDENTITY_ERROR"]["authorship_count"],
            "stage_c_orcid_external_validation_candidates": len(manual_review_rows),
        },
        "implementation_plan": implementation_plan(),
    }

    summary_path = output_dir / "lk_affiliation_audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(output_dir / "lk_affiliation_audit_report.md", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "openalex" / "openalex_sri_lanka_works.jsonl",
        help="Path to raw OpenAlex works JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "openalex_lk_affiliation_audit",
        help="Directory for audit artifacts.",
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
        "Audit complete: %s works, %s current LK authorship rows, strict works=%s",
        summary["overall"]["unique_openalex_work_ids"],
        summary["overall"]["currently_lk_authorships"],
        summary["publication_impact"]["strict_verified_dataset_size"],
    )


if __name__ == "__main__":
    main()
