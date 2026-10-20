#!/usr/bin/env python3
"""Merge prior accepted AI decisions with fresh high-confidence classifications."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cse_uom.dataset import deduplication_key


OUTPUT_DIR = PROJECT_ROOT / "outputs/cse_uom"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        "--prior-accepted",
        type=Path,
        required=True,
        help="Previously reviewed/accepted CSE AI CSV.",
    )
    value.add_argument(
        "--classified",
        type=Path,
        default=OUTPUT_DIR / "cse_uom_publications_ai_classified_2016_2026.csv",
    )
    value.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "cse_uom_ai_publications_verified_2016_2026.csv",
    )
    value.add_argument(
        "--review-output",
        type=Path,
        default=OUTPUT_DIR / "cse_uom_ai_manual_review.csv",
    )
    value.add_argument(
        "--summary-output",
        type=Path,
        default=OUTPUT_DIR / "cse_uom_ai_validation_summary.json",
    )
    return value


def main() -> None:
    args = parser().parse_args()
    prior_columns, prior_rows = read_csv(args.prior_accepted)
    classified_columns, classified_rows = read_csv(args.classified)
    prior_by_key = {deduplication_key(row): row for row in prior_rows}
    classified_keys = {deduplication_key(row) for row in classified_rows}

    final_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    new_auto_ai_count = 0
    prior_retained_count = 0
    for row in classified_rows:
        key = deduplication_key(row)
        prior_accepted = key in prior_by_key
        label = row.get("ai_classification_label", "")
        if prior_accepted or label == "AI":
            accepted = dict(row)
            accepted["ai_fresh_classification_label"] = label
            accepted["ai_fresh_classification_confidence"] = row.get(
                "ai_classification_confidence", ""
            )
            accepted["ai_fresh_classification_reason"] = row.get(
                "ai_classification_reason", ""
            )
            if prior_accepted and label == "AI":
                source = "prior_accepted_ai+fresh_auto_ai"
            elif prior_accepted:
                source = "prior_accepted_ai"
            else:
                source = "fresh_auto_ai"
                new_auto_ai_count += 1
            accepted["ai_dataset_acceptance_source"] = source
            accepted["ai_prior_accepted"] = str(prior_accepted).upper()
            accepted["ai_classification_label"] = "AI"
            accepted["ai_classification_reason"] = source
            final_rows.append(accepted)
            if prior_accepted:
                prior_retained_count += 1
        elif label == "review":
            review_rows.append(dict(row))

    missing_prior_rows = [
        dict(row)
        for key, row in prior_by_key.items()
        if key not in classified_keys
    ]
    for row in missing_prior_rows:
        row["ai_dataset_acceptance_source"] = "prior_accepted_ai_not_in_fresh_corpus"
        row["ai_prior_accepted"] = "TRUE"
        row["ai_fresh_classification_label"] = ""
        row["ai_fresh_classification_confidence"] = ""
        row["ai_fresh_classification_reason"] = ""
        row["ai_classification_label"] = "AI"
        final_rows.append(row)

    final_rows.sort(
        key=lambda row: (
            int(row.get("publication_year") or 0),
            str(row.get("title") or "").casefold(),
        )
    )
    columns = list(
        dict.fromkeys(
            [
                *classified_columns,
                *prior_columns,
                "ai_dataset_acceptance_source",
                "ai_prior_accepted",
                "ai_fresh_classification_label",
                "ai_fresh_classification_confidence",
                "ai_fresh_classification_reason",
            ]
        )
    )
    write_csv(args.output, columns, final_rows)
    write_csv(args.review_output, columns, review_rows)

    label_counts: dict[str, int] = {}
    for row in classified_rows:
        label = row.get("ai_classification_label", "")
        label_counts[label] = label_counts.get(label, 0) + 1
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "publication_scope": "University of Moratuwa CSE AI publications, 2016-2026",
        "fresh_verified_cse_publication_count": len(classified_rows),
        "fresh_classification_counts": label_counts,
        "prior_accepted_ai_count": len(prior_rows),
        "prior_accepted_matched_fresh_count": prior_retained_count,
        "prior_accepted_missing_fresh_count": len(missing_prior_rows),
        "new_auto_ai_count": new_auto_ai_count,
        "final_ai_publication_count": len(final_rows),
        "pending_ai_manual_review_count": len(review_rows),
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "review_output": str(args.review_output),
        "review_output_sha256": sha256(args.review_output),
    }
    args.summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
