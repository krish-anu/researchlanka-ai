"""Generate compact chart data for the frontend dashboard pages."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_ALL_RECORDS_CSV = BACKEND_ROOT / "data" / "processed" / "common" / "common_publications_all_records.csv"
DEFAULT_FINAL_CSV = BACKEND_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_MODEL_COMPARISON_CSV = BACKEND_ROOT / "data" / "models" / "classification_comparison" / "model_comparison.csv"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "frontend" / "src" / "data" / "datasetCharts.json"

SOURCE_LABELS = {
    "openalex": "OpenAlex",
    "crossref": "Crossref",
    "repositories_combined": "Repositories",
    "sljol": "SLJOL",
}


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_key_text(value: Any) -> str:
    text = clean_text(value).casefold()
    output: list[str] = []
    previous_was_space = True
    for character in text:
        category_group = unicodedata.category(character)[0]
        if category_group in {"L", "M", "N"}:
            output.append(character)
            previous_was_space = False
        elif not previous_was_space:
            output.append(" ")
            previous_was_space = True
    return "".join(output).strip()


def normalize_doi(value: Any) -> str:
    text = clean_text(value).casefold()
    if not text:
        return ""
    match = re.search(r"10\.\d{4,9}/[^\s\"'<>;]+", text, flags=re.IGNORECASE)
    if match:
        text = match.group(0)
    text = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(" ", "").rstrip(".,;:)]}")
    return text if re.match(r"^10\.\d{4,9}/", text) else ""


def source_label(value: str) -> str:
    parts = [SOURCE_LABELS.get(part, part) for part in value.split("; ") if part]
    return " + ".join(parts) if parts else "Unknown"


def read_csv_rows(path: Path):
    raise_csv_field_limit()
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def final_dataset_charts(path: Path) -> tuple[list[dict[str, int | str]], list[dict[str, int | str]]]:
    by_year: Counter[str] = Counter()
    source_combinations: Counter[str] = Counter()
    for row in read_csv_rows(path):
        year = clean_text(row.get("publication_year"))
        if year.isdigit():
            by_year[year] += 1
        source_combinations[clean_text(row.get("source_dataset")) or "unknown"] += 1

    publications_by_year = [
        {"label": year, "value": count}
        for year, count in sorted(by_year.items(), key=lambda item: int(item[0]))
    ]
    multi_source = [
        {"label": source_label(source), "value": count}
        for source, count in source_combinations.most_common(12)
    ]
    return publications_by_year, multi_source


def source_and_dedup_charts(path: Path) -> tuple[list[dict[str, int | str]], list[dict[str, int | str]]]:
    main_sources: Counter[str] = Counter()
    title_year_dois: dict[tuple[str, str], set[str]] = defaultdict(set)
    doi_details: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for row in read_csv_rows(path):
        source = clean_text(row.get("source_dataset")) or "unknown"
        main_sources[source] += 1

        doi = normalize_doi(row.get("doi"))
        title = normalize_key_text(row.get("title"))
        year = clean_text(row.get("publication_year"))
        if title and year and doi:
            title_year_dois[(title, year)].add(doi)
        if doi:
            doi_details[doi].add((title, year))

    source_counts = [
        {"label": SOURCE_LABELS.get(source, source), "value": main_sources.get(source, 0)}
        for source in ("repositories_combined", "openalex", "crossref", "sljol")
    ]
    dedup_counts = [
        {
            "label": "Exact title + year, different DOIs",
            "value": sum(1 for dois in title_year_dois.values() if len(dois) > 1),
        },
        {
            "label": "Same DOI, title/year differs",
            "value": sum(1 for details in doi_details.values() if len(details) > 1),
        },
    ]
    return source_counts, dedup_counts


def model_comparison(path: Path) -> list[dict[str, float | str]]:
    labels = {
        "linear_svm": "Linear SVM",
        "logistic_regression": "Logistic Regression",
        "multinomial_nb": "Multinomial NB",
    }
    rows: list[dict[str, float | str]] = []
    for row in read_csv_rows(path):
        model = clean_text(row.get("model_family"))
        rows.append(
            {
                "label": labels.get(model, model),
                "accuracy": round(float(row.get("accuracy") or 0) * 100, 2),
                "macroF1": round(float(row.get("macro_f1") or 0) * 100, 2),
                "weightedF1": round(float(row.get("weighted_f1") or 0) * 100, 2),
            }
        )
    return rows


def generate_snapshot(
    *,
    all_records_csv: Path,
    final_csv: Path,
    model_comparison_csv: Path,
    output_json: Path,
) -> dict[str, Any]:
    publications_by_year, multi_source = final_dataset_charts(final_csv)
    main_sources, dedup = source_and_dedup_charts(all_records_csv)
    snapshot = {
        "publicationsByYear": publications_by_year,
        "mainSources": main_sources,
        "multiSourceCombinations": multi_source,
        "deduplication": dedup,
        "modelComparison": model_comparison(model_comparison_csv),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate frontend chart JSON from pipeline outputs.")
    parser.add_argument("--all-records-csv", type=Path, default=DEFAULT_ALL_RECORDS_CSV)
    parser.add_argument("--final-csv", type=Path, default=DEFAULT_FINAL_CSV)
    parser.add_argument("--model-comparison-csv", type=Path, default=DEFAULT_MODEL_COMPARISON_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = generate_snapshot(
        all_records_csv=args.all_records_csv,
        final_csv=args.final_csv,
        model_comparison_csv=args.model_comparison_csv,
        output_json=args.output_json,
    )
    print("Generated chart snapshot.")
    print(f"  Output: {args.output_json}")
    for key, value in snapshot.items():
        print(f"  {key}: {len(value):,} rows")


if __name__ == "__main__":
    main()
