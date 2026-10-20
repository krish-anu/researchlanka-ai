#!/usr/bin/env python3
"""Build candidate and verified UoM CSE publication CSV files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cse_uom.dataset import build_cse_uom_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Match the official UoM CSE staff roster to a publication dataset, "
            "verify UoM affiliation, and deduplicate verified records."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--roster",
        type=Path,
        default=PROJECT_ROOT / "data/config/cse_uom_staff.tsv",
    )
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--verified-output", type=Path, required=True)
    parser.add_argument(
        "--corrections",
        type=Path,
        help="Reviewed DOI-level CSE attribution corrections (TSV).",
    )
    parser.add_argument(
        "--supplement",
        type=Path,
        action="append",
        default=[],
        help="Reviewed publication CSV to append before CSE matching; repeatable.",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="Optional CSV containing VERIFIED, REVIEW, and REJECT decisions.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional JSON validation summary.",
    )
    parser.add_argument("--year-min", type=int, default=2016)
    parser.add_argument("--year-max", type=int, default=2026)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.year_min > args.year_max:
        raise SystemExit("--year-min must be less than or equal to --year-max")
    summary = build_cse_uom_dataset(
        input_path=args.input,
        roster_path=args.roster,
        candidate_output=args.candidate_output,
        verified_output=args.verified_output,
        corrections_path=args.corrections,
        supplement_paths=args.supplement,
        audit_output=args.audit_output,
        year_min=args.year_min,
        year_max=args.year_max,
    )
    rendered_summary = json.dumps(summary, indent=2, sort_keys=True)
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(f"{rendered_summary}\n", encoding="utf-8")
    print(rendered_summary)


if __name__ == "__main__":
    main()
