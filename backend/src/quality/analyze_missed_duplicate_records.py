"""Analyze likely duplicate records that survived deduplication."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.pipeline.kaggle_merge_common_dataset import (
    is_blank,
    normalize_author_key,
    normalize_doi,
    normalize_title_key,
    normalize_year,
)


PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)

DEFAULT_DEDUPLICATED_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_deduplicated.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "common" / "missed_duplicate_analysis"
DEFAULT_MAX_YEAR_SPAN = 1

DEDUPLICATED_COLUMNS = [
    "source_dataset",
    "source_record_id",
    "doi",
    "title",
    "publication_year",
    "authors",
    "author_names",
    "journal",
    "container_title",
    "url",
]


@dataclass(frozen=True)
class MissedDuplicateAnalysis:
    metrics: dict[str, int]
    summary: pd.DataFrame
    candidate_groups: pd.DataFrame
    source_summary: pd.DataFrame


def not_blank(value: Any) -> bool:
    return not is_blank(value)


def normalized_doi_set(values: Iterable[Any]) -> set[str]:
    return {
        str(doi)
        for value in values
        if not is_blank(doi := normalize_doi(value))
    }


def sample_values(values: Iterable[Any], *, limit: int = 5, max_chars: int = 120) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if is_blank(value):
            continue
        text = str(value).strip()
        if text in seen:
            continue
        seen.add(text)
        output.append(text[:max_chars])
        if len(output) >= limit:
            break
    return " || ".join(output)


def split_source_values(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    for value in values:
        if is_blank(value):
            continue
        for chunk in str(value).split(";"):
            source = chunk.strip()
            if source:
                seen.add(source)
    return sorted(seen)


def doi_state(values: Iterable[Any]) -> str:
    raw_values = list(values)
    normalized = normalized_doi_set(raw_values)
    present_count = sum(not is_blank(normalize_doi(value)) for value in raw_values)
    if not normalized:
        return "all_missing"
    if present_count < len(raw_values):
        return "some_missing"
    if len(normalized) == 1:
        return "same_doi"
    return "different_doi"


def candidate_reason(method: str, state: str) -> str:
    if method == "duplicate_doi_after_dedup":
        return "Same normalized DOI appears in more than one deduplicated row."
    if method == "title_year_first_author":
        return (
            "Same normalized title, publication year, and first author survived "
            f"deduplication with DOI state {state}."
        )
    if method == "title_year":
        return (
            "Same normalized title and publication year survived deduplication "
            f"without enough first-author evidence; DOI state {state}."
        )
    return (
        "Same normalized title and first author survived deduplication with "
        f"publication-year span <= {DEFAULT_MAX_YEAR_SPAN}; DOI state {state}."
    )


def candidate_row(
    candidate_group_number: int,
    method: str,
    confidence: str,
    key: str,
    group: pd.DataFrame,
) -> dict[str, Any]:
    state = doi_state(group["doi"])
    years = sorted(
        {
            int(year)
            for value in group["publication_year"]
            if not is_blank(year := normalize_year(value))
        }
    )
    year_span = years[-1] - years[0] if len(years) > 1 else 0
    return {
        "candidate_group_number": candidate_group_number,
        "review_status": "needs_manual_review",
        "review_method": method,
        "confidence": confidence,
        "candidate_key": key,
        "review_reason": candidate_reason(method, state),
        "doi_state": state,
        "input_record_count": len(group),
        "source_datasets": "; ".join(split_source_values(group["source_dataset"])),
        "source_record_ids": sample_values(group["source_record_id"], limit=8),
        "normalized_dois": "; ".join(sorted(normalized_doi_set(group["doi"]))),
        "titles": sample_values(group["title"]),
        "publication_years": "; ".join(str(year) for year in years),
        "publication_year_span": year_span,
        "authors": sample_values(group["author_names"].where(group["author_names"].map(not_blank), group["authors"])),
        "journals": sample_values(group["journal"].where(group["journal"].map(not_blank), group["container_title"])),
        "urls": sample_values(group["url"], limit=8),
        "input_row_numbers": "; ".join(str(index + 1) for index in group.index),
    }


def add_group_candidates(
    rows: list[dict[str, Any]],
    seen: set[frozenset[int]],
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    method: str,
    confidence: str,
) -> None:
    candidates = frame.dropna(subset=group_columns)
    if candidates.empty:
        return

    for key_values, group in candidates.groupby(group_columns, sort=False, dropna=False):
        if len(group) < 2:
            continue
        index_set = frozenset(int(index) for index in group.index)
        if index_set in seen:
            continue
        seen.add(index_set)
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        key = "|".join(str(value) for value in key_values)
        rows.append(
            candidate_row(
                len(rows) + 1,
                method,
                confidence,
                key,
                group,
            )
        )


def prepare_records(records: pd.DataFrame) -> pd.DataFrame:
    working = records.copy()
    for column in DEDUPLICATED_COLUMNS:
        if column not in working.columns:
            working[column] = pd.NA
    author_source = working["author_names"].where(working["author_names"].map(not_blank), working["authors"])
    working["_normalized_doi"] = working["doi"].map(normalize_doi)
    working["_title_key"] = working["title"].map(normalize_title_key)
    working["_year_key"] = working["publication_year"].map(normalize_year)
    working["_first_author_key"] = author_source.map(normalize_author_key)
    working.loc[working["_normalized_doi"].map(is_blank), "_normalized_doi"] = pd.NA
    working.loc[working["_title_key"].map(is_blank), "_title_key"] = pd.NA
    working.loc[working["_year_key"].map(is_blank), "_year_key"] = pd.NA
    working.loc[working["_first_author_key"].map(is_blank), "_first_author_key"] = pd.NA
    return working


def analyze_missed_duplicates(
    records: pd.DataFrame,
    *,
    max_year_span: int = DEFAULT_MAX_YEAR_SPAN,
) -> MissedDuplicateAnalysis:
    """Find review groups that may represent duplicates missed by prior steps."""

    working = prepare_records(records)
    rows: list[dict[str, Any]] = []
    seen: set[frozenset[int]] = set()

    add_group_candidates(
        rows,
        seen,
        working,
        group_columns=["_normalized_doi"],
        method="duplicate_doi_after_dedup",
        confidence="high",
    )
    add_group_candidates(
        rows,
        seen,
        working,
        group_columns=["_title_key", "_year_key", "_first_author_key"],
        method="title_year_first_author",
        confidence="medium",
    )
    missing_author = working.loc[working["_first_author_key"].map(is_blank)]
    add_group_candidates(
        rows,
        seen,
        missing_author,
        group_columns=["_title_key", "_year_key"],
        method="title_year",
        confidence="low",
    )

    title_author_rows: list[dict[str, Any]] = []
    title_author = working.dropna(subset=["_title_key", "_first_author_key", "_year_key"])
    for key_values, group in title_author.groupby(
        ["_title_key", "_first_author_key"],
        sort=False,
        dropna=False,
    ):
        if len(group) < 2:
            continue
        years = sorted({int(year) for year in group["_year_key"] if not is_blank(year)})
        if len(years) < 2 or years[-1] - years[0] > max_year_span:
            continue
        index_set = frozenset(int(index) for index in group.index)
        if index_set in seen:
            continue
        seen.add(index_set)
        key = "|".join(str(value) for value in key_values)
        title_author_rows.append(
            candidate_row(
                len(rows) + len(title_author_rows) + 1,
                "title_first_author_near_year",
                "low",
                key,
                group,
            )
        )
    rows.extend(title_author_rows)

    candidate_groups = pd.DataFrame(rows)
    if candidate_groups.empty:
        source_summary = pd.DataFrame(columns=["source_datasets", "candidate_groups"])
    else:
        source_summary = (
            candidate_groups["source_datasets"]
            .value_counts()
            .rename_axis("source_datasets")
            .reset_index(name="candidate_groups")
        )

    metrics = {
        "deduplicated_rows_reviewed": len(working),
        "missed_duplicate_candidate_groups": len(candidate_groups),
        "missed_duplicate_candidate_records": (
            int(candidate_groups["input_record_count"].sum()) if not candidate_groups.empty else 0
        ),
        "duplicate_doi_after_dedup_groups": (
            int((candidate_groups["review_method"] == "duplicate_doi_after_dedup").sum())
            if not candidate_groups.empty
            else 0
        ),
        "title_year_first_author_groups": (
            int((candidate_groups["review_method"] == "title_year_first_author").sum())
            if not candidate_groups.empty
            else 0
        ),
        "title_year_groups": (
            int((candidate_groups["review_method"] == "title_year").sum())
            if not candidate_groups.empty
            else 0
        ),
        "title_first_author_near_year_groups": (
            int((candidate_groups["review_method"] == "title_first_author_near_year").sum())
            if not candidate_groups.empty
            else 0
        ),
    }
    summary = pd.DataFrame([{"metric": metric, "value": value} for metric, value in metrics.items()])
    return MissedDuplicateAnalysis(
        metrics=metrics,
        summary=summary,
        candidate_groups=candidate_groups,
        source_summary=source_summary,
    )


def read_deduplicated(path: Path) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0)
    usecols = [column for column in DEDUPLICATED_COLUMNS if column in header.columns]
    return pd.read_csv(path, usecols=usecols, dtype="object", low_memory=False)


def write_outputs(output_dir: Path, analysis: MissedDuplicateAnalysis) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "summary": output_dir / "missed_duplicate_summary.csv",
        "candidate_groups": output_dir / "missed_duplicate_candidate_groups.csv",
        "source_summary": output_dir / "missed_duplicate_source_summary.csv",
    }
    analysis.summary.to_csv(outputs["summary"], index=False)
    analysis.candidate_groups.to_csv(outputs["candidate_groups"], index=False)
    analysis.source_summary.to_csv(outputs["source_summary"], index=False)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze likely duplicate records that survived deduplication."
    )
    parser.add_argument("--deduplicated-csv", type=Path, default=DEFAULT_DEDUPLICATED_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-year-span", type=int, default=DEFAULT_MAX_YEAR_SPAN)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_deduplicated(args.deduplicated_csv)
    analysis = analyze_missed_duplicates(records, max_year_span=args.max_year_span)
    outputs = write_outputs(args.output_dir, analysis)

    print("Missed duplicate analysis complete.")
    for name, path in outputs.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
