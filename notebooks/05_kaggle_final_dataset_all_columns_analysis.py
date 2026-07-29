"""Kaggle notebook script: analyze every column in the current final dataset.

Copy this file into a Kaggle notebook cell-by-cell, or upload it as a Kaggle
script notebook. It auto-detects the latest final dataset file from Kaggle
inputs or from the local project folder.
"""

# %% [markdown]
# # Final Dataset: All Column Analysis
#
# This notebook profiles every column in the current ResearchLanka final dataset.
# It creates:
#
# - dataset overview
# - missing-value profile for every column
# - distinct-value profile for every column
# - top values for every column
# - numeric/date/year checks
# - multi-value column checks
# - source/type/language summary tables
# - CSV reports in the Kaggle working directory

# %%
from pathlib import Path
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

try:
    from IPython.display import display
except ImportError:  # pragma: no cover - only used outside notebooks
    display = print


pd.set_option("display.max_columns", 120)
pd.set_option("display.max_rows", 200)
pd.set_option("display.max_colwidth", 120)
sns.set_theme(style="whitegrid")


# %% [markdown]
# ## 1. Find And Load Dataset
#
# On Kaggle, click **Add Input** and attach your dataset. This notebook searches
# `/kaggle/input` automatically. Locally, it searches `data/processed/common`.

# %%
CANDIDATE_FILENAMES = [
    "common_publications_final_2016_2026_language_normalized.csv",
    "common_publications_final_2016_2026.csv",
    "common_publications_columns_filtered.csv",
    "common_publications_final.csv",
]


def find_dataset() -> Path:
    search_roots = [
        Path("/kaggle/input"),
        Path("/kaggle/working"),
        Path("data/processed/common"),
        Path("../input"),
    ]

    for filename in CANDIDATE_FILENAMES:
        for root in search_roots:
            if not root.exists():
                continue
            matches = sorted(root.rglob(filename))
            if matches:
                return matches[0]

    raise FileNotFoundError(
        "No final dataset found. Add the CSV to Kaggle input or set DATASET_PATH manually."
    )


DATASET_PATH = find_dataset()
OUTPUT_DIR = Path("/kaggle/working/final_dataset_column_analysis")
if not Path("/kaggle/working").exists():
    OUTPUT_DIR = Path("data/reports/final_dataset_column_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Dataset: {DATASET_PATH}")
print(f"Reports: {OUTPUT_DIR}")


# %%
def load_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype="object", low_memory=False)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported dataset format: {path.suffix}")


df = load_dataset(DATASET_PATH)
df.columns = [str(column).strip() for column in df.columns]

print("Shape:", df.shape)
display(df.head(3))


# %% [markdown]
# ## 2. Helpers

# %%
BLANK_STRINGS = {"", "nan", "none", "null", "na", "n/a", "[]", "{}"}
MULTIVALUE_SEPARATOR = ";"


def clean_text(value):
    if pd.isna(value):
        return ""
    return " ".join(str(value).split()).strip()


def nonblank_mask(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.notna() & ~normalized.isin(BLANK_STRINGS)


def example_values(series: pd.Series, limit: int = 3) -> str:
    values = []
    for value in series[nonblank_mask(series)].drop_duplicates().head(limit):
        text = clean_text(value)
        if len(text) > 80:
            text = text[:77] + "..."
        values.append(text)
    return " | ".join(values)


def infer_column_role(column: str) -> str:
    lower = column.lower()
    if lower in {"publication_year", "author_count", "citation_count", "reference_count"}:
        return "numeric"
    if lower.endswith("_count") or "difference" in lower:
        return "numeric"
    if "date" in lower or lower.endswith("datestamp"):
        return "date"
    if lower in {"doi", "openalex_id", "url", "pdf_url", "issn", "issn_l"}:
        return "identifier"
    if lower in {"title", "abstract", "keywords"}:
        return "text"
    if lower in {"authors", "institutions", "countries", "concepts", "topics"}:
        return "multi_value"
    if lower in {"type", "source_type", "language", "license", "oa_status", "is_oa"}:
        return "category"
    return "metadata"


# %% [markdown]
# ## 3. Dataset Overview

# %%
overview = pd.DataFrame(
    [
        {"metric": "dataset_path", "value": str(DATASET_PATH)},
        {"metric": "rows", "value": len(df)},
        {"metric": "columns", "value": len(df.columns)},
        {"metric": "memory_mb", "value": round(df.memory_usage(deep=True).sum() / 1024**2, 2)},
        {"metric": "duplicate_doi_values", "value": int(df["doi"].duplicated().sum()) if "doi" in df else None},
        {
            "metric": "duplicate_title_year_values",
            "value": int(df.duplicated(["title", "publication_year"]).sum())
            if {"title", "publication_year"}.issubset(df.columns)
            else None,
        },
    ]
)
display(overview)
overview.to_csv(OUTPUT_DIR / "dataset_overview.csv", index=False)


# %% [markdown]
# ## 4. Column Profile For Every Column

# %%
profile_rows = []
for position, column in enumerate(df.columns, start=1):
    series = df[column]
    present = nonblank_mask(series)
    present_values = series[present].astype(str).str.strip()
    string_lengths = present_values.str.len()
    multivalue_count = (
        int(present_values.str.contains(MULTIVALUE_SEPARATOR, regex=False).sum())
        if len(present_values)
        else 0
    )

    profile_rows.append(
        {
            "position": position,
            "column": column,
            "role": infer_column_role(column),
            "present_rows": int(present.sum()),
            "missing_rows": int((~present).sum()),
            "coverage_pct": round(float(present.mean() * 100), 2),
            "missing_pct": round(float((~present).mean() * 100), 2),
            "distinct_values": int(present_values.nunique(dropna=True)),
            "multivalue_rows": multivalue_count,
            "multivalue_present_pct": round(multivalue_count / len(present_values) * 100, 2)
            if len(present_values)
            else 0.0,
            "min_length": int(string_lengths.min()) if len(string_lengths) else 0,
            "max_length": int(string_lengths.max()) if len(string_lengths) else 0,
            "examples": example_values(series),
        }
    )

column_profile = pd.DataFrame(profile_rows)
display(column_profile)
column_profile.to_csv(OUTPUT_DIR / "column_profile.csv", index=False)


# %% [markdown]
# ## 5. Missingness Plot

# %%
plot_df = column_profile.sort_values("missing_pct", ascending=False)
plt.figure(figsize=(12, max(8, len(plot_df) * 0.22)))
sns.barplot(data=plot_df, y="column", x="missing_pct", hue="role", dodge=False)
plt.title("Missing Percentage By Column")
plt.xlabel("Missing %")
plt.ylabel("")
plt.legend(loc="lower right")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "missing_percentage_by_column.png", dpi=160)
plt.show()


# %% [markdown]
# ## 6. Top Values For Every Column

# %%
top_value_rows = []
for column in df.columns:
    series = df[column].copy()
    values = series.astype("string").str.strip()
    values = values.mask(values.str.lower().isin(BLANK_STRINGS), pd.NA)
    counts = values.value_counts(dropna=True).head(20)
    for rank, (value, count) in enumerate(counts.items(), start=1):
        top_value_rows.append(
            {
                "column": column,
                "rank": rank,
                "value": value,
                "rows": int(count),
                "pct_of_dataset": round(count / len(df) * 100, 3),
            }
        )

top_values = pd.DataFrame(top_value_rows)
display(top_values.head(100))
top_values.to_csv(OUTPUT_DIR / "top_values_by_column.csv", index=False)


# %% [markdown]
# ## 7. Numeric Column Checks

# %%
numeric_candidate_columns = [
    column
    for column in df.columns
    if infer_column_role(column) == "numeric" or column in {"publication_year", "author_count"}
]

numeric_rows = []
for column in numeric_candidate_columns:
    numeric = pd.to_numeric(df[column], errors="coerce")
    numeric_rows.append(
        {
            "column": column,
            "numeric_rows": int(numeric.notna().sum()),
            "non_numeric_or_missing_rows": int(numeric.isna().sum()),
            "min": numeric.min(),
            "median": numeric.median(),
            "mean": numeric.mean(),
            "max": numeric.max(),
        }
    )

numeric_profile = pd.DataFrame(numeric_rows)
display(numeric_profile)
numeric_profile.to_csv(OUTPUT_DIR / "numeric_profile.csv", index=False)


# %% [markdown]
# ## 8. Year Analysis

# %%
if "publication_year" in df.columns:
    years = pd.to_numeric(df["publication_year"], errors="coerce")
    year_summary = pd.DataFrame(
        [
            {"metric": "min_year", "value": years.min()},
            {"metric": "max_year", "value": years.max()},
            {"metric": "missing_or_invalid_year", "value": int(years.isna().sum())},
            {"metric": "before_2016", "value": int((years < 2016).sum())},
            {"metric": "after_2026", "value": int((years > 2026).sum())},
        ]
    )
    display(year_summary)
    year_summary.to_csv(OUTPUT_DIR / "year_summary.csv", index=False)

    year_counts = years.dropna().astype(int).value_counts().sort_index().reset_index()
    year_counts.columns = ["publication_year", "rows"]
    display(year_counts)
    year_counts.to_csv(OUTPUT_DIR / "year_counts.csv", index=False)

    plt.figure(figsize=(12, 5))
    sns.barplot(data=year_counts, x="publication_year", y="rows", color="#4C78A8")
    plt.xticks(rotation=45)
    plt.title("Publication Rows By Year")
    plt.xlabel("Publication year")
    plt.ylabel("Rows")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "publication_rows_by_year.png", dpi=160)
    plt.show()


# %% [markdown]
# ## 9. Important Category Distributions

# %%
category_columns = [
    column
    for column in [
        "type",
        "source_type",
        "language",
        "license",
        "oa_status",
        "is_oa",
        "primary_domain",
        "primary_field",
        "source_dataset",
    ]
    if column in df.columns
]

for column in category_columns:
    counts = (
        df[column]
        .astype("string")
        .str.strip()
        .mask(lambda value: value.str.lower().isin(BLANK_STRINGS), pd.NA)
        .fillna("unknown")
        .value_counts()
        .head(30)
        .reset_index()
    )
    counts.columns = [column, "rows"]
    counts["pct"] = (counts["rows"] / len(df) * 100).round(2)
    display(counts)
    counts.to_csv(OUTPUT_DIR / f"{column}_counts.csv", index=False)

    plt.figure(figsize=(10, max(4, min(10, len(counts) * 0.3))))
    sns.barplot(data=counts, y=column, x="rows", color="#59A14F")
    plt.title(f"Top {column} Values")
    plt.xlabel("Rows")
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"{column}_top_values.png", dpi=160)
    plt.show()


# %% [markdown]
# ## 10. Multi-Value Column Analysis

# %%
multi_value_columns = [
    "source_dataset",
    "authors",
    "keywords",
    "author_affiliations",
    "author_orcids",
    "sri_lankan_authors",
    "contributors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "issn",
    "concepts",
    "topics",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "source_set_specs",
    "raw_identifiers",
]
multi_value_columns = [column for column in multi_value_columns if column in df.columns]

multi_rows = []
for column in multi_value_columns:
    values = df[column][nonblank_mask(df[column])].astype(str)
    item_counts = values.map(lambda value: len([item for item in value.split(";") if item.strip()]))
    multi_rows.append(
        {
            "column": column,
            "present_rows": int(len(values)),
            "rows_with_multiple_values": int((item_counts > 1).sum()),
            "multi_value_present_pct": round((item_counts > 1).mean() * 100, 2)
            if len(item_counts)
            else 0,
            "mean_items_per_present_row": round(item_counts.mean(), 2) if len(item_counts) else 0,
            "max_items_in_one_row": int(item_counts.max()) if len(item_counts) else 0,
        }
    )

multi_value_profile = pd.DataFrame(multi_rows)
display(multi_value_profile)
multi_value_profile.to_csv(OUTPUT_DIR / "multi_value_profile.csv", index=False)


# %% [markdown]
# ## 11. Coverage By Source Type

# %%
if "source_type" in df.columns:
    coverage_rows = []
    for source_type, group in df.groupby(df["source_type"].fillna("unknown")):
        for column in df.columns:
            coverage_rows.append(
                {
                    "source_type": source_type,
                    "column": column,
                    "rows": len(group),
                    "present_rows": int(nonblank_mask(group[column]).sum()),
                    "coverage_pct": round(nonblank_mask(group[column]).mean() * 100, 2),
                }
            )

    coverage_by_source_type = pd.DataFrame(coverage_rows)
    display(coverage_by_source_type.head(100))
    coverage_by_source_type.to_csv(OUTPUT_DIR / "coverage_by_source_type.csv", index=False)


# %% [markdown]
# ## 12. Quality Flags

# %%
quality = {}
if "title" in df.columns:
    quality["missing_title"] = int((~nonblank_mask(df["title"])).sum())
if "doi" in df.columns:
    doi_present = nonblank_mask(df["doi"])
    quality["doi_present"] = int(doi_present.sum())
    quality["duplicate_doi_rows"] = int(df.loc[doi_present, "doi"].duplicated().sum())
if {"title", "publication_year"}.issubset(df.columns):
    title_year_present = nonblank_mask(df["title"]) & nonblank_mask(df["publication_year"])
    quality["duplicate_title_year_rows"] = int(
        df.loc[title_year_present].duplicated(["title", "publication_year"]).sum()
    )
if "abstract" in df.columns:
    quality["missing_abstract"] = int((~nonblank_mask(df["abstract"])).sum())
if "language" in df.columns:
    quality["unknown_language"] = int(df["language"].fillna("").astype(str).str.strip().eq("unknown").sum())

quality_flags = pd.DataFrame([{"metric": key, "value": value} for key, value in quality.items()])
display(quality_flags)
quality_flags.to_csv(OUTPUT_DIR / "quality_flags.csv", index=False)


# %% [markdown]
# ## 13. Report Files

# %%
report_files = sorted(OUTPUT_DIR.glob("*"))
display(pd.DataFrame({"report_file": [str(path) for path in report_files]}))
print(f"Saved {len(report_files)} report files to {OUTPUT_DIR}")
