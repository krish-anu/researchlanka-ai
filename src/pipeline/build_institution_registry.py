"""Generate the national institution registry from observed dataset values.

The registry seed is the ``sri_lankan_institutions`` column of the merged
dataset. That column is OpenAlex's own country-filtered institution list, so
every value in it is already confirmed to be a Sri Lankan organisation and no
separate country check is needed.

Existing institution identifiers are preserved: an institution that already has
an ``LK###`` identifier keeps it, so identifiers that have already been written
into exported datasets never shift meaning. New institutions are appended with
the next free identifier.

The output is written for review -- run this, read the diff, correct anything
mis-typed, then commit.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_analytics.institutions import (  # noqa: E402
    NON_INSTITUTION_SOURCE_IDS,
    normalize_lookup_key,
    standardize_institution_name,
)


DEFAULT_INPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
)
DEFAULT_REGISTRY_CSV = PROJECT_ROOT / "configurations" / "sri_lanka" / "institutions.csv"
DEFAULT_REPOSITORIES_JSON = PROJECT_ROOT / "data" / "config" / "repositories.json"

SEED_COLUMN = "sri_lankan_institutions"
COUNTRY_CODE = "LK"

REGISTRY_FIELDNAMES = (
    "institution_id",
    "preferred_name",
    "alternative_name",
    "country_code",
    "ror_id",
    "parent_institution_id",
    "institution_type",
    "source_institution_id",
)

# Repository collection codes mapped onto the institution name as it appears in
# the dataset. Written out explicitly rather than matched heuristically, because
# repositories.json names carry parenthetical qualifiers ("University of Colombo
# (main)") that do not appear in publication metadata.
SOURCE_ID_TO_INSTITUTION: dict[str, str] = {
    "uom": "University of Moratuwa",
    "cmb": "University of Colombo",
    "ucsc": "University of Colombo",
    "pdn": "University of Peradeniya",
    "kln": "University of Kelaniya",
    "sjp": "University of Sri Jayewardenepura",
    "jfn_research": "University of Jaffna",
    "jfn_medicine": "University of Jaffna",
    "seu": "South Eastern University of Sri Lanka",
    "ou": "Open University of Sri Lanka",
    "vpa": "University of the Visual & Performing Arts",
    "rjt": "Rajarata University of Sri Lanka",
    "busl": "Buddhasravaka Bhiksu University",
    "sltc": "Sri Lanka Technological Campus",
    "ruh": "University of Ruhuna",
    "esn": "Eastern University, Sri Lanka",
    "sab": "Sabaragamuwa University of Sri Lanka",
    "wyb": "Wayamba University of Sri Lanka",
    "uwu": "Uva Wellassa University",
    "vau": "University of Vavuniya",
    "kdu": "General Sir John Kotelawala Defence University",
    "nsf": "National Science Foundation of Sri Lanka",
    "sliit": "Sri Lanka Institute of Information Technology",
    "bpu": "Buddhist and Pali University of Sri Lanka",
    "ifs": "National Institute of Fundamental Studies",
    "pgim": "Post Graduate Institute of Medicine, University of Colombo, Sri Lanka",
    "ncas": "National Centre for Advanced Studies in Humanities and Social Sciences",
    "gwuas": "Gampaha Wickramarachchi University of Ayurveda",
    "ocu": "Ocean University of Sri Lanka",
    "uovt": "University of Vocational Technology",
    "pgia": "Postgraduate Institute of Agriculture",
    "pgis": "Postgraduate Institute of Science",
    "pim": "Postgraduate Institute of Management",
    "pgipbs": "Postgraduate Institute of Pali and Buddhist Studies",
}

# Acronyms and name variants that appear in the corpus but are not derivable
# from the preferred name. Auto-generating acronyms was rejected: it produces
# collisions between short names and creates false matches.
CURATED_ALIASES: dict[str, tuple[str, ...]] = {
    "University of Colombo": ("UOC", "Colombo University", "University of Colombo, Sri Lanka"),
    "University of Peradeniya": ("UOP", "PDN", "University of Peradeniya, Sri Lanka"),
    "University of Moratuwa": ("UOM", "Univ. of Moratuwa", "University of Moratuwa, Sri Lanka"),
    "University of Jaffna": ("UOJ", "Jaffna University"),
    "University of Sri Jayewardenepura": (
        "USJ",
        "USJP",
        "University of Sri Jayewardenapura",
        "Sri Jayewardenepura University",
    ),
    "University of Kelaniya": ("UOK", "Kelaniya University"),
    "University of Ruhuna": ("UOR", "RUH", "Ruhuna University"),
    "Rajarata University of Sri Lanka": ("RUSL", "Rajarata University"),
    "Sabaragamuwa University of Sri Lanka": ("SUSL", "Sabaragamuwa University"),
    "Wayamba University of Sri Lanka": ("WUSL", "Wayamba University"),
    "Eastern University, Sri Lanka": ("EUSL", "Eastern University"),
    "South Eastern University of Sri Lanka": ("SEUSL", "SEU", "South Eastern University"),
    "Open University of Sri Lanka": ("OUSL", "The Open University of Sri Lanka"),
    "Uva Wellassa University": ("UWU", "Uva Wellassa University of Sri Lanka"),
    "General Sir John Kotelawala Defence University": (
        "KDU",
        "Kotelawala Defence University",
        "General Sir John Kotelawala Defense University",
    ),
    "Sri Lanka Institute of Information Technology": ("SLIIT",),
    "Sri Lanka Technological Campus": ("SLTC", "SLTC Research University"),
    "National Science Foundation of Sri Lanka": (
        "NSF",
        "National Science Foundation",
        "National Science Foundation, Sri Lanka",
    ),
    "National Institute of Fundamental Studies": (
        "NIFS",
        "Institute of Fundamental Studies",
        "IFS",
    ),
    "Buddhasravaka Bhiksu University": (
        "Bhiksu University of Sri Lanka",
        "Bhiksu University Of Sri Lanka Anuradhapura",
        "BUSL",
    ),
    "University of the Visual & Performing Arts": (
        "UVPA",
        "University of the Visual and Performing Arts",
        "University of Visual & Performing Arts",
    ),
    "National Hospital of Sri Lanka": ("NHSL",),
    "Institute of Policy Studies of Sri Lanka": ("IPS",),
    "Industrial Technology Institute": ("ITI",),
    "Medical Research Institute": ("MRI",),
    "Informatics Institute of Technology": ("IIT",),
    "Buddhist and Pali University of Sri Lanka": ("BPU",),
    "University of Vavuniya": ("Vavuniya University",),
}

# Keyword -> institution_type, evaluated in order. First match wins.
TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("teaching hospital", "hospital", "infirmary"), "hospital"),
    (("university", "campus"), "university"),
    (("ministry", "department of", "council", "commission", "authority", "agency",
      "university grants"), "government_body"),
    (("(pvt)", "pvt ltd", "wso2", "glaxosmithkline", "genetech", "wijeya", "greentech",
      "nawaloka", "durdans", "lanka hospitals"), "company"),
    (("association", "society", "trust", "collaboration", "federation", "alternatives",
      "human rights", "initiative", "fund"), "ngo_or_association"),
    (("institute", "research", "centre", "center", "foundation", "studies"),
     "research_institute"),
    (("college", "school"), "college"),
)


def read_seed_counts(input_csv: Path, *, column: str = SEED_COLUMN) -> Counter[str]:
    """Count distinct institution names in the confirmed-national column."""

    csv.field_size_limit(10**9)
    counts: Counter[str] = Counter()
    with input_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if column not in (reader.fieldnames or ()):
            raise ValueError(f"Input dataset must include a {column} column.")
        for row in reader:
            for raw in (row.get(column) or "").split(";"):
                name = standardize_institution_name(raw)
                if name:
                    counts[name] += 1
    return counts


def read_existing_registry(registry_csv: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return existing institutions by id, plus a lookup-key -> id index."""

    existing: dict[str, dict[str, Any]] = {}
    key_to_id: dict[str, str] = {}
    if not registry_csv.exists():
        return existing, key_to_id

    with registry_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            institution_id = (row.get("institution_id") or "").strip()
            preferred_name = (row.get("preferred_name") or "").strip()
            if not institution_id or not preferred_name:
                continue
            entry = existing.setdefault(
                institution_id,
                {
                    "institution_id": institution_id,
                    "preferred_name": preferred_name,
                    "aliases": set(),
                    "ror_id": (row.get("ror_id") or "").strip(),
                    "parent_institution_id": (row.get("parent_institution_id") or "").strip(),
                    "institution_type": (row.get("institution_type") or "").strip(),
                },
            )
            for candidate in (preferred_name, (row.get("alternative_name") or "").strip()):
                if candidate:
                    entry["aliases"].add(candidate)
                    key_to_id.setdefault(normalize_lookup_key(candidate), institution_id)
    return existing, key_to_id


def infer_institution_type(name: str) -> str:
    lowered = name.lower()
    for keywords, institution_type in TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return institution_type
    return "other"


def next_institution_id(used: set[str], *, prefix: str = COUNTRY_CODE) -> str:
    index = 1
    while f"{prefix}{index:03d}" in used:
        index += 1
    return f"{prefix}{index:03d}"


def build_registry_rows(
    seed_counts: Mapping[str, int],
    existing: dict[str, dict[str, Any]],
    key_to_id: dict[str, str],
    source_id_map: dict[str, str],
) -> list[dict[str, str]]:
    """Assemble registry rows, preserving already-assigned identifiers."""

    institution_source_ids: dict[str, set[str]] = {}
    for source_id, institution_name in source_id_map.items():
        if source_id.casefold() in NON_INSTITUTION_SOURCE_IDS:
            continue
        institution_source_ids.setdefault(normalize_lookup_key(institution_name), set()).add(
            source_id
        )

    # Curated aliases double as merge hints. Registering them before seeding
    # means a dataset spelling such as "National Science Foundation of Sri
    # Lanka" attaches to the existing "National Science Foundation" entry
    # instead of being created as a second institution.
    for preferred_name, aliases in CURATED_ALIASES.items():
        candidate_keys = [normalize_lookup_key(preferred_name)]
        candidate_keys.extend(normalize_lookup_key(alias) for alias in aliases)
        matched_id = next(
            (key_to_id[key] for key in candidate_keys if key in key_to_id),
            None,
        )
        if matched_id is None:
            continue
        for key in candidate_keys:
            if key:
                key_to_id.setdefault(key, matched_id)

    used_ids = set(existing)
    records: dict[str, dict[str, Any]] = {}

    # Existing institutions come first so their identifiers stay stable even if
    # they no longer appear in the dataset.
    for institution_id, entry in existing.items():
        records[institution_id] = {
            "institution_id": institution_id,
            "preferred_name": entry["preferred_name"],
            "aliases": set(entry["aliases"]),
            "ror_id": entry["ror_id"],
            "parent_institution_id": entry["parent_institution_id"],
            "institution_type": entry["institution_type"],
            "source_ids": set(),
            "mentions": 0,
        }

    # Highest mention count first, so the most common spelling of a name becomes
    # the preferred name when several spellings collapse onto one institution.
    ordered_seed = sorted(seed_counts.items(), key=lambda item: (-item[1], item[0]))
    for name, mentions in ordered_seed:
        key = normalize_lookup_key(name)
        institution_id = key_to_id.get(key)
        if institution_id is None:
            institution_id = next_institution_id(used_ids)
            used_ids.add(institution_id)
            key_to_id[key] = institution_id
            records[institution_id] = {
                "institution_id": institution_id,
                "preferred_name": name,
                "aliases": {name},
                "ror_id": "",
                "parent_institution_id": "",
                "institution_type": infer_institution_type(name),
                "source_ids": set(),
                "mentions": 0,
            }
        record = records[institution_id]
        record["aliases"].add(name)
        record["mentions"] += mentions
        if not record["institution_type"]:
            record["institution_type"] = infer_institution_type(record["preferred_name"])

    # Curated aliases and repository codes, attached by lookup key.
    for preferred_name, aliases in CURATED_ALIASES.items():
        institution_id = key_to_id.get(normalize_lookup_key(preferred_name))
        if institution_id and institution_id in records:
            records[institution_id]["aliases"].update(aliases)

    for key, source_ids in institution_source_ids.items():
        institution_id = key_to_id.get(key)
        if institution_id and institution_id in records:
            records[institution_id]["source_ids"].update(source_ids)

    rows: list[dict[str, str]] = []
    for record in sorted(records.values(), key=lambda item: item["institution_id"]):
        aliases = sorted(record["aliases"], key=lambda alias: (alias != record["preferred_name"], alias.lower()))
        source_ids = sorted(record["source_ids"]) or [""]
        institution_type = record["institution_type"] or infer_institution_type(
            record["preferred_name"]
        )
        # One row per alias; the source id rides on the first row of each block.
        for position, alias in enumerate(aliases):
            rows.append(
                {
                    "institution_id": record["institution_id"],
                    "preferred_name": record["preferred_name"],
                    "alternative_name": alias,
                    "country_code": COUNTRY_CODE,
                    "ror_id": record["ror_id"],
                    "parent_institution_id": record["parent_institution_id"],
                    "institution_type": institution_type,
                    "source_institution_id": (
                        source_ids[position] if position < len(source_ids) else ""
                    ),
                }
            )
        # Any remaining source ids need their own rows.
        for source_id in source_ids[len(aliases):]:
            rows.append(
                {
                    "institution_id": record["institution_id"],
                    "preferred_name": record["preferred_name"],
                    "alternative_name": record["preferred_name"],
                    "country_code": COUNTRY_CODE,
                    "ror_id": record["ror_id"],
                    "parent_institution_id": record["parent_institution_id"],
                    "institution_type": institution_type,
                    "source_institution_id": source_id,
                }
            )
    return rows


def find_possible_duplicates(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Flag institutions whose names nest inside one another, for hand review.

    Nesting is the shape a missed merge takes ("National Science Foundation" vs
    "National Science Foundation of Sri Lanka"). Reported, never merged
    automatically -- distinct institutions can legitimately nest.
    """

    preferred: dict[str, str] = {}
    for row in rows:
        preferred.setdefault(row["institution_id"], row["preferred_name"])

    keyed = [(institution_id, normalize_lookup_key(name)) for institution_id, name in preferred.items()]
    duplicates: list[tuple[str, str]] = []
    for index, (left_id, left_key) in enumerate(keyed):
        for right_id, right_key in keyed[index + 1 :]:
            if not left_key or not right_key:
                continue
            if left_key in right_key or right_key in left_key:
                duplicates.append(
                    (f"{left_id} {preferred[left_id]}", f"{right_id} {preferred[right_id]}")
                )
    return duplicates


def load_source_id_map(repositories_json: Path) -> dict[str, str]:
    """Load repository codes, falling back to the curated map when absent."""

    if not repositories_json.exists():
        return dict(SOURCE_ID_TO_INSTITUTION)
    data = json.loads(repositories_json.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else next(
        (value for value in data.values() if isinstance(value, list)), []
    )
    known_codes = {str(entry.get("id") or "").strip() for entry in entries if isinstance(entry, dict)}
    return {
        source_id: name
        for source_id, name in SOURCE_ID_TO_INSTITUTION.items()
        if not known_codes or source_id in known_codes
    }


def write_registry(rows: list[dict[str, str]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REGISTRY_FIELDNAMES))
        writer.writeheader()
        writer.writerows(rows)


def build_institution_registry(
    input_csv: Path,
    registry_csv: Path,
    repositories_json: Path,
) -> list[dict[str, str]]:
    seed_counts = read_seed_counts(input_csv)
    existing, key_to_id = read_existing_registry(registry_csv)
    source_id_map = load_source_id_map(repositories_json)
    rows = build_registry_rows(seed_counts, existing, key_to_id, source_id_map)
    write_registry(rows, registry_csv)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the national institution registry from dataset values."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--repositories-json", type=Path, default=DEFAULT_REPOSITORIES_JSON)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_institution_registry(args.input_csv, args.registry_csv, args.repositories_json)
    institutions = {row["institution_id"] for row in rows}
    with_source_id = {row["institution_id"] for row in rows if row["source_institution_id"]}

    print("Done.")
    print(f"  Institutions: {len(institutions):,}")
    print(f"  Alias rows: {len(rows):,}")
    print(f"  Institutions with a repository source id: {len(with_source_id):,}")
    print(f"  Registry: {args.registry_csv}")

    duplicates = find_possible_duplicates(rows)
    if duplicates:
        print(f"\n  Possible duplicates needing review ({len(duplicates)}):")
        for left, right in duplicates:
            print(f"    {left}  <->  {right}")
    print("\n  Review the diff before committing.")


if __name__ == "__main__":
    main()
