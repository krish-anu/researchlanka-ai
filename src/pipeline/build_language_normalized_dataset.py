"""Build a publication dataset with normalized language values."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final_2016_2026.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_language_normalized.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_language_normalized_summary.csv"
)

LANGUAGE_ALIASES = {
    "english": "en",
}


def normalize_language(value: Any) -> str:
    """Normalize a raw language value to a compact lowercase code."""
    if pd.isna(value):
        return "unknown"

    text = str(value).strip()
    if not text:
        return "unknown"

    normalized = text.lower().replace("-", "_")
    normalized = LANGUAGE_ALIASES.get(normalized, normalized)

    if "_" in normalized:
        language_code = normalized.split("_", maxsplit=1)[0].strip()
        return language_code or "unknown"

    return normalized


def normalize_language_column(df: pd.DataFrame) -> pd.DataFrame:
    if "language" not in df.columns:
        raise ValueError("Input dataset must include a language column.")

    normalized = df.copy()
    normalized["language"] = normalized["language"].map(normalize_language)
    return normalized


def language_summary_rows(before: pd.Series, after: pd.Series) -> list[dict[str, Any]]:
    before_values = before.fillna("").astype(str).str.strip()
    before_values = before_values.mask(before_values.eq(""), "unknown")
    after_values = after.fillna("").astype(str).str.strip()

    summary = (
        pd.DataFrame({"raw_language": before_values, "normalized_language": after_values})
        .value_counts(["raw_language", "normalized_language"])
        .reset_index(name="rows")
        .sort_values(["normalized_language", "raw_language"])
    )
    return summary.to_dict("records")


def write_summary(
    output_path: Path,
    *,
    input_csv: Path,
    output_csv: Path,
    input_rows: int,
    input_columns: int,
    output_rows: int,
    output_columns: int,
    distinct_languages_before: int,
    distinct_languages_after: int,
) -> None:
    rows = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "input_rows", "value": input_rows},
        {"metric": "input_columns", "value": input_columns},
        {"metric": "output_rows", "value": output_rows},
        {"metric": "output_columns", "value": output_columns},
        {"metric": "distinct_languages_before", "value": distinct_languages_before},
        {"metric": "distinct_languages_after", "value": distinct_languages_after},
        {"metric": "normalization_rule", "value": "lowercase; en_US -> en; si_lk -> si; blanks -> unknown"},
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def build_language_normalized_dataset(
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
) -> pd.DataFrame:
    df = pd.read_csv(input_csv, dtype="object", low_memory=False)
    normalized = normalize_language_column(df)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_csv, index=False)

    before = df["language"].fillna("").astype(str).str.strip().replace("", pd.NA)
    after = normalized["language"].fillna("").astype(str).str.strip().replace("", pd.NA)
    write_summary(
        summary_csv,
        input_csv=input_csv,
        output_csv=output_csv,
        input_rows=len(df),
        input_columns=len(df.columns),
        output_rows=len(normalized),
        output_columns=len(normalized.columns),
        distinct_languages_before=before.nunique(dropna=True),
        distinct_languages_after=after.nunique(dropna=True),
    )

    mapping_csv = summary_csv.with_name(summary_csv.stem.replace("_summary", "_mapping") + ".csv")
    pd.DataFrame(language_summary_rows(df["language"], normalized["language"])).to_csv(
        mapping_csv,
        index=False,
    )

    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a dataset with normalized language values.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalized = build_language_normalized_dataset(args.input_csv, args.output_csv, args.summary_csv)

    print("Done.")
    print(f"  Rows: {len(normalized):,}")
    print(f"  Columns: {len(normalized.columns):,}")
    print(f"  Language-normalized dataset: {args.output_csv}")
    print(f"  Summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
