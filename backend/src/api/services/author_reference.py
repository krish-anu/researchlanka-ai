"""Reference data for author tools: institutions, categories, author names.

* Institutions come from the Sri Lankan registry the pipeline normalises
  against (`configurations/sri_lanka/institutions.csv`) plus every
  institution label already in the public dataset, so an author picking an
  institution lands on the same label institution rankings count.
* Categories are the field/subfield taxonomy the hierarchical classifier was
  trained on (`category_hierarchy.json`), so an author-added publication files
  under the same Topics & fields entries as harvested ones.
* Author names are the spellings already printed in the dataset. One person
  often appears under several, which is why a verified profile can claim more
  than one.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from src.api.core.serializers import normalize_value, split_semicolon_value


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_CSV = PROJECT_ROOT / "configurations" / "sri_lanka" / "institutions.csv"
TAXONOMY_JSON = PROJECT_ROOT / "category_hierarchy.json"
SRI_LANKA = "LK"
LOOKUP_LIMIT = 15
MIN_LOOKUP_LENGTH = 2
KEY_PATTERN = re.compile(r"[^a-z0-9]+")


def institution_key(name: Any) -> str:
    """Comparable form of an institution name: no accents, case or punctuation."""

    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return KEY_PATTERN.sub(" ", text.casefold()).strip()


# ------------------------------------------------------------ institutions


@lru_cache(maxsize=1)
def institution_registry() -> dict[str, dict[str, str]]:
    """Alias key -> {"label": preferred name, "country_code": ...}."""

    registry: dict[str, dict[str, str]] = {}
    try:
        with REGISTRY_CSV.open(encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                preferred = (row.get("preferred_name") or "").strip()
                if not preferred:
                    continue
                entry = {"label": preferred, "country_code": (row.get("country_code") or SRI_LANKA).strip().upper()}
                for alias in (preferred, row.get("alternative_name")):
                    key = institution_key(alias)
                    if key:
                        registry.setdefault(key, entry)
    except OSError as exc:
        logger.warning("Institution registry unavailable at %s: %s", REGISTRY_CSV, exc)
    return registry


def canonical_institution(name: Any) -> dict[str, Any]:
    """The registry label for a name, or the name itself when it is not registered."""

    text = " ".join(str(name or "").split())
    entry = institution_registry().get(institution_key(text))
    if entry:
        return {"label": entry["label"], "country_code": entry["country_code"], "registered": True}
    return {"label": text, "country_code": None, "registered": False}


def lookup_institutions(connection: Any, query: str, *, limit: int = LOOKUP_LIMIT) -> list[dict[str, Any]]:
    """Registry and dataset institutions matching a typed fragment, most-published first."""

    term = " ".join(str(query or "").split())
    if len(term) < MIN_LOOKUP_LENGTH:
        return []
    key = institution_key(term)
    matches: dict[str, dict[str, Any]] = {}

    # Every preferred name is also an alias key, and aliases ("Colombo
    # University", "cmb") find the preferred name too.
    for alias_key, entry in institution_registry().items():
        if key in alias_key:
            matches.setdefault(
                entry["label"].casefold(),
                {
                    "label": entry["label"],
                    "country_code": entry["country_code"],
                    "sri_lankan": entry["country_code"] == SRI_LANKA,
                    "registered": True,
                    "publication_count": 0,
                },
            )

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT btrim(item.value) AS label, count(*) AS publication_count,
                   bool_or(position(lower(btrim(item.value)) in lower(coalesce(p.sri_lankan_institutions, ''))) > 0)
                       AS sri_lankan
            FROM public_eligible_publications p,
                 regexp_split_to_table(coalesce(p.institutions, ''), ';') AS item(value)
            WHERE btrim(item.value) ILIKE %s
            GROUP BY 1
            ORDER BY count(*) DESC
            LIMIT 40
            """,
            [f"%{term}%"],
        )
        for row in cursor.fetchall():
            label = str(row["label"])
            existing = matches.get(label.casefold())
            if existing:
                existing["publication_count"] = int(row["publication_count"])
                continue
            canonical = canonical_institution(label)
            matches[label.casefold()] = {
                "label": label,
                "country_code": canonical["country_code"] or (SRI_LANKA if row["sri_lankan"] else None),
                "sri_lankan": bool(row["sri_lankan"]) or canonical["country_code"] == SRI_LANKA,
                "registered": canonical["registered"],
                "publication_count": int(row["publication_count"]),
            }

    ranked = sorted(
        matches.values(),
        key=lambda item: (
            not item["label"].casefold().startswith(term.casefold()),
            -int(item["publication_count"]),
            item["label"],
        ),
    )
    return ranked[:limit]


# -------------------------------------------------------------- categories


@lru_cache(maxsize=1)
def category_taxonomy() -> dict[str, list[str]]:
    try:
        with TAXONOMY_JSON.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError) as exc:
        logger.warning("Category taxonomy unavailable at %s: %s", TAXONOMY_JSON, exc)
        return {}
    return {str(field): [str(subfield) for subfield in subfields] for field, subfields in data.items()}


def field_domains(connection: Any) -> dict[str, str]:
    """Each field's domain as the dataset uses it (OpenAlex assigns one per field)."""

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (primary_field) primary_field, primary_domain
            FROM final_publications
            WHERE coalesce(primary_field, '') <> '' AND coalesce(primary_domain, '') <> ''
            GROUP BY primary_field, primary_domain
            ORDER BY primary_field, count(*) DESC
            """
        )
        return {str(row["primary_field"]): str(row["primary_domain"]) for row in cursor.fetchall()}


def category_options(connection: Any) -> dict[str, Any]:
    domains = field_domains(connection)
    taxonomy = category_taxonomy()
    return {
        "fields": [
            {"field": field, "domain": domains.get(field), "subfields": subfields}
            for field, subfields in sorted(taxonomy.items())
        ]
    }


def suggest_category(record: Mapping[str, Any]) -> dict[str, Any]:
    """Field and subfield from the hierarchical classifier, as a suggestion.

    The models are large, so they are loaded for the call and released after
    it rather than held by the API process; submissions are rare.
    """

    from src.modeling.hierarchical_linear_svm import (
        DEFAULT_TEXT_COLUMNS,
        default_field_model_output,
        default_subfield_model_output,
        load_hierarchical_models,
        predict_field_subfield,
    )

    field_path, subfield_path = default_field_model_output(), default_subfield_model_output()
    if not field_path.is_file() or not subfield_path.is_file():
        logger.warning("Category models not found at %s / %s", field_path, subfield_path)
        return {"field": None, "subfield": None, "available": False, "reason": "model_not_found"}
    try:
        import pandas as pd

        field_model, subfield_models = load_hierarchical_models(field_path, subfield_path)
        predicted = predict_field_subfield(
            pd.DataFrame([dict(record)]),
            field_model=field_model,
            subfield_models=subfield_models,
            text_columns=DEFAULT_TEXT_COLUMNS,
        ).iloc[0]
    except Exception as exc:  # noqa: BLE001 - a broken model is evidence, not a 500
        logger.warning("Category suggestion failed: %s", exc)
        return {"field": None, "subfield": None, "available": False, "reason": f"model_error:{type(exc).__name__}"}

    def clean(value: Any) -> str | None:
        text = None if value is None else str(value)
        return None if text in (None, "", "<NA>", "nan") else text

    return {
        "field": clean(predicted.get("predicted_field")),
        "subfield": clean(predicted.get("predicted_subfield")),
        "available": True,
        "reason": None,
    }


# ------------------------------------------------------------ author names


def lookup_author_names(connection: Any, query: str, *, limit: int = LOOKUP_LIMIT) -> dict[str, Any]:
    """Printed author names and verified profiles matching a typed fragment.

    Each name carries the profile that has claimed it, if any, so the person
    adding a paper can link an author to the right profile — and so one
    researcher's several spellings can be seen side by side.
    """

    term = " ".join(str(query or "").split())
    if len(term) < MIN_LOOKUP_LENGTH:
        return {"names": [], "profiles": []}
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT btrim(item.value) AS name,
                   count(*) AS publication_count,
                   min(COALESCE(p.publication_year, EXTRACT(YEAR FROM p.publication_date)::int)) AS year_min,
                   max(COALESCE(p.publication_year, EXTRACT(YEAR FROM p.publication_date)::int)) AS year_max
            FROM public_eligible_publications p,
                 regexp_split_to_table(coalesce(p.authors, ''), ';') AS item(value)
            WHERE btrim(item.value) ILIKE %s
            GROUP BY 1
            ORDER BY count(*) DESC, 1
            LIMIT %s
            """,
            [f"%{term}%", limit],
        )
        names = [dict(row) for row in cursor.fetchall()]
        claimed = claimed_name_profiles(cursor, [row["name"] for row in names])
        cursor.execute(
            """
            SELECT slug, display_name, institution, name_variants
            FROM author_profiles
            WHERE status = 'approved'
              AND (display_name ILIKE %s
                   OR EXISTS (SELECT 1 FROM unnest(name_variants) AS variant WHERE variant ILIKE %s))
            ORDER BY display_name
            LIMIT %s
            """,
            [f"%{term}%", f"%{term}%", limit],
        )
        profiles = [dict(row) for row in cursor.fetchall()]
    for row in names:
        row["profile"] = claimed.get(row["name"].casefold())
    return normalize_value({"names": names, "profiles": profiles})


# A printed spelling belongs to a verified profile when it is printed on one of
# that profile's approved publications and is either the listed name the claim
# was made on, or a name the author declared (display name or variant). Merged
# sources often print one person twice on a paper ("Roshan Ragel; Roshan G.
# Ragel"), so a claim made on one spelling also vouches for the declared others.
# Fuzzy matching is deliberately not used: a co-author "Ruwan Ragel" on the same
# paper must not be taken for "Roshan Ragel".
PROFILE_SPELLINGS_SQL = """
    SELECT c.profile_id, btrim(item.value) AS spelling, c.publication_key
    FROM author_publication_claims c
    JOIN author_profiles p ON p.profile_id = c.profile_id
    JOIN final_publications fp ON fp.publication_key = c.publication_key
    CROSS JOIN LATERAL regexp_split_to_table(coalesce(fp.authors, ''), ';') AS item(value)
    WHERE c.status = 'approved' AND p.status = 'approved'
      AND (
          lower(btrim(item.value)) = lower(c.name_as_listed)
          OR lower(btrim(item.value)) = lower(p.display_name)
          OR lower(btrim(item.value)) IN (SELECT lower(variant) FROM unnest(p.name_variants) AS variant)
      )
"""


def claimed_name_profiles(cursor: Any, names: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Printed name (case-folded) -> the verified profile that owns that spelling."""

    keys = sorted({str(name).casefold() for name in names if name})
    if not keys:
        return {}
    cursor.execute(
        f"""
        SELECT lower(s.spelling) AS name_key, p.slug, p.display_name, p.institution,
               count(DISTINCT s.publication_key) AS claimed_count
        FROM ({PROFILE_SPELLINGS_SQL}) AS s
        JOIN author_profiles p ON p.profile_id = s.profile_id
        WHERE lower(s.spelling) = ANY(%s::text[])
        GROUP BY 1, 2, 3, 4
        ORDER BY count(DISTINCT s.publication_key) DESC
        """,
        [keys],
    )
    result: dict[str, dict[str, Any]] = {}
    for row in cursor.fetchall():
        # A spelling shared by two verified people keeps the larger claim set;
        # the name page lists both through the public profile search.
        result.setdefault(
            row["name_key"],
            {
                "slug": row["slug"],
                "display_name": row["display_name"],
                "institution": row["institution"],
                "claimed_count": int(row["claimed_count"]),
            },
        )
    return result


# --------------------------------------------- institution at publication time


def affiliation_active(affiliation: Mapping[str, Any], year: int | None) -> bool:
    if year is None:
        return False
    start, end = affiliation.get("start_year"), affiliation.get("end_year")
    return (start is None or start <= year) and (end is None or year <= end)


def institution_at_time(
    paper_institutions: Iterable[str],
    year: int | None,
    affiliations: list[Mapping[str, Any]],
) -> str | None:
    """Which of a paper's institutions is the author's, judged by their history.

    Harvested records list every author's institutions together, so the
    author's own one is inferred: an institution from their history that was
    current in the publication year, else any institution from their history
    that the paper lists. Unknown is returned as None rather than guessed.
    """

    listed = {institution_key(name): name for name in paper_institutions if name}
    listed.update(
        {institution_key(canonical_institution(name)["label"]): name for name in list(listed.values())}
    )
    ordered = sorted(affiliations, key=lambda item: not affiliation_active(item, year))
    for affiliation in ordered:
        for key in (
            institution_key(affiliation.get("institution")),
            institution_key(canonical_institution(affiliation.get("institution"))["label"]),
        ):
            if key and key in listed:
                return listed[key]
    return None


def institution_breakdown(
    papers: list[Mapping[str, Any]],
    affiliations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Count an author's publications by the institution they were at for each."""

    groups: dict[str, dict[str, Any]] = {}
    unattributed = 0
    for paper in papers:
        year = paper.get("publication_year")
        institution = paper.get("author_institution") or institution_at_time(
            split_semicolon_value(paper.get("institutions")), year, affiliations
        )
        if not institution:
            unattributed += 1
            continue
        group = groups.setdefault(
            institution.casefold(),
            {"institution": institution, "publication_count": 0, "year_min": None, "year_max": None},
        )
        group["publication_count"] += 1
        if year is not None:
            group["year_min"] = year if group["year_min"] is None else min(group["year_min"], year)
            group["year_max"] = year if group["year_max"] is None else max(group["year_max"], year)
    ordered = sorted(groups.values(), key=lambda item: (-(item["year_max"] or 0), item["institution"]))
    return {"institutions": ordered, "unattributed": unattributed}
