"""Tag final-dataset publications with a university department.

The consolidated dataset records affiliations at institution level only, but
the raw affiliation strings OpenAlex and Crossref keep per authorship often
name the department as well ("Dept. of Computer Science & Engineering,
University of Moratuwa"). This step reads those strings from the Sri Lanka
affiliation-audit outputs and tags every final-dataset publication that has at
least one author in a configured department.

A publication is tagged in one of two ways:

* ``explicit`` -- an author's affiliation string on that publication names the
  department at the target institution.
* ``inferred`` -- an author lists only the institution on that publication (no
  department, faculty or school), but named the department on at least
  ``--min-history`` other works in the corpus and named it at least
  ``--dominance`` times as often as any other unit of the institution.

Departments are configured in ``configurations/sri_lanka/departments.json``.
Two files come out, served by the API as a sidecar to ``final_publications``:

* one row per tagged publication and department author, with the evidence;
* a JSON summary with the counts and rules of the run.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.loader import build_final_publication_row  # noqa: E402
from src.utils.doi import normalize_doi  # noqa: E402


DEFAULT_CONFIG_JSON = PROJECT_ROOT / "configurations" / "sri_lanka" / "departments.json"
DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_ai_only_all_review_binary_resolved.csv"
)
DEFAULT_OPENALEX_AUTHORSHIPS = (
    PROJECT_ROOT / "data" / "reports" / "openalex_lk_affiliation_audit" / "verified_lk_authorships.csv"
)
DEFAULT_CROSSREF_AUTHORSHIPS = (
    PROJECT_ROOT / "data" / "reports" / "crossref_lk_affiliation_audit" / "verified_lk_authorships.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "common" / "departments"
PUBLICATION_AUTHORS_FILENAME = "department_publication_authors.csv"
SUMMARY_FILENAME = "department_tagging_summary.json"

DEFAULT_MIN_HISTORY = 2
DEFAULT_DOMINANCE = 2.0

# Authorship labels, strongest first.
DEPARTMENT = "department"
OTHER_UNIT = "other_unit"
INSTITUTION_ONLY = "institution_only"
LABEL_PRECEDENCE = (DEPARTMENT, OTHER_UNIT, INSTITUTION_ONLY)

EXPLICIT = "explicit"
INFERRED = "inferred"

UNIT_PHRASE_RE = re.compile(r"\b(?:department|dept\.?|faculty|school|division)\b", re.IGNORECASE)
# A segment naming one of these is about some other organisation unless it
# also names the target institution.
OTHER_INSTITUTION_RE = re.compile(
    r"universit|institute\s+of\s+technology|\bcampus\b|\bcollege\b",
    re.IGNORECASE,
)
OPENALEX_WORK_ID_RE = re.compile(r"(W\d+)", re.IGNORECASE)

PUBLICATION_AUTHOR_COLUMNS = [
    "department_id",
    "publication_key",
    "doi",
    "openalex_id",
    "source_dataset",
    "source_record_id",
    "publication_year",
    "title",
    "publication_match",
    "author_id",
    "author_name",
    "author_match",
    "author_department_works",
    "author_other_unit_works",
    "evidence",
]


@dataclass(frozen=True)
class DepartmentSpec:
    """One configured department and the patterns that identify it."""

    department_id: str
    name: str
    short_name: str
    institution_id: str
    institution_name: str
    faculty: str | None
    url: str | None
    unit_patterns: tuple[re.Pattern[str], ...]
    institution_patterns: tuple[re.Pattern[str], ...]
    openalex_institution_names: frozenset[str]
    parent_unit_patterns: tuple[re.Pattern[str], ...] = ()

    @classmethod
    def from_config(cls, entry: dict[str, Any]) -> "DepartmentSpec":
        def compile_all(key: str) -> tuple[re.Pattern[str], ...]:
            return tuple(re.compile(pattern, re.IGNORECASE) for pattern in entry.get(key, []))

        return cls(
            department_id=str(entry["department_id"]),
            name=str(entry["name"]),
            short_name=str(entry.get("short_name") or entry["name"]),
            institution_id=str(entry.get("institution_id") or ""),
            institution_name=str(entry["institution_name"]),
            faculty=entry.get("faculty"),
            url=entry.get("url"),
            unit_patterns=compile_all("unit_patterns"),
            institution_patterns=compile_all("institution_patterns"),
            openalex_institution_names=frozenset(
                str(name).casefold() for name in entry.get("openalex_institution_names", [])
            ),
            parent_unit_patterns=compile_all("parent_unit_patterns"),
        )

    def names_unit(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.unit_patterns)

    def names_institution(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.institution_patterns)

    def is_openalex_institution(self, institution_names: Iterable[Any]) -> bool:
        return any(
            str(name).strip().casefold() in self.openalex_institution_names
            for name in institution_names
            if not is_blank(name)
        )

    def names_other_unit(self, text: str) -> bool:
        stripped = text
        for pattern in self.parent_unit_patterns:
            stripped = pattern.sub(" ", stripped)
        return bool(UNIT_PHRASE_RE.search(stripped))

    def metadata(self) -> dict[str, Any]:
        return {
            "department_id": self.department_id,
            "name": self.name,
            "short_name": self.short_name,
            "institution_id": self.institution_id,
            "institution_name": self.institution_name,
            "faculty": self.faculty,
            "url": self.url,
        }


@dataclass(frozen=True)
class AuthorshipMatch:
    author_id: str | None
    author_name: str
    label: str
    evidence: str | None


@dataclass
class AuthorHistory:
    department_works: set[str] = field(default_factory=set)
    other_unit_works: set[str] = field(default_factory=set)

    def qualifies(self, *, min_history: int, dominance: float) -> bool:
        department = len(self.department_works)
        return department >= min_history and department >= dominance * len(self.other_unit_works)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip().casefold() in {"", "nan", "none", "null"}


def load_departments(path: Path, department_ids: Iterable[str] | None = None) -> list[DepartmentSpec]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    specs = [DepartmentSpec.from_config(entry) for entry in payload.get("departments", [])]
    wanted = {value.casefold() for value in department_ids or []}
    if wanted:
        specs = [spec for spec in specs if spec.department_id.casefold() in wanted]
        missing = wanted - {spec.department_id.casefold() for spec in specs}
        if missing:
            raise ValueError(f"Unknown department id(s): {', '.join(sorted(missing))}")
    return specs


def affiliation_segments(raw: Any) -> list[str]:
    """Split a flattened raw-affiliation cell into one string per affiliation.

    Entities are decoded first: Crossref strings carry ``&amp;`` whose ``;``
    would otherwise split "Computer Science &amp; Engineering" in two.
    """
    if is_blank(raw):
        return []
    text = html.unescape(str(raw))
    return [segment.strip() for segment in text.split(";") if segment.strip()]


def classify_segment(segment: str, spec: DepartmentSpec, *, at_institution: bool) -> str | None:
    """Label one affiliation string relative to the department.

    ``at_institution`` says whether OpenAlex matched the authorship to the
    target institution; it lets a bare "Department of Computer Science and
    Engineering" count, unless the string names some other organisation.
    """
    names_target = spec.names_institution(segment) or (
        at_institution and not OTHER_INSTITUTION_RE.search(segment)
    )
    if not names_target:
        return None
    if spec.names_unit(segment):
        return DEPARTMENT
    if spec.names_other_unit(segment):
        return OTHER_UNIT
    return INSTITUTION_ONLY


def classify_authorship(
    raw_affiliations: Any,
    spec: DepartmentSpec,
    *,
    at_institution: bool,
) -> tuple[str | None, str | None]:
    """Return the strongest label across an authorship's affiliations, with evidence."""
    best_label: str | None = None
    best_evidence: str | None = None
    for segment in affiliation_segments(raw_affiliations):
        label = classify_segment(segment, spec, at_institution=at_institution)
        if label is None:
            continue
        if best_label is None or LABEL_PRECEDENCE.index(label) < LABEL_PRECEDENCE.index(best_label):
            best_label, best_evidence = label, segment
    if best_label is None and at_institution:
        best_label = INSTITUTION_ONLY
    return best_label, best_evidence


def publication_year(row: dict[str, Any]) -> int | None:
    """Year of a loader-shaped row, falling back to the date as the API's SQL does."""
    if row.get("publication_year"):
        return int(row["publication_year"])
    match = re.match(r"(\d{4})", str(row.get("publication_date") or ""))
    return int(match.group(1)) if match else None


def openalex_work_id(value: Any) -> str | None:
    if is_blank(value):
        return None
    match = OPENALEX_WORK_ID_RE.search(str(value))
    return match.group(1).upper() if match else None


def openalex_authorship_matches(
    authorships: pd.DataFrame,
    spec: DepartmentSpec,
) -> dict[str, list[AuthorshipMatch]]:
    """Label each OpenAlex authorship, grouped by work id.

    The audit file has one row per authorship and matched institution, so
    rows are first folded back to one authorship.
    """
    matches: dict[str, list[AuthorshipMatch]] = {}
    frame = authorships.assign(_work_id=authorships["openalex_work_id"].map(openalex_work_id))
    frame = frame[frame["_work_id"].notna()]
    author_key = frame["openalex_author_id"].where(
        frame["openalex_author_id"].map(lambda value: not is_blank(value)),
        "name:" + frame["author_name"].astype(str),
    )
    frame = frame.assign(_author_key=author_key)
    for (work_id, author_key), group in frame.groupby(["_work_id", "_author_key"], sort=False):
        at_institution = spec.is_openalex_institution(group["institution_name"])
        label, evidence = classify_authorship(
            group["raw_affiliation_strings"].iloc[0],
            spec,
            at_institution=at_institution,
        )
        if label is None:
            continue
        author_id = None if str(author_key).startswith("name:") else str(author_key)
        matches.setdefault(work_id, []).append(
            AuthorshipMatch(
                author_id=author_id,
                author_name=str(group["author_name"].iloc[0]).strip(),
                label=label,
                evidence=evidence,
            )
        )
    return matches


def crossref_authorship_matches(
    authorships: pd.DataFrame,
    spec: DepartmentSpec,
) -> dict[str, list[AuthorshipMatch]]:
    """Label Crossref authorships by DOI. Crossref has no institution ids."""
    matches: dict[str, list[AuthorshipMatch]] = {}
    for row in authorships.itertuples(index=False):
        doi = normalize_doi(getattr(row, "doi", None))
        if not doi:
            continue
        label, evidence = classify_authorship(row.raw_affiliation_strings, spec, at_institution=False)
        if label is None:
            continue
        matches.setdefault(doi, []).append(
            AuthorshipMatch(
                author_id=None,
                author_name=str(row.author_name).strip(),
                label=label,
                evidence=evidence,
            )
        )
    return matches


def author_histories(matches: dict[str, list[AuthorshipMatch]]) -> dict[str, AuthorHistory]:
    histories: dict[str, AuthorHistory] = {}
    for work_id, authorships in matches.items():
        for authorship in authorships:
            if authorship.author_id is None:
                continue
            history = histories.setdefault(authorship.author_id, AuthorHistory())
            if authorship.label == DEPARTMENT:
                history.department_works.add(work_id)
            elif authorship.label == OTHER_UNIT:
                history.other_unit_works.add(work_id)
    return histories


def tag_department(
    final_rows: pd.DataFrame,
    openalex_authorships: pd.DataFrame,
    crossref_authorships: pd.DataFrame,
    spec: DepartmentSpec,
    *,
    min_history: int = DEFAULT_MIN_HISTORY,
    dominance: float = DEFAULT_DOMINANCE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Tag final-dataset rows for one department.

    Returns the publication-author rows and the summary for the department.
    """
    openalex_matches = openalex_authorship_matches(openalex_authorships, spec)
    crossref_matches = crossref_authorship_matches(crossref_authorships, spec)
    histories = author_histories(openalex_matches)

    rows: list[dict[str, Any]] = []
    coverage: Counter[str] = Counter()
    authors_seen: set[str] = set()

    for row_number, record in enumerate(final_rows.to_dict("records"), start=1):
        work_id = openalex_work_id(record.get("openalex_id"))
        doi = normalize_doi(record.get("doi"))
        openalex_authorships_here = openalex_matches.get(work_id, []) if work_id else []
        crossref_authorships_here = crossref_matches.get(doi, []) if doi else []

        department_authors: list[tuple[AuthorshipMatch, str, str | None]] = []
        for authorship in openalex_authorships_here:
            if authorship.label == DEPARTMENT:
                department_authors.append((authorship, EXPLICIT, authorship.evidence))
            elif authorship.label == INSTITUTION_ONLY and authorship.author_id:
                history = histories.get(authorship.author_id)
                if history and history.qualifies(min_history=min_history, dominance=dominance):
                    evidence = (
                        f"No unit named on this work; named {spec.short_name} on "
                        f"{len(history.department_works)} other works"
                    )
                    department_authors.append((authorship, INFERRED, evidence))
        if not department_authors:
            # Crossref only fills gaps: its author names ("Perera, A.") would
            # otherwise duplicate the OpenAlex display names.
            department_authors = [
                (authorship, EXPLICIT, authorship.evidence)
                for authorship in crossref_authorships_here
                if authorship.label == DEPARTMENT
            ]

        labels = {authorship.label for authorship in [*openalex_authorships_here, *crossref_authorships_here]}
        at_institution = bool(labels) or spec.institution_name.casefold() in str(
            record.get("sri_lankan_institutions") or record.get("institutions") or ""
        ).casefold()
        if not at_institution:
            continue

        matches = {match for _, match, _ in department_authors}
        if EXPLICIT in matches:
            publication_match = EXPLICIT
        elif INFERRED in matches:
            publication_match = INFERRED
        else:
            coverage[OTHER_UNIT if OTHER_UNIT in labels else INSTITUTION_ONLY] += 1
            continue
        coverage[publication_match] += 1

        key_row = build_final_publication_row(record, row_number)
        seen_here: set[str] = set()
        for authorship, author_match, evidence in department_authors:
            identity = authorship.author_id or authorship.author_name.casefold()
            if identity in seen_here:
                continue
            seen_here.add(identity)
            authors_seen.add(identity)
            history = histories.get(authorship.author_id or "", AuthorHistory())
            rows.append(
                {
                    "department_id": spec.department_id,
                    "publication_key": key_row["publication_key"],
                    "doi": key_row.get("doi"),
                    "openalex_id": None if is_blank(record.get("openalex_id")) else record.get("openalex_id"),
                    "source_dataset": record.get("source_dataset"),
                    "source_record_id": record.get("source_record_id"),
                    "publication_year": publication_year(key_row),
                    "title": record.get("title"),
                    "publication_match": publication_match,
                    "author_id": authorship.author_id,
                    "author_name": authorship.author_name,
                    "author_match": author_match,
                    "author_department_works": len(history.department_works),
                    "author_other_unit_works": len(history.other_unit_works),
                    "evidence": evidence,
                }
            )

    summary = {
        **spec.metadata(),
        "rules": {
            "unit_patterns": [pattern.pattern for pattern in spec.unit_patterns],
            "institution_patterns": [pattern.pattern for pattern in spec.institution_patterns],
            "openalex_institution_names": sorted(spec.openalex_institution_names),
            "min_history": min_history,
            "dominance": dominance,
        },
        "counts": {
            "final_publications": int(len(final_rows)),
            "institution_publications": int(sum(coverage.values())),
            "department_publications": int(coverage[EXPLICIT] + coverage[INFERRED]),
            "explicit_publications": int(coverage[EXPLICIT]),
            "inferred_publications": int(coverage[INFERRED]),
            "other_unit_publications": int(coverage[OTHER_UNIT]),
            "institution_only_publications": int(coverage[INSTITUTION_ONLY]),
            "department_authors": len(authors_seen),
        },
    }
    return rows, summary


def read_authorships(path: Path, columns: list[str]) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Authorship audit file not found: {path}. Run `make lk-affiliation-audits` first."
        )
    return pd.read_csv(path, usecols=columns, dtype=str, low_memory=False)


def build_department_tags(
    *,
    input_csv: Path,
    openalex_authorships_csv: Path,
    crossref_authorships_csv: Path,
    config_json: Path,
    output_dir: Path,
    department_ids: list[str] | None = None,
    min_history: int = DEFAULT_MIN_HISTORY,
    dominance: float = DEFAULT_DOMINANCE,
) -> dict[str, Any]:
    specs = load_departments(config_json, department_ids)
    final_rows = pd.read_csv(input_csv, low_memory=False)
    openalex_authorships = read_authorships(
        openalex_authorships_csv,
        ["openalex_work_id", "openalex_author_id", "author_name", "raw_affiliation_strings", "institution_name"],
    )
    crossref_authorships = read_authorships(
        crossref_authorships_csv,
        ["doi", "author_name", "raw_affiliation_strings"],
    )

    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for spec in specs:
        rows, summary = tag_department(
            final_rows,
            openalex_authorships,
            crossref_authorships,
            spec,
            min_history=min_history,
            dominance=dominance,
        )
        all_rows.extend(rows)
        summaries.append(summary)

    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows, columns=PUBLICATION_AUTHOR_COLUMNS).to_csv(
        output_dir / PUBLICATION_AUTHORS_FILENAME,
        index=False,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "final_dataset": str(input_csv),
            "openalex_authorships": str(openalex_authorships_csv),
            "crossref_authorships": str(crossref_authorships_csv),
        },
        "departments": summaries,
    }
    (output_dir / SUMMARY_FILENAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tag final-dataset publications with configured university departments."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--openalex-authorships", type=Path, default=DEFAULT_OPENALEX_AUTHORSHIPS)
    parser.add_argument("--crossref-authorships", type=Path, default=DEFAULT_CROSSREF_AUTHORSHIPS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_JSON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--department",
        action="append",
        dest="departments",
        help="Department id to tag; repeat for several. Defaults to every configured department.",
    )
    parser.add_argument(
        "--min-history",
        type=int,
        default=DEFAULT_MIN_HISTORY,
        help="Works naming the department an author needs before unit-less works are inferred.",
    )
    parser.add_argument(
        "--dominance",
        type=float,
        default=DEFAULT_DOMINANCE,
        help="How many times more often the department must be named than other units.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_department_tags(
        input_csv=args.input_csv,
        openalex_authorships_csv=args.openalex_authorships,
        crossref_authorships_csv=args.crossref_authorships,
        config_json=args.config,
        output_dir=args.output_dir,
        department_ids=args.departments,
        min_history=args.min_history,
        dominance=args.dominance,
    )
    for summary in payload["departments"]:
        counts = summary["counts"]
        print(
            f"{summary['department_id']}: {counts['department_publications']} publications "
            f"({counts['explicit_publications']} explicit, {counts['inferred_publications']} inferred) "
            f"of {counts['institution_publications']} at {summary['institution_name']}; "
            f"{counts['department_authors']} authors"
        )
    print(f"Wrote {args.output_dir / PUBLICATION_AUTHORS_FILENAME}")
    print(f"Wrote {args.output_dir / SUMMARY_FILENAME}")


if __name__ == "__main__":
    main()
