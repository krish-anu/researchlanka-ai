"""Report how much of an institution's OpenAlex output is genuinely new
next to its repository records.

The two sources overlap only partly: repositories hold theses, conference
papers and locally published work, OpenAlex holds indexed journal output.
This script quantifies that per institution so the combined figure is not
double-counted, matching on DOI first and on a normalised title second
(repository records rarely carry a DOI, so title matching does most of
the work).

Examples:
    python scripts/compare_repository_openalex.py
    python scripts/compare_repository_openalex.py --ids cmb,pdn
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

REPOSITORY_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"
OPENALEX_DIR = PROJECT_ROOT / "data" / "processed" / "openalex"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"

PUNCTUATION_RE = re.compile(r"[^a-z0-9 ]+")
WHITESPACE_RE = re.compile(r"\s+")


def normalise_title(title: str | None) -> str | None:
    """Lowercase, strip punctuation and collapse whitespace.

    Deliberately blunt: repository titles carry stray trailing full stops,
    bracketed notes and double spaces that would otherwise defeat an exact
    match against the same paper in OpenAlex.
    """

    if not title:
        return None
    text = PUNCTUATION_RE.sub(" ", title.lower())
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def normalise_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    text = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.rstrip(".").strip() or None


def load_keys(path: Path) -> tuple[set[str], set[str], int]:
    """Return (dois, normalised titles, record count) for one JSONL file."""

    dois: set[str] = set()
    titles: set[str] = set()
    count = 0
    if not path.exists():
        return dois, titles, count

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            count += 1
            if (doi := normalise_doi(record.get("doi"))):
                dois.add(doi)
            if (title := normalise_title(record.get("title"))):
                titles.add(title)
    return dois, titles, count


def compare_one(institution_id: str) -> dict[str, int] | None:
    repo_dois, repo_titles, repo_count = load_keys(REPOSITORY_DIR / f"{institution_id}.jsonl")
    oa_path = OPENALEX_DIR / f"{institution_id}.jsonl"
    if not oa_path.exists():
        return None

    matched_doi = 0
    matched_title = 0
    new_records = 0
    oa_count = 0

    with oa_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            oa_count += 1
            doi = normalise_doi(record.get("doi"))
            title = normalise_title(record.get("title"))
            if doi and doi in repo_dois:
                matched_doi += 1
            elif title and title in repo_titles:
                matched_title += 1
            else:
                new_records += 1

    return {
        "repository_records": repo_count,
        "openalex_records": oa_count,
        "matched_by_doi": matched_doi,
        "matched_by_title": matched_title,
        "new_from_openalex": new_records,
        "combined_unique": repo_count + new_records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare repository and OpenAlex records per institution."
    )
    parser.add_argument(
        "--ids",
        default=None,
        help="Comma-separated institution ids. Default: every id with OpenAlex data.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help=f"Also write a JSON report into {REPORT_DIR}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.ids:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    elif OPENALEX_DIR.exists():
        ids = sorted(p.stem for p in OPENALEX_DIR.glob("*.jsonl"))
    else:
        print(f"No OpenAlex data under {OPENALEX_DIR}.")
        return

    if not ids:
        print(f"No OpenAlex data under {OPENALEX_DIR}.")
        return

    results: dict[str, dict[str, int]] = {}
    header = f"{'id':6s} {'repo':>8s} {'openalex':>9s} {'dup(doi)':>9s} {'dup(title)':>11s} {'new':>8s} {'combined':>9s}"
    print(header)
    print("-" * len(header))

    for institution_id in ids:
        stats = compare_one(institution_id)
        if stats is None:
            print(f"{institution_id:6s} no OpenAlex file")
            continue
        results[institution_id] = stats
        print(
            f"{institution_id:6s} {stats['repository_records']:8d} {stats['openalex_records']:9d} "
            f"{stats['matched_by_doi']:9d} {stats['matched_by_title']:11d} "
            f"{stats['new_from_openalex']:8d} {stats['combined_unique']:9d}"
        )

    if results:
        totals = {
            key: sum(stats[key] for stats in results.values())
            for key in next(iter(results.values()))
        }
        print("-" * len(header))
        print(
            f"{'TOTAL':6s} {totals['repository_records']:8d} {totals['openalex_records']:9d} "
            f"{totals['matched_by_doi']:9d} {totals['matched_by_title']:11d} "
            f"{totals['new_from_openalex']:8d} {totals['combined_unique']:9d}"
        )

    if args.report and results:
        from datetime import datetime, timezone

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_DIR / f"repository_openalex_overlap_{timestamp}.json"
        report_path.write_text(
            json.dumps({"institutions": results}, indent=2), encoding="utf-8"
        )
        print(f"\nWrote {report_path}")


if __name__ == "__main__":
    main()
