"""National institution registry, affiliation parsing and collaboration typing.

The registry resolves free-text institution and affiliation strings onto a
controlled national institution list. Matching is deterministic: a normalized
lookup key is built for every registry alias and for every incoming name, and
the two are compared exactly. No fuzzy or probabilistic matching happens here,
so a resolution can always be explained by pointing at the alias that produced
it.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_analytics.config import FrameworkConfig


# Source identifiers that name a platform rather than a research institution.
# SLJOL is the national journal-hosting platform: its records belong to many
# different universities, so a record's institution can never be inferred from
# the fact that it was collected there.
NON_INSTITUTION_SOURCE_IDS = frozenset({"sljol", "learn_dspace_ac_lk", "private_other"})

# Leading segments that describe a unit inside an institution rather than the
# institution itself. Only stripped when a further comma-separated segment
# remains, so a standalone "Department of Archaeology" is left untouched.
SUBUNIT_PREFIX_RE = re.compile(
    r"^(?:the\s+)?(?:department|dept\.?|faculty|division|unit|laboratory|lab"
    r"|section|chair|clinic|ward|library)\b",
    re.IGNORECASE,
)

# Trailing segments that state the country rather than part of the name.
TRAILING_COUNTRY_RE = re.compile(
    r",\s*(?:sri\s*lanka|srilanka|lk|ceylon)\s*$",
    re.IGNORECASE,
)

WHITESPACE_RE = re.compile(r"\s+")

# Abbreviations expanded before building a lookup key so that "Univ. of Colombo"
# and "University of Colombo" collapse onto the same key.
ABBREVIATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\buniv\.?\b", re.IGNORECASE), "university"),
    (re.compile(r"\binst\.?\b", re.IGNORECASE), "institute"),
    (re.compile(r"\bnatl\.?\b", re.IGNORECASE), "national"),
    (re.compile(r"\bsc\.?\b", re.IGNORECASE), "science"),
    (re.compile(r"\btech\.?\b", re.IGNORECASE), "technology"),
    (re.compile(r"\bctr\.?\b", re.IGNORECASE), "centre"),
    (re.compile(r"\bcenter\b", re.IGNORECASE), "centre"),
    (re.compile(r"\bhosp\.?\b", re.IGNORECASE), "hospital"),
    (re.compile(r"&", re.IGNORECASE), " and "),
)

ISO_3166_1_ALPHA_2 = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
    BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR
    CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF
    PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI
    SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
    TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split()
    # XK is the user-assigned code for Kosovo. It is not in the official ISO
    # 3166-1 list but OpenAlex emits it, so it is accepted rather than dropped.
    + ["XK"]
)

# Best-effort country-name recognition for affiliation strings. Deliberately
# limited to names actually observed in the corpus plus the most common research
# partner countries; unrecognised names simply yield no hint.
COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "sri lanka": "LK",
    "srilanka": "LK",
    "ceylon": "LK",
    "australia": "AU",
    "bangladesh": "BD",
    "belgium": "BE",
    "bhutan": "BT",
    "brazil": "BR",
    "canada": "CA",
    "china": "CN",
    "denmark": "DK",
    "egypt": "EG",
    "england": "GB",
    "ethiopia": "ET",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "ghana": "GH",
    "hong kong": "HK",
    "india": "IN",
    "indonesia": "ID",
    "iran": "IR",
    "iraq": "IQ",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "kenya": "KE",
    "malaysia": "MY",
    "maldives": "MV",
    "mexico": "MX",
    "nepal": "NP",
    "netherlands": "NL",
    "new zealand": "NZ",
    "nigeria": "NG",
    "norway": "NO",
    "pakistan": "PK",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "qatar": "QA",
    "russia": "RU",
    "saudi arabia": "SA",
    "scotland": "GB",
    "singapore": "SG",
    "south africa": "ZA",
    "south korea": "KR",
    "korea": "KR",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "taiwan": "TW",
    "tanzania": "TZ",
    "thailand": "TH",
    "turkey": "TR",
    "uganda": "UG",
    "ukraine": "UA",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "uk": "GB",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "vietnam": "VN",
    "wales": "GB",
    "zimbabwe": "ZW",
}


@dataclass
class Institution:
    institution_id: str
    preferred_name: str
    country_code: str | None = None
    alternative_names: set[str] = field(default_factory=set)
    ror_id: str | None = None
    parent_institution_id: str | None = None
    institution_type: str | None = None
    source_institution_ids: set[str] = field(default_factory=set)


class NationalInstitutionRegistry:
    """Controlled national institution registry with alias lookup."""

    def __init__(self, institutions: dict[str, Institution]) -> None:
        self.institutions = institutions
        self.alias_index: dict[str, str] = {}
        self.source_id_index: dict[str, str] = {}
        for institution in institutions.values():
            self._index_alias(institution.preferred_name, institution.institution_id)
            for alias in institution.alternative_names:
                self._index_alias(alias, institution.institution_id)
            for source_id in institution.source_institution_ids:
                self.source_id_index[source_id.strip().casefold()] = institution.institution_id

    def _index_alias(self, alias: str, institution_id: str) -> None:
        key = normalize_lookup_key(alias)
        if key:
            self.alias_index.setdefault(key, institution_id)

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        country_code: str | None = None,
        institution_id_column: str = "institution_id",
        preferred_name_column: str = "preferred_name",
        alternative_name_column: str = "alternative_name",
        country_code_column: str = "country_code",
        ror_id_column: str = "ror_id",
        parent_id_column: str = "parent_institution_id",
        institution_type_column: str = "institution_type",
        source_institution_id_column: str = "source_institution_id",
    ) -> "NationalInstitutionRegistry":
        institutions: dict[str, Institution] = {}
        with Path(path).open(newline="", encoding="utf-8") as registry_file:
            for row in csv.DictReader(registry_file):
                row_country = row.get(country_code_column) or country_code
                if country_code and row_country and row_country != country_code:
                    continue
                institution_id = (row.get(institution_id_column) or "").strip()
                preferred_name = (row.get(preferred_name_column) or "").strip()
                alternative_name = (row.get(alternative_name_column) or "").strip()
                if not institution_id or not preferred_name:
                    continue

                institution = institutions.setdefault(
                    institution_id,
                    Institution(
                        institution_id=institution_id,
                        preferred_name=preferred_name,
                        country_code=row_country,
                        ror_id=(row.get(ror_id_column) or "").strip() or None,
                        parent_institution_id=(row.get(parent_id_column) or "").strip() or None,
                        institution_type=(row.get(institution_type_column) or "").strip() or None,
                    ),
                )
                if alternative_name:
                    institution.alternative_names.add(alternative_name)
                source_id = (row.get(source_institution_id_column) or "").strip()
                if source_id and source_id.casefold() not in NON_INSTITUTION_SOURCE_IDS:
                    institution.source_institution_ids.add(source_id)
        return cls(institutions)

    @classmethod
    def from_config(cls, config: FrameworkConfig) -> "NationalInstitutionRegistry | None":
        if not config.institution_registry.path:
            return None
        return cls.from_csv(
            config.institution_registry.path,
            country_code=config.project.country_code,
            institution_id_column=config.institution_registry.institution_id_column,
            preferred_name_column=config.institution_registry.preferred_name_column,
            alternative_name_column=config.institution_registry.alternative_name_column,
            country_code_column=config.institution_registry.country_code_column,
            ror_id_column=config.institution_registry.ror_id_column,
            parent_id_column=config.institution_registry.parent_id_column,
        )

    def resolve_name(self, name: Any) -> Institution | None:
        """Resolve a single institution or affiliation string.

        Tries the whole string first. If that misses, retries against
        progressively shorter comma-prefixes, which strips address tails such as
        "University of Peradeniya, Peradeniya 20400" down to a name the registry
        knows. Shortening stops before the first segment, so a name is never
        reduced past its own head.
        """

        for candidate in _lookup_candidates(name):
            institution_id = self.alias_index.get(candidate)
            if institution_id:
                return self.institutions.get(institution_id)
        return None

    def resolve_names(self, names: Any) -> tuple[list[Institution], list[str]]:
        resolved: list[Institution] = []
        unresolved: list[str] = []
        for name in split_multi_value(names):
            institution = self.resolve_name(name)
            if institution is not None:
                if institution not in resolved:
                    resolved.append(institution)
            elif name:
                unresolved.append(name)
        return resolved, unresolved

    def resolve_from_source_id(self, source_institution_id: Any) -> list[Institution]:
        """Resolve repository collection codes such as ``uom`` onto institutions.

        Platform identifiers listed in :data:`NON_INSTITUTION_SOURCE_IDS` never
        resolve, because they identify where a record was collected rather than
        which institution produced it.
        """

        resolved: list[Institution] = []
        for raw in split_multi_value(source_institution_id):
            code = raw.strip().casefold()
            if not code or code in NON_INSTITUTION_SOURCE_IDS:
                continue
            institution_id = self.source_id_index.get(code) or self.alias_index.get(
                normalize_lookup_key(code)
            )
            if not institution_id:
                continue
            institution = self.institutions.get(institution_id)
            if institution is not None and institution not in resolved:
                resolved.append(institution)
        return resolved


def enrich_national_context(
    record: dict[str, Any],
    registry: NationalInstitutionRegistry | None,
    *,
    national_country_code: str | None,
) -> dict[str, Any]:
    """Mark national association and collaboration type without dropping records."""

    enriched = dict(record)
    if registry is None:
        enriched["national_association"] = _has_country(record, national_country_code)
        enriched["collaboration_type"] = (
            "unresolved_affiliation"
            if not enriched["national_association"]
            else "international_collaboration"
            if _has_international_country(record, national_country_code)
            else "domestic_single_institution"
        )
        enriched["national_institution_ids"] = []
        enriched["national_institutions"] = []
        enriched["resolved_institutions"] = []
        enriched["unresolved_institutions"] = split_multi_value(record.get("institutions"))
        enriched["collaboration_scope"] = collaboration_scope(enriched["collaboration_type"])
        return enriched

    resolved, unresolved = registry.resolve_names(record.get("institutions"))
    national_institution_ids = [institution.institution_id for institution in resolved]
    national_institutions = [institution.preferred_name for institution in resolved]
    enriched["national_association"] = bool(national_institution_ids)
    enriched["national_institution_ids"] = national_institution_ids
    enriched["national_institutions"] = national_institutions
    enriched["resolved_institutions"] = national_institutions
    enriched["unresolved_institutions"] = unresolved
    enriched["collaboration_type"] = classify_collaboration(
        record,
        national_institution_ids=national_institution_ids,
        unresolved_institutions=unresolved,
        national_country_code=national_country_code,
    )
    enriched["collaboration_scope"] = collaboration_scope(enriched["collaboration_type"])
    return enriched


def classify_collaboration(
    record: dict[str, Any],
    *,
    national_institution_ids: list[str],
    unresolved_institutions: list[str],
    national_country_code: str | None,
) -> str:
    """Classify national collaboration while retaining international records."""

    if not national_institution_ids:
        return "unresolved_affiliation" if unresolved_institutions else "not_national"
    if _has_international_country(record, national_country_code):
        return "international_collaboration"
    if len(set(national_institution_ids)) > 1:
        return "domestic_multi_institution"
    return "domestic_single_institution"


def collaboration_scope(collaboration_type: str | None) -> str:
    """Reduce the five collaboration types to local / international / unknown.

    The work plan asks separately for local and international collaboration
    records; this is that coarser view, derived from ``collaboration_type``
    rather than replacing it.
    """

    if collaboration_type == "international_collaboration":
        return "international"
    if collaboration_type in {"domestic_single_institution", "domestic_multi_institution"}:
        return "local"
    return "unknown"


def standardize_institution_name(value: Any) -> str | None:
    """Tidy an institution name for display without changing its identity."""

    if value is None:
        return None
    text = str(value).replace("�", "").replace("’", "'").strip()
    text = WHITESPACE_RE.sub(" ", text)
    text = text.strip(" ,;.")
    return text or None


def normalize_lookup_key(value: Any) -> str:
    """Build the deterministic matching key used by the alias index.

    Applied identically to registry aliases and to incoming names, so any change
    here affects both sides symmetrically.
    """

    if value is None:
        return ""
    text = str(value)
    if not text.strip():
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.replace("�", " ").replace("’", "'")
    text = _strip_subunit_prefixes(text)
    text = TRAILING_COUNTRY_RE.sub("", text)

    for pattern, replacement in ABBREVIATION_PATTERNS:
        text = pattern.sub(replacement, text)

    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return text.strip()


def _lookup_candidates(value: Any) -> list[str]:
    """Lookup keys to try for a name, from the most to the least complete."""

    full_key = normalize_lookup_key(value)
    if not full_key:
        return []

    candidates = [full_key]
    if value is None:
        return candidates

    segments = [
        segment.strip()
        for segment in _strip_subunit_prefixes(str(value)).split(",")
        if segment.strip()
    ]
    for length in range(len(segments) - 1, 0, -1):
        key = normalize_lookup_key(", ".join(segments[:length]))
        if key and key not in candidates:
            candidates.append(key)
    return candidates


def _strip_subunit_prefixes(text: str) -> str:
    """Drop leading department/faculty segments when a parent segment remains."""

    segments = [segment.strip() for segment in text.split(",")]
    while len(segments) > 1 and SUBUNIT_PREFIX_RE.match(segments[0]):
        segments.pop(0)
    return ", ".join(segment for segment in segments if segment)


def parse_affiliation(value: Any) -> tuple[list[str], list[str]]:
    """Split an affiliation string into institution names and country hints.

    Affiliation values in this corpus are semicolon-joined institution names,
    occasionally carrying a country name in the final segment. Returns the
    institution names with sub-unit prefixes removed, plus any ISO-2 country
    codes recognised in the text.
    """

    institutions: list[str] = []
    country_hints: list[str] = []

    for part in split_multi_value(value):
        cleaned = standardize_institution_name(_strip_subunit_prefixes(part))
        if not cleaned:
            continue

        for name, code in _country_matches(part):
            if code not in country_hints:
                country_hints.append(code)
            # Drop the country only when it is a comma-separated address tail.
            # Without the comma guard this truncates institutions whose own name
            # ends in a country: "Rajarata University of Sri Lanka" must not
            # become "Rajarata University of".
            cleaned = re.sub(
                rf",\s*{re.escape(name)}\s*$", "", cleaned, flags=re.IGNORECASE
            ).strip(" ,")

        cleaned = standardize_institution_name(cleaned)
        if cleaned and cleaned not in institutions:
            institutions.append(cleaned)

    return institutions, country_hints


def _country_matches(text: str) -> list[tuple[str, str]]:
    lowered = f" {re.sub(r'[^a-z ]+', ' ', text.lower())} "
    matches: list[tuple[str, str]] = []
    for name, code in COUNTRY_NAME_TO_CODE.items():
        if f" {name} " in lowered:
            matches.append((name, code))
    # Prefer longer names so "united states" wins over a bare "us" style match.
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches


def standardize_country(value: Any) -> str | None:
    """Normalize a country value to an ISO 3166-1 alpha-2 code."""

    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return None

    upper = text.upper()
    if len(upper) == 2 and upper in ISO_3166_1_ALPHA_2:
        return upper

    named = COUNTRY_NAME_TO_CODE.get(re.sub(r"[^a-z ]+", " ", text.lower()).strip())
    if named:
        return named
    return None


def standardize_countries(value: Any) -> tuple[list[str], list[str]]:
    """Standardize a multi-value country field into codes and unrecognised values."""

    codes: list[str] = []
    unrecognised: list[str] = []
    for item in split_multi_value(value):
        code = standardize_country(item)
        if code:
            if code not in codes:
                codes.append(code)
        else:
            unrecognised.append(item)
    return codes, unrecognised


def split_multi_value(value: Any) -> list[str]:
    """Split a multi-value field on semicolons only.

    Institution, affiliation and country names legitimately contain commas
    ("Eastern University, Sri Lanka"), so comma splitting would fragment a
    single value into meaningless parts.
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return []
    return [item.strip() for item in text.split(";") if item.strip()]


def _as_list(value: Any) -> list[str]:
    return split_multi_value(value)


def _normalize_name(value: str) -> str:
    return normalize_lookup_key(value)


def _has_country(record: dict[str, Any], country_code: str | None) -> bool:
    if not country_code:
        return False
    return country_code in set(split_multi_value(record.get("countries")))


def _has_international_country(record: dict[str, Any], national_country_code: str | None) -> bool:
    countries = set(split_multi_value(record.get("countries")))
    if not countries or not national_country_code:
        return False
    return any(country != national_country_code for country in countries)
