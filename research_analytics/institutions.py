"""National institution registry and affiliation resolution."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_analytics.config import FrameworkConfig


@dataclass
class Institution:
    institution_id: str
    preferred_name: str
    country_code: str | None = None
    alternative_names: set[str] = field(default_factory=set)
    ror_id: str | None = None
    parent_institution_id: str | None = None


class NationalInstitutionRegistry:
    """Controlled national institution registry with alias lookup."""

    def __init__(self, institutions: dict[str, Institution]) -> None:
        self.institutions = institutions
        self.alias_index: dict[str, str] = {}
        for institution in institutions.values():
            self.alias_index[_normalize_name(institution.preferred_name)] = institution.institution_id
            for alias in institution.alternative_names:
                self.alias_index[_normalize_name(alias)] = institution.institution_id

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
                    ),
                )
                if alternative_name:
                    institution.alternative_names.add(alternative_name)
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

    def resolve_names(self, names: Any) -> tuple[list[Institution], list[str]]:
        resolved: list[Institution] = []
        unresolved: list[str] = []
        for name in _as_list(names):
            institution_id = self.alias_index.get(_normalize_name(name))
            if institution_id:
                institution = self.institutions[institution_id]
                if institution not in resolved:
                    resolved.append(institution)
            elif name:
                unresolved.append(name)
        return resolved, unresolved


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
        enriched["unresolved_institutions"] = _as_list(record.get("institutions"))
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


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _has_country(record: dict[str, Any], country_code: str | None) -> bool:
    if not country_code:
        return False
    return country_code in set(_as_list(record.get("countries")))


def _has_international_country(record: dict[str, Any], national_country_code: str | None) -> bool:
    countries = set(_as_list(record.get("countries")))
    if not countries or not national_country_code:
        return False
    return any(country != national_country_code for country in countries)
