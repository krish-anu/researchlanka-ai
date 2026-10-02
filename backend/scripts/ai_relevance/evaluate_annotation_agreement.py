"""Evaluate agreement between two AI-relevance annotator columns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix


VALID_LABELS = ("AI", "NON_AI", "REVIEW")


def normalize_label(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if text in {"AI", "ARTIFICIAL_INTELLIGENCE"}:
        return "AI"
    if text in {"NON_AI", "NONAI", "NOT_AI", "NON_AI_RELEVANT"}:
        return "NON_AI"
    if text in {"REVIEW", "UNCERTAIN", "UNSURE", "AMBIGUOUS"}:
        return "REVIEW"
    if not text:
        return None
    raise ValueError(f"Unsupported annotation label: {value!r}")


def evaluate_agreement(
    frame: pd.DataFrame,
    *,
    annotator_a: str,
    annotator_b: str,
    include_review: bool,
) -> dict[str, Any]:
    missing = [column for column in (annotator_a, annotator_b) if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing annotator column(s): {', '.join(missing)}")

    labels = list(VALID_LABELS if include_review else ("AI", "NON_AI"))
    scored = pd.DataFrame(
        {
            "annotator_a": frame[annotator_a].map(normalize_label),
            "annotator_b": frame[annotator_b].map(normalize_label),
        }
    ).dropna()
    if not include_review:
        scored = scored[
            scored["annotator_a"].isin(labels) & scored["annotator_b"].isin(labels)
        ].copy()
    if scored.empty:
        raise ValueError("No overlapping completed annotation rows are available.")

    agreement = scored["annotator_a"].eq(scored["annotator_b"])
    matrix = confusion_matrix(
        scored["annotator_a"],
        scored["annotator_b"],
        labels=labels,
    )
    return {
        "annotator_a": annotator_a,
        "annotator_b": annotator_b,
        "include_review": include_review,
        "labels": labels,
        "overlap_rows": int(len(scored)),
        "agreement_rows": int(agreement.sum()),
        "disagreement_rows": int((~agreement).sum()),
        "percent_agreement": float(agreement.mean()),
        "cohens_kappa": float(
            cohen_kappa_score(scored["annotator_a"], scored["annotator_b"], labels=labels)
        ),
        "confusion_matrix": [
            {
                "annotator_a_label": label,
                **{predicted: int(matrix[index][j]) for j, predicted in enumerate(labels)},
            }
            for index, label in enumerate(labels)
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate percent agreement and Cohen's kappa for two annotators."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--annotator-a", required=True)
    parser.add_argument("--annotator-b", required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="Include REVIEW as a third class. By default only AI/NON_AI rows are scored.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = pd.read_csv(args.input, dtype="object", low_memory=False)
    metrics = evaluate_agreement(
        frame,
        annotator_a=args.annotator_a,
        annotator_b=args.annotator_b,
        include_review=args.include_review,
    )
    payload = json.dumps(metrics, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
