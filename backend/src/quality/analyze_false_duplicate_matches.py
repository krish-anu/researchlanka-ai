"""Analyze duplicate-candidate false-positive risk.

This script focuses on cases that would be unsafe if non-DOI duplicate
signals were promoted to automatic merge rules. It also audits same-DOI groups
for severe title/year disagreement, since DOI is the current automatic merge
key.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.pipeline.kaggle_merge_common_dataset import (
    is_blank,
    normalize_doi,
    normalize_title_key,
    normalize_year,
)


PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)

DEFAULT_CANDIDATE_PAIRS = PROJECT_ROOT / "notebooks" / "candidate_duplicate_pairs.csv"
DEFAULT_ALL_RECORDS = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_all_records.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "common" / "duplicate_match_analysis"

ALL_RECORD_COLUMNS = [
    "source_dataset",
    "source_record_id",
    "doi",
    "title",
    "publication_year",
]

ARTIFACT_TITLE_RE = (
    r"\b(?:additional file|supplementary|supplemental|figure|fig\.?|table|"
    r"dataset|data set|appendix|annex|image|plate)\b"
)

SEVERE_TITLE_SIMILARITY_THRESHOLD = 0.80
SEVERE_YEAR_SPAN_THRESHOLD = 1


@dataclass(frozen=True)
class CandidatePairAnalysis:
    metrics: dict[str, int]
    summary: pd.DataFrame


@dataclass(frozen=True)
class SameDoiAnalysis:
    metrics: dict[str, int]
    summary: pd.DataFrame
    conflict_groups: pd.DataFrame
    severe_groups: pd.DataFrame
    severe_source_summary: pd.DataFrame


def not_blank(value: Any) -> bool:
    return not is_blank(value)


def normalized_doi_series(values: pd.Series) -> pd.Series:
    return values.map(normalize_doi)


def normalized_title_series(values: pd.Series) -> pd.Series:
    return values.map(normalize_title_key)


def normalized_year_series(values: pd.Series) -> pd.Series:
    return values.map(normalize_year)


def count(mask: pd.Series) -> int:
    return int(mask.fillna(False).sum())


def share(count_value: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count_value / total, 4)


def metric_row(
    metric: str,
    count_value: int,
    total: int,
    interpretation: str,
) -> dict[str, Any]:
    return {
        "metric": metric,
        "count": count_value,
        "share": share(count_value, total),
        "interpretation": interpretation,
    }


def analyze_candidate_pairs(candidate_pairs: pd.DataFrame) -> CandidatePairAnalysis:
    """Summarize false-positive risk signals in candidate duplicate pairs."""

    total = len(candidate_pairs)
    doi1 = normalized_doi_series(candidate_pairs.get("doi1", pd.Series(index=candidate_pairs.index)))
    doi2 = normalized_doi_series(candidate_pairs.get("doi2", pd.Series(index=candidate_pairs.index)))
    title1 = normalized_title_series(
        candidate_pairs.get("title1", pd.Series(index=candidate_pairs.index))
    )
    title2 = normalized_title_series(
        candidate_pairs.get("title2", pd.Series(index=candidate_pairs.index))
    )
    year1 = normalized_year_series(
        candidate_pairs.get("year1", pd.Series(index=candidate_pairs.index))
    )
    year2 = normalized_year_series(
        candidate_pairs.get("year2", pd.Series(index=candidate_pairs.index))
    )
    score = pd.to_numeric(
        candidate_pairs.get("final_score", pd.Series(pd.NA, index=candidate_pairs.index)),
        errors="coerce",
    )

    doi1_present = doi1.map(not_blank)
    doi2_present = doi2.map(not_blank)
    both_doi = doi1_present & doi2_present
    one_doi_missing = doi1_present ^ doi2_present
    neither_doi = ~doi1_present & ~doi2_present
    different_doi = both_doi & (doi1 != doi2)

    same_title = title1.map(not_blank) & title2.map(not_blank) & (title1 == title2)
    different_title = title1.map(not_blank) & title2.map(not_blank) & (title1 != title2)
    same_year = year1.map(not_blank) & year2.map(not_blank) & (year1 == year2)

    title_text_1 = candidate_pairs.get("title1", pd.Series(index=candidate_pairs.index))
    title_text_2 = candidate_pairs.get("title2", pd.Series(index=candidate_pairs.index))
    artifact_title = (
        title_text_1.fillna("").astype(str).str.contains(ARTIFACT_TITLE_RE, case=False, regex=True)
        | title_text_2.fillna("").astype(str).str.contains(
            ARTIFACT_TITLE_RE,
            case=False,
            regex=True,
        )
    )
    source1 = candidate_pairs.get("source1", pd.Series(index=candidate_pairs.index))
    source2 = candidate_pairs.get("source2", pd.Series(index=candidate_pairs.index))
    repository_involved = (
        source1.fillna("").astype(str).str.contains("repositories_combined", regex=False)
        | source2.fillna("").astype(str).str.contains("repositories_combined", regex=False)
    )
    same_source_label = source1.fillna("").astype(str) == source2.fillna("").astype(str)

    metrics = {
        "candidate_pair_rows": total,
        "both_doi": count(both_doi),
        "different_doi_when_both_present": count(different_doi),
        "exact_title_same_year_different_doi": count(same_title & same_year & different_doi),
        "non_identical_normalized_titles": count(different_title),
        "artifact_title": count(artifact_title),
        "one_doi_missing": count(one_doi_missing),
        "neither_doi_present": count(neither_doi),
        "repository_involved_pair": count(repository_involved),
        "same_source_label_pair": count(same_source_label),
        "score_at_least_99_with_different_doi": count((score >= 99) & different_doi),
        "score_at_least_95_with_one_or_no_doi": count((score >= 95) & ~both_doi),
    }

    rows = [
        metric_row(
            "both_doi_different",
            metrics["different_doi_when_both_present"],
            total,
            "Both records have DOI values, but the normalized DOI values differ.",
        ),
        metric_row(
            "exact_title_same_year_different_doi",
            metrics["exact_title_same_year_different_doi"],
            total,
            "Perfect title/year agreement is not sufficient for automatic merging.",
        ),
        metric_row(
            "non_identical_normalized_titles",
            metrics["non_identical_normalized_titles"],
            total,
            "Fuzzy candidate scoring includes title variants that require review.",
        ),
        metric_row(
            "artifact_title",
            metrics["artifact_title"],
            total,
            "Artifacts such as figures, tables, datasets, and supplements can be distinct records.",
        ),
        metric_row(
            "one_doi_missing",
            metrics["one_doi_missing"],
            total,
            "One side lacks DOI evidence, so identity cannot be confirmed automatically.",
        ),
        metric_row(
            "neither_doi_present",
            metrics["neither_doi_present"],
            total,
            "Neither side has DOI evidence; keep as manual-review only.",
        ),
        metric_row(
            "repository_involved_pair",
            metrics["repository_involved_pair"],
            total,
            "Repository metadata is a major source of duplicate uncertainty.",
        ),
        metric_row(
            "same_source_label_pair",
            metrics["same_source_label_pair"],
            total,
            "Repeated records inside the same source label need source-specific review.",
        ),
        metric_row(
            "score_at_least_99_with_different_doi",
            metrics["score_at_least_99_with_different_doi"],
            total,
            "Very high fuzzy scores still include DOI-disagreeing candidates.",
        ),
        metric_row(
            "score_at_least_95_with_one_or_no_doi",
            metrics["score_at_least_95_with_one_or_no_doi"],
            total,
            "Score thresholds alone would over-merge DOI-poor records.",
        ),
    ]

    return CandidatePairAnalysis(metrics=metrics, summary=pd.DataFrame(rows))


def split_source_values(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if is_blank(value):
            continue
        for chunk in str(value).split(";"):
            source = chunk.strip()
            if source and source not in seen:
                seen.add(source)
                output.append(source)

    return sorted(output)


def min_pairwise_similarity(values: Iterable[Any]) -> float:
    normalized = sorted({str(value) for value in values if not is_blank(value)})
    if len(normalized) < 2:
        return 1.0

    scores = [
        SequenceMatcher(None, left, right).ratio()
        for index, left in enumerate(normalized)
        for right in normalized[index + 1 :]
    ]
    return min(scores) if scores else 1.0


def sample_values(values: Iterable[Any], *, limit: int = 5, max_chars: int = 95) -> str:
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


def analyze_same_doi_groups(records: pd.DataFrame) -> SameDoiAnalysis:
    """Find same-DOI groups with title or publication-year disagreement."""

    working = records.copy()
    working["_normalized_doi"] = normalized_doi_series(working["doi"])
    working["_title_key"] = normalized_title_series(working["title"])
    working["_year_key"] = normalized_year_series(working["publication_year"])

    rows_with_doi = working.loc[working["_normalized_doi"].map(not_blank)].copy()
    doi_counts = rows_with_doi["_normalized_doi"].value_counts()
    duplicate_dois = doi_counts.loc[doi_counts > 1]
    duplicate_rows = rows_with_doi.loc[rows_with_doi["_normalized_doi"].isin(duplicate_dois.index)]

    conflict_rows: list[dict[str, Any]] = []
    for doi, group in duplicate_rows.groupby("_normalized_doi", sort=False):
        title_keys = [value for value in group["_title_key"] if not is_blank(value)]
        title_variant_count = len({str(value) for value in title_keys})
        years = sorted({int(value) for value in group["_year_key"] if not is_blank(value)})
        year_variant_count = len(years)

        if title_variant_count <= 1 and year_variant_count <= 1:
            continue

        min_title_similarity = min_pairwise_similarity(title_keys)
        year_span = max(years) - min(years) if len(years) > 1 else 0
        severe = (
            min_title_similarity < SEVERE_TITLE_SIMILARITY_THRESHOLD
            or year_span > SEVERE_YEAR_SPAN_THRESHOLD
        )
        conflict_rows.append(
            {
                "doi": doi,
                "input_record_count": len(group),
                "source_combination": "; ".join(split_source_values(group["source_dataset"])),
                "title_variant_count": title_variant_count,
                "year_variant_count": year_variant_count,
                "min_title_similarity": round(min_title_similarity, 4),
                "publication_year_span": year_span,
                "publication_years": "; ".join(str(year) for year in years),
                "severe_conflict": severe,
                "sample_titles": sample_values(group["title"]),
                "source_record_ids": sample_values(
                    group["source_record_id"],
                    limit=8,
                    max_chars=120,
                ),
            }
        )

    conflict_groups = pd.DataFrame(conflict_rows)
    if conflict_groups.empty:
        severe_groups = conflict_groups.copy()
        severe_source_summary = pd.DataFrame(columns=["source_combination", "severe_groups"])
    else:
        severe_groups = conflict_groups.loc[conflict_groups["severe_conflict"]].copy()
        severe_source_summary = (
            severe_groups["source_combination"]
            .value_counts()
            .rename_axis("source_combination")
            .reset_index(name="severe_groups")
        )

    metrics = {
        "all_rows": len(working),
        "rows_with_doi": len(rows_with_doi),
        "duplicate_doi_groups": int(len(duplicate_dois)),
        "rows_in_duplicate_doi_groups": int(duplicate_dois.sum()),
        "conflicting_doi_groups": len(conflict_groups),
        "title_conflict_groups": (
            int((conflict_groups["title_variant_count"] > 1).sum())
            if not conflict_groups.empty
            else 0
        ),
        "year_conflict_groups": (
            int((conflict_groups["year_variant_count"] > 1).sum())
            if not conflict_groups.empty
            else 0
        ),
        "title_similarity_below_095": (
            int((conflict_groups["min_title_similarity"] < 0.95).sum())
            if not conflict_groups.empty
            else 0
        ),
        "title_similarity_below_090": (
            int((conflict_groups["min_title_similarity"] < 0.90).sum())
            if not conflict_groups.empty
            else 0
        ),
        "title_similarity_below_080": (
            int(
                (
                    conflict_groups["min_title_similarity"]
                    < SEVERE_TITLE_SIMILARITY_THRESHOLD
                ).sum()
            )
            if not conflict_groups.empty
            else 0
        ),
        "year_span_greater_than_0": (
            int((conflict_groups["publication_year_span"] > 0).sum())
            if not conflict_groups.empty
            else 0
        ),
        "year_span_greater_than_1": (
            int(
                (
                    conflict_groups["publication_year_span"]
                    > SEVERE_YEAR_SPAN_THRESHOLD
                ).sum()
            )
            if not conflict_groups.empty
            else 0
        ),
        "severe_same_doi_conflict_groups": len(severe_groups),
    }

    summary = pd.DataFrame(
        [{"metric": metric, "value": value} for metric, value in metrics.items()]
    )
    return SameDoiAnalysis(
        metrics=metrics,
        summary=summary,
        conflict_groups=conflict_groups,
        severe_groups=severe_groups,
        severe_source_summary=severe_source_summary,
    )


def read_all_records(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, usecols=ALL_RECORD_COLUMNS, dtype="object", low_memory=False)


def write_outputs(
    *,
    output_dir: Path,
    candidate_analysis: CandidatePairAnalysis,
    same_doi_analysis: SameDoiAnalysis | None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "candidate_risk_summary": output_dir / "false_duplicate_candidate_risk_summary.csv",
    }
    candidate_analysis.summary.to_csv(outputs["candidate_risk_summary"], index=False)

    if same_doi_analysis is not None:
        outputs.update(
            {
                "same_doi_summary": output_dir / "same_doi_conflict_summary.csv",
                "same_doi_conflicts": output_dir / "same_doi_conflict_groups.csv",
                "severe_same_doi_conflicts": output_dir / "severe_same_doi_conflicts.csv",
                "severe_source_summary": output_dir / "severe_same_doi_source_summary.csv",
            }
        )
        same_doi_analysis.summary.to_csv(outputs["same_doi_summary"], index=False)
        same_doi_analysis.conflict_groups.to_csv(outputs["same_doi_conflicts"], index=False)
        same_doi_analysis.severe_groups.to_csv(
            outputs["severe_same_doi_conflicts"],
            index=False,
        )
        same_doi_analysis.severe_source_summary.to_csv(
            outputs["severe_source_summary"],
            index=False,
        )

    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze false-positive risk in duplicate candidate matches."
    )
    parser.add_argument(
        "--candidate-pairs",
        type=Path,
        default=DEFAULT_CANDIDATE_PAIRS,
        help="CSV containing candidate duplicate pairs.",
    )
    parser.add_argument(
        "--all-records",
        type=Path,
        default=DEFAULT_ALL_RECORDS,
        help="Common all-records CSV used to audit same-DOI conflicts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for analysis CSV outputs.",
    )
    parser.add_argument(
        "--skip-same-doi-scan",
        action="store_true",
        help="Only analyze candidate-pair risk signals.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate_pairs = pd.read_csv(args.candidate_pairs)
    candidate_analysis = analyze_candidate_pairs(candidate_pairs)

    same_doi_analysis = None
    if not args.skip_same_doi_scan:
        same_doi_analysis = analyze_same_doi_groups(read_all_records(args.all_records))

    outputs = write_outputs(
        output_dir=args.output_dir,
        candidate_analysis=candidate_analysis,
        same_doi_analysis=same_doi_analysis,
    )

    print("False duplicate match analysis complete.")
    for name, path in outputs.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
