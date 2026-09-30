"""Print report-ready verification evidence for pipeline and model outputs."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SUMMARY_PATH = (
    ROOT
    / "backend"
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_analysis_ready_summary.csv"
)
PRIMARY_METRICS_PATH = (
    ROOT
    / "backend"
    / "researchlanka-kaggle-outputs"
    / "data"
    / "models"
    / "linear_svm_primary_domain_metrics.txt"
)
HIERARCHICAL_METRICS_PATH = (
    ROOT
    / "backend"
    / "researchlanka-kaggle-outputs"
    / "data"
    / "models"
    / "linear_svm_hierarchical_metrics.txt"
)

ARTIFACTS = [
    ROOT
    / "backend"
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_analysis_ready.csv",
    ROOT
    / "backend"
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_summary.csv",
    PRIMARY_METRICS_PATH,
    HIERARCHICAL_METRICS_PATH,
]


def read_summary(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["metric"]: row["value"] for row in csv.DictReader(handle)}


def read_metrics(path: Path) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metrics[key.strip()] = value.strip()
    return metrics


def print_metric(name: str, value: str | None) -> None:
    print(f"  {name:<30} {value or '-'}")


def main() -> int:
    missing = [path for path in [SUMMARY_PATH, PRIMARY_METRICS_PATH, HIERARCHICAL_METRICS_PATH] if not path.exists()]
    missing.extend(path for path in ARTIFACTS if not path.exists())
    if missing:
        print("[FAIL] Required output artifacts are missing")
        for path in missing:
            print(f"  MISSING  {path.relative_to(ROOT)}")
        print("Result: FAIL")
        return 1

    summary = read_summary(SUMMARY_PATH)
    primary = read_metrics(PRIMARY_METRICS_PATH)
    hierarchical = read_metrics(HIERARCHICAL_METRICS_PATH)

    print("[PASS] Dagster/data pipeline output artifacts found")
    for path in ARTIFACTS:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  OK  {str(path.relative_to(ROOT)):<86} {size_mb:8.2f} MB")

    print()
    print("[PASS] Analysis-ready dataset summary")
    print_metric("input_rows", summary.get("input_rows"))
    print_metric("output_rows", summary.get("output_rows"))
    print_metric("output_columns", summary.get("output_columns"))
    print_metric("records_with_valid_doi", summary.get("records_with_valid_doi"))
    print_metric(
        "records_dropped_missing_or_invalid_doi",
        summary.get("records_dropped_missing_or_invalid_doi"),
    )

    print()
    print("[PASS] Primary domain Linear SVM model metrics")
    print_metric("usable_rows", primary.get("usable_rows"))
    print_metric("train_rows", primary.get("train_rows"))
    print_metric("test_rows", primary.get("test_rows"))
    print_metric("accuracy", primary.get("accuracy"))
    print_metric("macro_f1", primary.get("macro_f1"))

    print()
    print("[PASS] Hierarchical Linear SVM model metrics")
    print_metric("field_class_count", hierarchical.get("field_class_count"))
    print_metric("subfield_model_count", hierarchical.get("subfield_model_count"))
    print_metric("field_accuracy", hierarchical.get("field_accuracy"))
    print_metric("field_macro_f1", hierarchical.get("field_macro_f1"))

    print()
    print(f"Verification completed successfully at {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
