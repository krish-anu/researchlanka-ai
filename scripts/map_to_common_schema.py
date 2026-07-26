"""Map harvested OAI-DC records (data/raw/<id>/oai_dc.jsonl) into the
project's common publication-metadata schema.

Examples:
    python scripts/map_to_common_schema.py --id uom
    python scripts/map_to_common_schema.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.schema_mapping import (
    map_crossref_record,
    map_dspace_rest_record,
    map_html_meta_record,
    map_oai_dc_record,
    map_openalex_record,
    map_pubmed_record,
)

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"
OPENALEX_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "openalex"
RECOVERY_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "recovery"


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def map_one(institution_id: str) -> int:
    """Map one institution's raw data into the common schema.

    An institution may have been harvested via up to three routes (OAI-DC,
    DSpace REST, HTML meta-tag crawl); uses whichever captured the most
    records -- several hosts have a broken/partial OAI route where another
    route got further (uwu, cmb, jfn_*). Never merges routes, to avoid
    duplicating the same items.
    """

    candidates = [
        (DEFAULT_RAW_DIR / institution_id / "oai_dc.jsonl", map_oai_dc_record, "oai"),
        (DEFAULT_RAW_DIR / institution_id / "rest_items.jsonl", map_dspace_rest_record, "rest"),
        (DEFAULT_RAW_DIR / institution_id / "html_meta.jsonl", map_html_meta_record, "html"),
        (DEFAULT_RAW_DIR / institution_id / "crossref_works.jsonl", map_crossref_record, "crossref"),
    ]
    counted = [
        (path.exists() and _count_lines(path) or 0, path, mapper, kind)
        for path, mapper, kind in candidates
    ]

    best_count, raw_path, mapper, source_kind = max(counted, key=lambda c: c[0])

    if best_count == 0:
        if not any(path.exists() for _, path, _, _ in counted):
            print(f"Skipping {institution_id}: no raw files under {DEFAULT_RAW_DIR / institution_id}")
        else:
            print(f"{institution_id}: mapped 0 records (raw files empty)")
        return 0

    output_path = DEFAULT_PROCESSED_DIR / f"{institution_id}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped_deleted = 0
    with raw_path.open(encoding="utf-8") as raw_file, output_path.open(
        "w", encoding="utf-8"
    ) as output_file:
        for line in raw_file:
            if not line.strip():
                continue
            record = json.loads(line)
            mapped = mapper(record, institution_id=institution_id)
            if mapped.get("deleted"):
                skipped_deleted += 1
                continue
            output_file.write(json.dumps(mapped, ensure_ascii=False) + "\n")
            total += 1

    note = f" ({skipped_deleted} deleted skipped)" if skipped_deleted else ""
    print(f"{institution_id}: mapped {total} records via {source_kind} -> {output_path}{note}")
    return total


def map_openalex_one(institution_id: str) -> int:
    """Map one institution's OpenAlex works into the common schema.

    Kept out of ``map_one``'s best-route contest on purpose: OpenAlex is a
    second, complementary population (DOI-bearing journal output) for the
    same institution, not another way of reading the repository, so it
    lands in its own processed namespace and is never allowed to displace
    the repository records.
    """

    raw_path = DEFAULT_RAW_DIR / institution_id / "openalex_works.jsonl"
    if not raw_path.exists():
        return 0

    output_path = OPENALEX_PROCESSED_DIR / f"{institution_id}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped_retracted = 0
    with raw_path.open(encoding="utf-8") as raw_file, output_path.open(
        "w", encoding="utf-8"
    ) as output_file:
        for line in raw_file:
            if not line.strip():
                continue
            mapped = map_openalex_record(json.loads(line), institution_id=institution_id)
            if mapped.get("deleted"):
                skipped_retracted += 1
                continue
            output_file.write(json.dumps(mapped, ensure_ascii=False) + "\n")
            total += 1

    note = f" ({skipped_retracted} retracted skipped)" if skipped_retracted else ""
    print(f"{institution_id}: mapped {total} records via openalex -> {output_path}{note}")
    return total


def _normalise_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    text = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.rstrip(".").strip() or None


def map_recovery_one(institution_id: str) -> int:
    """Map an institution's recovery-route data into the common schema.

    For institutions whose own repository cannot be harvested (kln), the
    Crossref-by-affiliation and PubMed-by-affiliation routes are the only
    sources. Unlike the repository routes these two are *merged*, because
    they cover overlapping populations: records are deduplicated on DOI,
    keeping the Crossref record (the publisher's own deposit) and filling
    its empty fields from the PubMed twin, which usually has the abstract
    and always has MeSH terms.
    """

    crossref_path = DEFAULT_RAW_DIR / institution_id / "crossref_affiliation.jsonl"
    pubmed_path = DEFAULT_RAW_DIR / institution_id / "pubmed_works.jsonl"
    if not crossref_path.exists() and not pubmed_path.exists():
        return 0

    records: list[dict] = []
    by_doi: dict[str, dict] = {}

    if crossref_path.exists():
        with crossref_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                mapped = map_crossref_record(
                    json.loads(line),
                    institution_id=institution_id,
                    source="crossref_affiliation",
                )
                records.append(mapped)
                if (doi := _normalise_doi(mapped.get("doi"))):
                    by_doi[doi] = mapped

    merged = 0
    if pubmed_path.exists():
        with pubmed_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                mapped = map_pubmed_record(json.loads(line), institution_id=institution_id)
                doi = _normalise_doi(mapped.get("doi"))
                twin = by_doi.get(doi) if doi else None
                if twin is None:
                    records.append(mapped)
                    if doi:
                        by_doi[doi] = mapped
                    continue
                # Same paper from both routes: enrich, never duplicate.
                for field in ("abstract", "keywords", "journal", "volume", "issue", "issn"):
                    if not twin.get(field) and mapped.get(field):
                        twin[field] = mapped[field]
                twin["also_in_pubmed"] = True
                if mapped.get("source_record_id"):
                    twin.setdefault("raw_identifiers", []).append(mapped["source_record_id"])
                merged += 1

    output_path = RECOVERY_PROCESSED_DIR / f"{institution_id}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    note = f" ({merged} shared with PubMed, merged)" if merged else ""
    print(f"{institution_id}: mapped {len(records)} records via recovery routes -> {output_path}{note}")
    return len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map raw OAI-DC records into the common schema.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", default=None, help="Single institution id to map.")
    group.add_argument("--all", action="store_true", help="Map every institution with raw data on disk.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.id:
        map_one(args.id)
        map_openalex_one(args.id)
        map_recovery_one(args.id)
        return

    if not DEFAULT_RAW_DIR.exists():
        print(f"No raw data directory at {DEFAULT_RAW_DIR}")
        return

    raw_filenames = (
        "oai_dc.jsonl",
        "rest_items.jsonl",
        "html_meta.jsonl",
        "crossref_works.jsonl",
        "openalex_works.jsonl",
        "crossref_affiliation.jsonl",
        "pubmed_works.jsonl",
    )
    ids = sorted(
        p.name
        for p in DEFAULT_RAW_DIR.iterdir()
        if p.is_dir() and any((p / name).exists() for name in raw_filenames)
    )
    if not ids:
        print("No harvested raw files found under data/raw/.")
        return

    total = 0
    openalex_total = 0
    recovery_total = 0
    for institution_id in ids:
        total += map_one(institution_id)
        openalex_total += map_openalex_one(institution_id)
        recovery_total += map_recovery_one(institution_id)
    print(f"\nMapped {total} repository records across {len(ids)} institutions.")
    if openalex_total:
        print(f"Mapped {openalex_total} OpenAlex records alongside them.")
    if recovery_total:
        print(f"Mapped {recovery_total} recovery-route records (blocked repositories).")


if __name__ == "__main__":
    main()
