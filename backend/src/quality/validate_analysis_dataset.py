"""Validate the author, institution, citation and collaboration fields.

Four independent validators over the analysis dataset. Each one answers a
different question, and each one reports the same three things: counted metrics,
quality gates with an explicit threshold, and a capped sample of the offending
records so a number can always be traced back to rows.

    authors        Are author names parseable, counted correctly, and are the
                   ORCIDs real and attached to the right number of people?
    institutions   Do the institution identifiers exist in the registry, do the
                   country codes exist at all, and did anything resolve?
    citations      Are the counts numbers, non-negative, and plausible for the
                   publication year?
    collaboration  Do the derived collaboration fields agree with the
                   institutions and countries they were derived from?
    ownership      Does the verified final dataset contain only Sri Lanka-led
                   INCLUDE records with non-low confidence and review rows removed?

Nothing here changes data. A validator that finds a problem reports it; fixing
it belongs to the pipeline stage that produced the column.

    python -m src.quality.validate_analysis_dataset
    python -m src.quality.validate_analysis_dataset --checks citations,collaboration
    python -m src.quality.validate_analysis_dataset --strict   # exit 1 on a failed gate
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_analytics.authors import (  # noqa: E402
    normalize_orcid,
    parse_author_name,
    split_author_field,
)
from research_analytics.institutions import (  # noqa: E402
    NationalInstitutionRegistry,
    collaboration_scope,
    split_multi_value,
    standardize_country,
)


COMMON_DIR = PROJECT_ROOT / "data" / "processed" / "common"

# Tried in order; the first that exists is used. The later stages add the
# columns the institution and collaboration validators need, so validating the
# most-normalized dataset available gives the most complete answer.
INPUT_CANDIDATES = (
    COMMON_DIR / "common_publications_final_author_disambiguated.csv",
    COMMON_DIR / "common_publications_final_institution_normalized.csv",
    COMMON_DIR / "common_publications_final.csv",
)

DEFAULT_REGISTRY_CSV = PROJECT_ROOT / "configurations" / "sri_lanka" / "institutions.csv"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "validation"
DEFAULT_CHUNK_SIZE = 25_000
DEFAULT_MAX_ISSUES = 5_000

CURRENT_YEAR = datetime.now(timezone.utc).year
PLAUSIBLE_YEAR_RANGE = (1900, CURRENT_YEAR + 1)

# A single work with more than this many citations is a parsing error, not a
# record: the most-cited paper ever sits below it by an order of magnitude.
MAX_PLAUSIBLE_CITATIONS = 500_000
MAX_PLAUSIBLE_REFERENCES = 10_000
MAX_PLAUSIBLE_AUTHORS = 5_000
MAX_AUTHOR_NAME_LENGTH = 120

# Placeholder strings that occupy an author position without naming anyone.
PLACEHOLDER_AUTHOR_NAMES = frozenset(
    {
        "anonymous",
        "anon",
        "unknown",
        "n a",
        "na",
        "none",
        "et al",
        "et al.",
        "no author",
        "author",
        "authors",
        "staff",
        "editor",
        "editors",
        "various",
    }
)

INSTITUTION_SOURCE_VALUES = frozenset(
    {"metadata", "source_institution_id", "author_affiliations", "none"}
)
COLLABORATION_TYPES = frozenset(
    {
        "domestic_single_institution",
        "domestic_multi_institution",
        "international_collaboration",
        "unresolved_affiliation",
        "not_national",
    }
)
COLLABORATION_SCOPES = frozenset({"local", "international", "unknown"})
NATIONAL_COUNTRY_CODE = "LK"
OWNERSHIP_DECISIONS = frozenset({"INCLUDE", "REVIEW", "EXCLUDE"})
VERIFIED_CONFIDENCES = frozenset({"HIGH", "MEDIUM"})

ISSUE_FIELDNAMES = ["record_id", "column", "issue", "value", "detail"]
SUMMARY_FIELDNAMES = ["metric", "value"]
GATE_FIELDNAMES = ["gate", "value", "threshold", "comparison", "status"]


@dataclass(frozen=True)
class ValidationIssue:
    record_id: str
    column: str
    issue: str
    value: str
    detail: str = ""

    def as_row(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "column": self.column,
            "issue": self.issue,
            "value": self.value[:200],
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Gate:
    """A threshold the dataset is expected to meet."""

    name: str
    value: float
    threshold: float
    comparison: str = ">="
    skipped: bool = False
    note: str = ""

    @property
    def passed(self) -> bool:
        if self.skipped:
            return True
        if self.comparison == ">=":
            return self.value >= self.threshold
        if self.comparison == "<=":
            return self.value <= self.threshold
        if self.comparison == "==":
            return self.value == self.threshold
        raise ValueError(f"unknown comparison: {self.comparison}")

    @property
    def status(self) -> str:
        if self.skipped:
            return f"skipped: {self.note}" if self.note else "skipped"
        return "pass" if self.passed else "FAIL"

    def as_row(self) -> dict[str, Any]:
        return {
            "gate": self.name,
            "value": round(self.value, 4),
            "threshold": self.threshold,
            "comparison": self.comparison,
            "status": self.status,
        }


@dataclass
class FieldValidationReport:
    name: str
    rows: int
    metrics: list[tuple[str, Any]] = field(default_factory=list)
    gates: list[Gate] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues_truncated: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def failed_gates(self) -> list[Gate]:
        return [gate for gate in self.gates if not gate.passed]

    def summary_rows(self) -> list[dict[str, Any]]:
        rows = [{"metric": "check", "value": self.name}, {"metric": "rows", "value": self.rows}]
        rows.extend({"metric": name, "value": value} for name, value in self.metrics)
        rows.extend(
            {"metric": f"issue:{issue}", "value": count}
            for issue, count in sorted(self.issue_counts.items())
        )
        rows.extend(
            {"metric": f"gate:{gate.name}", "value": gate.status} for gate in self.gates
        )
        rows.append({"metric": "issues_recorded", "value": len(self.issues)})
        rows.append({"metric": "issues_truncated", "value": self.issues_truncated})
        rows.append({"metric": "passed", "value": self.passed})
        return rows


class FieldValidator:
    """Accumulates one field group's counters over a record stream."""

    name = "field"

    def __init__(self, *, max_issues: int = DEFAULT_MAX_ISSUES) -> None:
        self.rows = 0
        self.max_issues = max_issues
        self.issues: list[ValidationIssue] = []
        self.issue_counts: Counter[str] = Counter()
        self.issues_truncated = False
        self.columns_seen: set[str] = set()

    def add_issue(
        self, record_id: str, column: str, issue: str, value: Any, detail: str = ""
    ) -> None:
        self.issue_counts[issue] += 1
        if len(self.issues) >= self.max_issues:
            self.issues_truncated = True
            return
        self.issues.append(
            ValidationIssue(
                record_id=record_id,
                column=column,
                issue=issue,
                value="" if value is None else str(value),
                detail=detail,
            )
        )

    def add_row(self, row: Mapping[str, Any], *, record_id: str) -> None:
        raise NotImplementedError

    def report(self) -> FieldValidationReport:
        raise NotImplementedError

    def _base_report(self, metrics: list[tuple[str, Any]], gates: list[Gate]) -> FieldValidationReport:
        return FieldValidationReport(
            name=self.name,
            rows=self.rows,
            metrics=metrics,
            gates=gates,
            issues=self.issues,
            issue_counts=self.issue_counts,
            issues_truncated=self.issues_truncated,
        )

    def has_column(self, row: Mapping[str, Any], column: str) -> bool:
        present = column in row
        if present:
            self.columns_seen.add(column)
        return present


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null"}:
        return None
    return text


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _parse_int(value: Any) -> tuple[int | None, str | None]:
    """Parse a count, reporting how it failed rather than just returning None."""

    text = _clean(value)
    if text is None:
        return None, "missing"
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None, "not_numeric"
    if number != int(number):
        return None, "not_an_integer"
    return int(number), None


# --- authors ----------------------------------------------------------------

AUTHOR_PRESENCE_THRESHOLD = 0.90
AUTHOR_NAME_PARSE_THRESHOLD = 0.98
AUTHOR_COUNT_AGREEMENT_THRESHOLD = 0.95
ORCID_VALIDITY_THRESHOLD = 0.95


class AuthorValidator(FieldValidator):
    """Author names, author counts and ORCIDs."""

    name = "authors"

    def __init__(self, *, max_issues: int = DEFAULT_MAX_ISSUES) -> None:
        super().__init__(max_issues=max_issues)
        self.rows_with_authors = 0
        self.author_mentions = 0
        self.unparsed_names = 0
        self.placeholder_names = 0
        self.overlong_names = 0
        self.rows_with_duplicate_names = 0
        self.rows_with_author_count = 0
        self.author_count_agrees = 0
        self.orcid_values = 0
        self.orcid_invalid = 0
        self.rows_with_orcids = 0
        self.rows_with_aligned_orcids = 0
        self.rows_with_duplicate_orcids = 0
        self.rows_with_author_ids = 0
        self.rows_with_author_id_mismatch = 0

    def add_row(self, row: Mapping[str, Any], *, record_id: str) -> None:
        self.rows += 1
        self.has_column(row, "authors")

        raw_names = split_author_field(row.get("authors"))
        if not raw_names:
            self.add_issue(record_id, "authors", "missing_authors", "")
            return

        self.rows_with_authors += 1
        self.author_mentions += len(raw_names)
        if len(raw_names) > MAX_PLAUSIBLE_AUTHORS:
            self.add_issue(
                record_id, "authors", "implausible_author_count", len(raw_names),
                f"more than {MAX_PLAUSIBLE_AUTHORS} names in one record",
            )

        parsed_keys: list[str] = []
        for raw in raw_names:
            name = parse_author_name(raw)
            if name is None:
                self.unparsed_names += 1
                self.add_issue(record_id, "authors", "unparseable_author_name", raw)
                continue
            parsed_keys.append(name.variant_key)

            stripped = raw.strip().strip(".,;").casefold()
            if stripped in PLACEHOLDER_AUTHOR_NAMES:
                self.placeholder_names += 1
                self.add_issue(record_id, "authors", "placeholder_author_name", raw)
            if len(raw) > MAX_AUTHOR_NAME_LENGTH:
                self.overlong_names += 1
                self.add_issue(
                    record_id, "authors", "overlong_author_name", raw[:80],
                    f"{len(raw)} characters -- probably an unsplit author list",
                )

        duplicates = [key for key, count in Counter(parsed_keys).items() if count > 1]
        if duplicates:
            self.rows_with_duplicate_names += 1
            self.add_issue(
                record_id, "authors", "duplicate_author_in_record", "; ".join(duplicates[:5])
            )

        self._check_author_count(row, record_id, len(raw_names))
        self._check_orcids(row, record_id, len(raw_names))
        self._check_author_ids(row, record_id, len(parsed_keys))

    def _check_author_count(
        self, row: Mapping[str, Any], record_id: str, name_count: int
    ) -> None:
        if not self.has_column(row, "author_count"):
            return
        declared, failure = _parse_int(row.get("author_count"))
        if failure == "missing":
            return
        self.rows_with_author_count += 1
        if declared is None:
            self.add_issue(
                record_id, "author_count", f"author_count_{failure}", row.get("author_count")
            )
            return
        if declared == name_count:
            self.author_count_agrees += 1
        else:
            self.add_issue(
                record_id, "author_count", "author_count_mismatch", declared,
                f"{name_count} names present",
            )

    def _check_orcids(self, row: Mapping[str, Any], record_id: str, name_count: int) -> None:
        if not self.has_column(row, "author_orcids"):
            return
        raw_orcids = split_author_field(row.get("author_orcids"))
        if not raw_orcids:
            return

        self.rows_with_orcids += 1
        self.orcid_values += len(raw_orcids)
        normalized: list[str] = []
        for raw in raw_orcids:
            orcid = normalize_orcid(raw)
            if orcid is None:
                self.orcid_invalid += 1
                self.add_issue(
                    record_id, "author_orcids", "invalid_orcid", raw,
                    "fails the ISO 7064 MOD 11-2 check digit",
                )
            else:
                normalized.append(orcid)

        if len(set(normalized)) != len(normalized):
            self.rows_with_duplicate_orcids += 1
            self.add_issue(
                record_id, "author_orcids", "duplicate_orcid_in_record", "; ".join(normalized[:5])
            )
        if len(raw_orcids) == name_count:
            self.rows_with_aligned_orcids += 1
        else:
            # Not an error: sources compact the ORCID list. It does mean the
            # identifiers cannot be tied to author positions.
            self.add_issue(
                record_id, "author_orcids", "orcid_count_not_aligned_with_authors",
                len(raw_orcids), f"{name_count} authors",
            )

    def _check_author_ids(
        self, row: Mapping[str, Any], record_id: str, parsed_count: int
    ) -> None:
        if not self.has_column(row, "author_ids"):
            return
        author_ids = split_multi_value(row.get("author_ids"))
        if not author_ids:
            return
        self.rows_with_author_ids += 1
        if len(author_ids) != parsed_count:
            self.rows_with_author_id_mismatch += 1
            self.add_issue(
                record_id, "author_ids", "author_id_count_mismatch", len(author_ids),
                f"{parsed_count} parseable names",
            )

    def report(self) -> FieldValidationReport:
        parsed = self.author_mentions - self.unparsed_names
        metrics: list[tuple[str, Any]] = [
            ("rows_with_authors", self.rows_with_authors),
            ("author_presence_rate", round(_rate(self.rows_with_authors, self.rows), 4)),
            ("author_mentions", self.author_mentions),
            ("unparsed_author_names", self.unparsed_names),
            ("author_name_parse_rate", round(_rate(parsed, self.author_mentions), 4)),
            ("placeholder_author_names", self.placeholder_names),
            ("overlong_author_names", self.overlong_names),
            ("rows_with_duplicate_author_names", self.rows_with_duplicate_names),
            ("rows_with_author_count", self.rows_with_author_count),
            (
                "author_count_agreement_rate",
                round(_rate(self.author_count_agrees, self.rows_with_author_count), 4),
            ),
            ("rows_with_orcids", self.rows_with_orcids),
            ("orcid_values", self.orcid_values),
            ("invalid_orcids", self.orcid_invalid),
            (
                "orcid_validity_rate",
                round(_rate(self.orcid_values - self.orcid_invalid, self.orcid_values), 4),
            ),
            ("rows_with_position_aligned_orcids", self.rows_with_aligned_orcids),
            ("rows_with_duplicate_orcids", self.rows_with_duplicate_orcids),
            ("rows_with_author_ids", self.rows_with_author_ids),
            ("rows_with_author_id_count_mismatch", self.rows_with_author_id_mismatch),
        ]
        gates = [
            Gate(
                "author_presence_rate",
                _rate(self.rows_with_authors, self.rows),
                AUTHOR_PRESENCE_THRESHOLD,
            ),
            Gate(
                "author_name_parse_rate",
                _rate(parsed, self.author_mentions),
                AUTHOR_NAME_PARSE_THRESHOLD,
            ),
            Gate(
                "author_count_agreement_rate",
                _rate(self.author_count_agrees, self.rows_with_author_count),
                AUTHOR_COUNT_AGREEMENT_THRESHOLD,
                skipped=self.rows_with_author_count == 0,
                note="no author_count values",
            ),
            Gate(
                "orcid_validity_rate",
                _rate(self.orcid_values - self.orcid_invalid, self.orcid_values),
                ORCID_VALIDITY_THRESHOLD,
                skipped=self.orcid_values == 0,
                note="no ORCIDs present",
            ),
        ]
        return self._base_report(metrics, gates)


# --- institutions -----------------------------------------------------------

INSTITUTION_COVERAGE_THRESHOLD = 0.85
COUNTRY_VALIDITY_THRESHOLD = 0.99


class InstitutionValidator(FieldValidator):
    """Institution names, registry identifiers and country codes."""

    name = "institutions"

    def __init__(
        self,
        *,
        registry: NationalInstitutionRegistry | None = None,
        max_issues: int = DEFAULT_MAX_ISSUES,
    ) -> None:
        super().__init__(max_issues=max_issues)
        self.registry = registry
        self.rows_with_institutions = 0
        self.institution_mentions = 0
        self.institution_mentions_resolved = 0
        self.national_id_values = 0
        self.unknown_national_ids = 0
        self.country_values = 0
        self.invalid_country_codes = 0
        self.rows_missing_national_country = 0
        self.invalid_institution_source = 0
        self.rows_affiliation_without_institution = 0
        self.unknown_id_examples: Counter[str] = Counter()

    def add_row(self, row: Mapping[str, Any], *, record_id: str) -> None:
        self.rows += 1
        self.has_column(row, "institutions")

        institutions = split_multi_value(row.get("institutions"))
        if institutions:
            self.rows_with_institutions += 1
        else:
            self.add_issue(record_id, "institutions", "missing_institutions", "")
            if self.has_column(row, "author_affiliations") and _clean(
                row.get("author_affiliations")
            ):
                self.rows_affiliation_without_institution += 1
                self.add_issue(
                    record_id, "institutions", "affiliation_present_without_institution",
                    str(row.get("author_affiliations"))[:120],
                )

        self.institution_mentions += len(institutions)
        if self.registry is not None:
            for name in institutions:
                if self.registry.resolve_name(name) is not None:
                    self.institution_mentions_resolved += 1

        self._check_national_ids(row, record_id)
        self._check_countries(row, record_id)

        if self.has_column(row, "institution_source"):
            source = _clean(row.get("institution_source"))
            if source is not None and source not in INSTITUTION_SOURCE_VALUES:
                self.invalid_institution_source += 1
                self.add_issue(
                    record_id, "institution_source", "unknown_institution_source", source,
                    f"expected one of {sorted(INSTITUTION_SOURCE_VALUES)}",
                )

    def _check_national_ids(self, row: Mapping[str, Any], record_id: str) -> None:
        if not self.has_column(row, "national_institution_ids"):
            return
        identifiers = split_multi_value(row.get("national_institution_ids"))
        self.national_id_values += len(identifiers)
        if self.registry is None:
            return
        for identifier in identifiers:
            if identifier not in self.registry.institutions:
                self.unknown_national_ids += 1
                self.unknown_id_examples[identifier] += 1
                self.add_issue(
                    record_id, "national_institution_ids", "unknown_registry_identifier",
                    identifier, "not present in the institution registry",
                )

    def _check_countries(self, row: Mapping[str, Any], record_id: str) -> None:
        if not self.has_column(row, "countries"):
            return
        countries = split_multi_value(row.get("countries"))
        self.country_values += len(countries)
        for country in countries:
            if standardize_country(country) is None:
                self.invalid_country_codes += 1
                self.add_issue(
                    record_id, "countries", "unrecognised_country", country,
                    "not an ISO 3166-1 alpha-2 code or a known country name",
                )

        national_ids = split_multi_value(row.get("national_institution_ids"))
        if national_ids and NATIONAL_COUNTRY_CODE not in countries:
            self.rows_missing_national_country += 1
            self.add_issue(
                record_id, "countries", "national_institution_without_national_country",
                "; ".join(countries) or "(none)",
                f"record resolves to {'; '.join(national_ids)}",
            )

    def report(self) -> FieldValidationReport:
        registry_available = self.registry is not None
        metrics: list[tuple[str, Any]] = [
            ("registry_loaded", registry_available),
            ("rows_with_institutions", self.rows_with_institutions),
            (
                "institution_coverage",
                round(_rate(self.rows_with_institutions, self.rows), 4),
            ),
            ("institution_mentions", self.institution_mentions),
            ("institution_mentions_resolved", self.institution_mentions_resolved),
            (
                "institution_resolution_rate",
                round(
                    _rate(self.institution_mentions_resolved, self.institution_mentions), 4
                ),
            ),
            ("national_institution_id_values", self.national_id_values),
            ("unknown_registry_identifiers", self.unknown_national_ids),
            ("distinct_unknown_registry_identifiers", len(self.unknown_id_examples)),
            ("country_values", self.country_values),
            ("unrecognised_country_values", self.invalid_country_codes),
            (
                "country_validity_rate",
                round(
                    _rate(self.country_values - self.invalid_country_codes, self.country_values),
                    4,
                ),
            ),
            ("rows_missing_national_country_code", self.rows_missing_national_country),
            ("unknown_institution_source_values", self.invalid_institution_source),
            (
                "rows_with_affiliation_but_no_institution",
                self.rows_affiliation_without_institution,
            ),
        ]
        gates = [
            Gate(
                "institution_coverage",
                _rate(self.rows_with_institutions, self.rows),
                INSTITUTION_COVERAGE_THRESHOLD,
            ),
            Gate(
                "unknown_registry_identifiers",
                self.unknown_national_ids,
                0,
                comparison="==",
                skipped=not registry_available,
                note="registry not loaded",
            ),
            Gate(
                "country_validity_rate",
                _rate(self.country_values - self.invalid_country_codes, self.country_values),
                COUNTRY_VALIDITY_THRESHOLD,
                skipped=self.country_values == 0,
                note="no country values",
            ),
            Gate(
                "unknown_institution_source_values",
                self.invalid_institution_source,
                0,
                comparison="==",
            ),
        ]
        return self._base_report(metrics, gates)


# --- citations --------------------------------------------------------------

CITATION_NUMERIC_VALIDITY_THRESHOLD = 1.0


class CitationValidator(FieldValidator):
    """Citation and reference counts, and their plausibility for the year."""

    name = "citations"

    def __init__(self, *, max_issues: int = DEFAULT_MAX_ISSUES) -> None:
        super().__init__(max_issues=max_issues)
        self.citation_present = 0
        self.citation_missing = 0
        self.citation_invalid = 0
        self.citation_negative = 0
        self.citation_implausible = 0
        self.citation_zero = 0
        self.citation_total = 0
        self.citation_max = 0
        self.reference_present = 0
        self.reference_invalid = 0
        self.reference_negative = 0
        self.reference_implausible = 0
        self.future_year_with_citations = 0
        self.invalid_years = 0

    def add_row(self, row: Mapping[str, Any], *, record_id: str) -> None:
        self.rows += 1
        year = self._check_year(row, record_id)
        citations = self._check_count(
            row,
            record_id,
            column="citation_count",
            maximum=MAX_PLAUSIBLE_CITATIONS,
        )

        if citations is None:
            self.citation_missing += 1
        else:
            self.citation_present += 1
            self.citation_total += max(citations, 0)
            self.citation_max = max(self.citation_max, citations)
            if citations == 0:
                self.citation_zero += 1
            # A work published after this year cannot have accumulated
            # citations; either the year or the count came from the wrong field.
            if citations > 0 and year is not None and year > CURRENT_YEAR:
                self.future_year_with_citations += 1
                self.add_issue(
                    record_id, "citation_count", "citations_on_future_publication",
                    citations, f"publication_year={year}",
                )

        references = self._check_count(
            row,
            record_id,
            column="reference_count",
            maximum=MAX_PLAUSIBLE_REFERENCES,
        )
        if references is not None:
            self.reference_present += 1

    def _check_year(self, row: Mapping[str, Any], record_id: str) -> int | None:
        if not self.has_column(row, "publication_year"):
            return None
        year, failure = _parse_int(row.get("publication_year"))
        if failure == "missing":
            return None
        if year is None or not (PLAUSIBLE_YEAR_RANGE[0] <= year <= PLAUSIBLE_YEAR_RANGE[1]):
            self.invalid_years += 1
            self.add_issue(
                record_id, "publication_year", "implausible_publication_year",
                row.get("publication_year"),
                f"outside {PLAUSIBLE_YEAR_RANGE[0]}-{PLAUSIBLE_YEAR_RANGE[1]}",
            )
            return None
        return year

    def _check_count(
        self, row: Mapping[str, Any], record_id: str, *, column: str, maximum: int
    ) -> int | None:
        if not self.has_column(row, column):
            return None
        value, failure = _parse_int(row.get(column))
        is_citation = column == "citation_count"

        if failure == "missing":
            return None
        if value is None:
            if is_citation:
                self.citation_invalid += 1
            else:
                self.reference_invalid += 1
            self.add_issue(record_id, column, f"{column}_{failure}", row.get(column))
            return None

        if value < 0:
            if is_citation:
                self.citation_negative += 1
            else:
                self.reference_negative += 1
            self.add_issue(record_id, column, f"negative_{column}", value)
        elif value > maximum:
            if is_citation:
                self.citation_implausible += 1
            else:
                self.reference_implausible += 1
            self.add_issue(
                record_id, column, f"implausible_{column}", value, f"above {maximum:,}"
            )
        return value

    def report(self) -> FieldValidationReport:
        citation_values = self.citation_present + self.citation_invalid
        valid_rate = _rate(self.citation_present, citation_values)
        metrics: list[tuple[str, Any]] = [
            ("rows_with_citation_count", self.citation_present),
            ("rows_missing_citation_count", self.citation_missing),
            (
                "citation_coverage",
                round(_rate(self.citation_present, self.rows), 4),
            ),
            ("non_numeric_citation_counts", self.citation_invalid),
            ("citation_numeric_validity_rate", round(valid_rate, 4)),
            ("negative_citation_counts", self.citation_negative),
            ("implausible_citation_counts", self.citation_implausible),
            ("zero_citation_rows", self.citation_zero),
            ("citations_on_future_publications", self.future_year_with_citations),
            ("max_citation_count", self.citation_max),
            ("total_citations", self.citation_total),
            (
                "mean_citations_per_cited_row",
                round(_rate(self.citation_total, self.citation_present), 4),
            ),
            ("rows_with_reference_count", self.reference_present),
            ("non_numeric_reference_counts", self.reference_invalid),
            ("negative_reference_counts", self.reference_negative),
            ("implausible_reference_counts", self.reference_implausible),
            ("implausible_publication_years", self.invalid_years),
        ]
        gates = [
            Gate(
                "citation_numeric_validity_rate",
                valid_rate,
                CITATION_NUMERIC_VALIDITY_THRESHOLD,
                skipped=citation_values == 0,
                note="no citation counts present",
            ),
            Gate("negative_citation_counts", self.citation_negative, 0, comparison="=="),
            Gate("implausible_citation_counts", self.citation_implausible, 0, comparison="=="),
            Gate("negative_reference_counts", self.reference_negative, 0, comparison="=="),
        ]
        return self._base_report(metrics, gates)


# --- collaboration ----------------------------------------------------------

COLLABORATION_PRESENCE_THRESHOLD = 0.99


class CollaborationValidator(FieldValidator):
    """Collaboration type and scope against the fields they derive from."""

    name = "collaboration"

    def __init__(self, *, max_issues: int = DEFAULT_MAX_ISSUES) -> None:
        super().__init__(max_issues=max_issues)
        self.rows_with_type = 0
        self.unknown_types = 0
        self.unknown_scopes = 0
        self.scope_mismatches = 0
        self.international_without_foreign_country = 0
        self.multi_without_two_institutions = 0
        self.single_with_many_institutions = 0
        self.unresolved_without_evidence = 0
        self.not_national_with_ids = 0
        self.type_counts: Counter[str] = Counter()
        self.scope_counts: Counter[str] = Counter()

    def add_row(self, row: Mapping[str, Any], *, record_id: str) -> None:
        self.rows += 1
        if not self.has_column(row, "collaboration_type"):
            return

        collaboration_type = _clean(row.get("collaboration_type"))
        if collaboration_type is None:
            self.add_issue(record_id, "collaboration_type", "missing_collaboration_type", "")
            return

        self.rows_with_type += 1
        self.type_counts[collaboration_type] += 1
        if collaboration_type not in COLLABORATION_TYPES:
            self.unknown_types += 1
            self.add_issue(
                record_id, "collaboration_type", "unknown_collaboration_type",
                collaboration_type, f"expected one of {sorted(COLLABORATION_TYPES)}",
            )
            return

        national_ids = set(split_multi_value(row.get("national_institution_ids")))
        countries = set(split_multi_value(row.get("countries")))
        unresolved = split_multi_value(row.get("unresolved_institutions"))

        self._check_scope(row, record_id, collaboration_type)
        self._check_consistency(
            record_id,
            collaboration_type,
            national_ids=national_ids,
            countries=countries,
            unresolved=unresolved,
        )

    def _check_scope(
        self, row: Mapping[str, Any], record_id: str, collaboration_type: str
    ) -> None:
        if not self.has_column(row, "collaboration_scope"):
            return
        scope = _clean(row.get("collaboration_scope"))
        if scope is None:
            self.add_issue(record_id, "collaboration_scope", "missing_collaboration_scope", "")
            return

        self.scope_counts[scope] += 1
        if scope not in COLLABORATION_SCOPES:
            self.unknown_scopes += 1
            self.add_issue(
                record_id, "collaboration_scope", "unknown_collaboration_scope", scope,
                f"expected one of {sorted(COLLABORATION_SCOPES)}",
            )
            return

        # Scope is derived from type, so recomputing it must reproduce it.
        expected = collaboration_scope(collaboration_type)
        if scope != expected:
            self.scope_mismatches += 1
            self.add_issue(
                record_id, "collaboration_scope", "scope_does_not_match_type", scope,
                f"{collaboration_type} implies {expected}",
            )

    def _check_consistency(
        self,
        record_id: str,
        collaboration_type: str,
        *,
        national_ids: set[str],
        countries: set[str],
        unresolved: Sequence[str],
    ) -> None:
        foreign = {code for code in countries if code != NATIONAL_COUNTRY_CODE}

        if collaboration_type == "international_collaboration" and not foreign:
            self.international_without_foreign_country += 1
            self.add_issue(
                record_id, "collaboration_type", "international_without_foreign_country",
                collaboration_type, f"countries={'; '.join(sorted(countries)) or '(none)'}",
            )
        elif collaboration_type == "domestic_multi_institution" and len(national_ids) < 2:
            self.multi_without_two_institutions += 1
            self.add_issue(
                record_id, "collaboration_type", "multi_institution_without_two_institutions",
                collaboration_type, f"national_institution_ids={len(national_ids)}",
            )
        elif collaboration_type == "domestic_single_institution" and len(national_ids) != 1:
            self.single_with_many_institutions += 1
            self.add_issue(
                record_id, "collaboration_type", "single_institution_count_mismatch",
                collaboration_type, f"national_institution_ids={len(national_ids)}",
            )
        elif collaboration_type == "unresolved_affiliation" and not unresolved:
            self.unresolved_without_evidence += 1
            self.add_issue(
                record_id, "collaboration_type", "unresolved_without_unresolved_institutions",
                collaboration_type, "unresolved_institutions is empty",
            )
        elif collaboration_type == "not_national" and national_ids:
            self.not_national_with_ids += 1
            self.add_issue(
                record_id, "collaboration_type", "not_national_with_national_institutions",
                collaboration_type, f"national_institution_ids={len(national_ids)}",
            )

    def report(self) -> FieldValidationReport:
        inconsistencies = (
            self.international_without_foreign_country
            + self.multi_without_two_institutions
            + self.single_with_many_institutions
            + self.unresolved_without_evidence
            + self.not_national_with_ids
        )
        metrics: list[tuple[str, Any]] = [
            ("rows_with_collaboration_type", self.rows_with_type),
            (
                "collaboration_presence_rate",
                round(_rate(self.rows_with_type, self.rows), 4),
            ),
            ("unknown_collaboration_types", self.unknown_types),
            ("unknown_collaboration_scopes", self.unknown_scopes),
            ("scope_type_mismatches", self.scope_mismatches),
            (
                "international_without_foreign_country",
                self.international_without_foreign_country,
            ),
            ("multi_institution_without_two_institutions", self.multi_without_two_institutions),
            ("single_institution_count_mismatches", self.single_with_many_institutions),
            ("unresolved_without_evidence", self.unresolved_without_evidence),
            ("not_national_with_national_institutions", self.not_national_with_ids),
            ("total_inconsistencies", inconsistencies),
        ]
        metrics.extend(
            (f"collaboration_type:{name}", count)
            for name, count in sorted(self.type_counts.items())
        )
        metrics.extend(
            (f"collaboration_scope:{name}", count)
            for name, count in sorted(self.scope_counts.items())
        )
        gates = [
            Gate(
                "collaboration_presence_rate",
                _rate(self.rows_with_type, self.rows),
                COLLABORATION_PRESENCE_THRESHOLD,
                skipped="collaboration_type" not in self.columns_seen,
                note="collaboration_type column not present",
            ),
            Gate("unknown_collaboration_types", self.unknown_types, 0, comparison="=="),
            Gate("scope_type_mismatches", self.scope_mismatches, 0, comparison="=="),
            # These are derived fields, so a disagreement with their own inputs
            # is a pipeline defect rather than a data-quality observation.
            Gate("collaboration_inconsistencies", inconsistencies, 0, comparison="=="),
        ]
        return self._base_report(metrics, gates)


# --- ownership --------------------------------------------------------------


class OwnershipValidator(FieldValidator):
    """Verified-final ownership gate."""

    name = "ownership"

    def __init__(self, *, max_issues: int = DEFAULT_MAX_ISSUES) -> None:
        super().__init__(max_issues=max_issues)
        self.total_candidates = 0
        self.verified_included = 0
        self.manual_review = 0
        self.excluded = 0
        self.verified_non_include_rows = 0
        self.verified_manual_review_rows = 0
        self.verified_low_confidence_rows = 0
        self.verified_missing_decision_reason_rows = 0
        self.verified_foreign_led_rows = 0
        self.unknown_ownership_in_verified_dataset = 0
        self.missing_leadership_evidence = 0
        self.first_author_only = 0
        self.source_only_evidence = 0
        self.conflicting_evidence = 0
        self.source_counts: Counter[str] = Counter()
        self.reason_counts: Counter[str] = Counter()

    def add_row(self, row: Mapping[str, Any], *, record_id: str) -> None:
        self.rows += 1
        self.total_candidates += 1
        source = _clean(row.get("source_dataset")) or "unknown"
        self.source_counts[source] += 1

        decision = (_clean(row.get("ownership_decision")) or "").upper()
        confidence = (_clean(row.get("ownership_confidence")) or "").upper()
        ownership_class = (_clean(row.get("ownership_class")) or "").upper()
        reason = _clean(row.get("ownership_reason"))
        needs_review = str(row.get("needs_manual_review", "")).strip().casefold()
        lead_country = set(split_multi_value(row.get("lead_country")))

        if reason:
            self.reason_counts[reason] += 1
        if "MISSING_LEADERSHIP" in ownership_class:
            self.missing_leadership_evidence += 1
        if "FIRST_AUTHOR_ONLY" in ownership_class:
            self.first_author_only += 1
        if "SOURCE_ONLY" in str(row.get("ownership_evidence", "")).upper() or "ONLY_EVIDENCE" in ownership_class:
            self.source_only_evidence += 1
        if "CONFLICT" in ownership_class:
            self.conflicting_evidence += 1

        if decision == "INCLUDE" and confidence in VERIFIED_CONFIDENCES and needs_review not in {"true", "1", "yes", "y"}:
            self.verified_included += 1
        elif decision == "REVIEW":
            self.manual_review += 1
        elif decision == "EXCLUDE":
            self.excluded += 1

        if decision not in OWNERSHIP_DECISIONS:
            self.unknown_ownership_in_verified_dataset += 1
            self.add_issue(record_id, "ownership_decision", "unknown_ownership_in_verified_dataset", decision)
            return
        if decision != "INCLUDE":
            self.verified_non_include_rows += 1
            self.add_issue(record_id, "ownership_decision", "verified_non_include_rows", decision)
        if needs_review in {"true", "1", "yes", "y"}:
            self.verified_manual_review_rows += 1
            self.add_issue(record_id, "needs_manual_review", "verified_manual_review_rows", needs_review)
        if confidence not in VERIFIED_CONFIDENCES:
            self.verified_low_confidence_rows += 1
            self.add_issue(record_id, "ownership_confidence", "verified_low_confidence_rows", confidence)
        if reason is None:
            self.verified_missing_decision_reason_rows += 1
            self.add_issue(record_id, "ownership_reason", "verified_missing_decision_reason_rows", "")
        if decision == "INCLUDE" and lead_country and NATIONAL_COUNTRY_CODE not in lead_country:
            self.verified_foreign_led_rows += 1
            self.add_issue(record_id, "lead_country", "verified_foreign_led_rows", row.get("lead_country"))

    def report(self) -> FieldValidationReport:
        metrics: list[tuple[str, Any]] = [
            ("total_candidates", self.total_candidates),
            ("verified_included", self.verified_included),
            ("manual_review", self.manual_review),
            ("excluded", self.excluded),
            ("missing_leadership_evidence", self.missing_leadership_evidence),
            ("first_author_only", self.first_author_only),
            ("source-only evidence", self.source_only_evidence),
            ("conflicting evidence", self.conflicting_evidence),
        ]
        metrics.extend((f"source:{name}", count) for name, count in sorted(self.source_counts.items()))
        metrics.extend((f"ownership_reason:{name}", count) for name, count in sorted(self.reason_counts.items()))
        gates = [
            Gate("verified_non_include_rows", self.verified_non_include_rows, 0, comparison="=="),
            Gate("verified_manual_review_rows", self.verified_manual_review_rows, 0, comparison="=="),
            Gate("verified_low_confidence_rows", self.verified_low_confidence_rows, 0, comparison="=="),
            Gate(
                "verified_missing_decision_reason_rows",
                self.verified_missing_decision_reason_rows,
                0,
                comparison="==",
            ),
            Gate("verified_foreign_led_rows", self.verified_foreign_led_rows, 0, comparison="=="),
            Gate(
                "unknown_ownership_in_verified_dataset",
                self.unknown_ownership_in_verified_dataset,
                0,
                comparison="==",
            ),
        ]
        return self._base_report(metrics, gates)


# --- runner -----------------------------------------------------------------

VALIDATOR_NAMES = ("authors", "institutions", "citations", "collaboration", "ownership")


def default_input_csv() -> Path:
    for candidate in INPUT_CANDIDATES:
        if candidate.is_file():
            return candidate
    return INPUT_CANDIDATES[0]


def load_registry(registry_csv: Path) -> NationalInstitutionRegistry | None:
    if not registry_csv.is_file():
        return None
    return NationalInstitutionRegistry.from_csv(registry_csv, country_code="LK")


def build_validators(
    names: Sequence[str],
    *,
    registry: NationalInstitutionRegistry | None = None,
    max_issues: int = DEFAULT_MAX_ISSUES,
) -> list[FieldValidator]:
    validators: list[FieldValidator] = []
    for name in names:
        if name == "authors":
            validators.append(AuthorValidator(max_issues=max_issues))
        elif name == "institutions":
            validators.append(InstitutionValidator(registry=registry, max_issues=max_issues))
        elif name == "citations":
            validators.append(CitationValidator(max_issues=max_issues))
        elif name == "collaboration":
            validators.append(CollaborationValidator(max_issues=max_issues))
        elif name == "ownership":
            validators.append(OwnershipValidator(max_issues=max_issues))
        else:
            raise ValueError(f"unknown check: {name}. Choose from {', '.join(VALIDATOR_NAMES)}")
    return validators


def record_identifier(row: Mapping[str, Any], fallback_row: int) -> str:
    for column in ("record_number", "openalex_id", "doi", "source_record_id"):
        value = _clean(row.get(column))
        if value:
            return value
    return f"row:{fallback_row}"


def run_validators(
    input_csv: Path,
    validators: Sequence[FieldValidator],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[FieldValidationReport]:
    """Stream the dataset once, feeding every validator each row."""

    row_number = 0
    for chunk in _read_chunks(input_csv, chunk_size):
        for row in chunk.to_dict("records"):
            row_number += 1
            identifier = record_identifier(row, row_number)
            for validator in validators:
                validator.add_row(row, record_id=identifier)
    return [validator.report() for validator in validators]


def _read_chunks(input_csv: Path, chunk_size: int) -> Iterator[pd.DataFrame]:
    return pd.read_csv(
        input_csv,
        dtype="object",
        low_memory=False,
        chunksize=chunk_size,
        keep_default_na=False,
    )


def write_report(report: FieldValidationReport, report_dir: Path) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = report_dir / f"{report.name}_validation_summary.csv"
    issues_csv = report_dir / f"{report.name}_validation_issues.csv"
    gates_csv = report_dir / f"{report.name}_validation_gates.csv"

    pd.DataFrame(report.summary_rows(), columns=SUMMARY_FIELDNAMES).to_csv(
        summary_csv, index=False
    )
    pd.DataFrame(
        [issue.as_row() for issue in report.issues], columns=ISSUE_FIELDNAMES
    ).to_csv(issues_csv, index=False)
    pd.DataFrame([gate.as_row() for gate in report.gates], columns=GATE_FIELDNAMES).to_csv(
        gates_csv, index=False
    )
    return {"summary": summary_csv, "issues": issues_csv, "gates": gates_csv}


def render_report(report: FieldValidationReport) -> str:
    lines = [
        f"{report.name}: {'PASS' if report.passed else 'FAIL'}  ({report.rows:,} rows)",
    ]
    lines.extend(f"    {name}: {value}" for name, value in report.metrics)
    lines.append("    gates:")
    for gate in report.gates:
        lines.append(
            f"      {gate.name:<48} {gate.value:>10.4f} {gate.comparison} "
            f"{gate.threshold:<8} {gate.status}"
        )
    if report.issue_counts:
        lines.append("    issues:")
        for issue, count in report.issue_counts.most_common(10):
            lines.append(f"      {issue:<48} {count:>10,}")
        if report.issues_truncated:
            lines.append(
                f"      (samples capped at {len(report.issues):,}; counts above are complete)"
            )
    return "\n".join(lines)


def parse_checks(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in VALIDATOR_NAMES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown check(s): {', '.join(unknown)}. Choose from {', '.join(VALIDATOR_NAMES)}"
        )
    return names or list(VALIDATOR_NAMES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate author, institution, citation and collaboration fields."
    )
    parser.add_argument("--input-csv", type=Path, default=None)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--checks", type=parse_checks, default=list(VALIDATOR_NAMES))
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument(
        "--max-issues",
        type=int,
        default=DEFAULT_MAX_ISSUES,
        help="Cap on issue rows kept per check. Counts stay complete either way.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any gate fails, for use in a pipeline.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_csv = args.input_csv or default_input_csv()
    if not input_csv.is_file():
        raise SystemExit(f"{input_csv} does not exist. Run the pipeline first.")

    registry = load_registry(args.registry_csv)
    validators = build_validators(
        args.checks, registry=registry, max_issues=args.max_issues
    )
    reports = run_validators(input_csv, validators, chunk_size=args.chunk_size)

    print(f"Validating {input_csv}")
    if registry is None and "institutions" in args.checks:
        print(f"  (registry {args.registry_csv} not found: identifier checks skipped)")
    print()
    for report in reports:
        print(render_report(report))
        written = write_report(report, args.report_dir)
        print(f"    reports: {written['summary'].parent}")
        print()

    failed = [report for report in reports if not report.passed]
    if failed:
        print(f"{len(failed)} of {len(reports)} checks failed:")
        for report in failed:
            for gate in report.failed_gates:
                print(f"  {report.name}.{gate.name}: {gate.value:.4f} {gate.comparison} {gate.threshold}")
        if args.strict:
            raise SystemExit(1)
    else:
        print(f"All {len(reports)} checks passed.")


if __name__ == "__main__":
    main()
