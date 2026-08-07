"""Create reproducible train/validation/test datasets for publication models."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from src.modeling.artifacts import SavedArtifact, file_sha256, write_csv_artifact, write_json_artifact
from src.utils.doi import is_valid_doi, normalize_doi


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_analysis_ready.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "modeling" / "publication_classifier"
DEFAULT_LABEL_COLUMN = "primary_domain"
DEFAULT_TEXT_COLUMNS = ("title", "abstract", "keywords")
DEFAULT_TRAIN_RATIO = 0.70
DEFAULT_VALIDATION_RATIO = 0.15
DEFAULT_TEST_RATIO = 0.15
DEFAULT_RANDOM_STATE = 42
DEFAULT_MIN_CLASS_COUNT = 20
SOURCE_ROW_COLUMN = "source_row"
SPLIT_COLUMN = "split"
PUBLICATION_GROUP_COLUMN = "__publication_group_key"
PUBLICATION_GROUP_LABEL_COLUMN = "__publication_group_label"
PUBLICATION_GROUP_ORDER_COLUMN = "__publication_group_order"
TITLE_IDENTITY_MIN_LENGTH = 16
SUMMARY_FIELDNAMES = ["split", "label", "count", "split_rows", "split_fraction"]
BLANK_VALUES = {"", "nan", "none", "null", "na", "n/a"}
PUBLICATION_YEAR_COLUMNS = ("publication_year", "publication_date", "year", "published_date")
EXACT_IDENTIFIER_COLUMNS = ("openalex_id",)
URL_IDENTIFIER_COLUMNS = ("url", "pdf_url")
IDENTITY_TEXT_RE = re.compile(r"[^\w\s]")
WHITESPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")


@dataclass(frozen=True)
class DatasetSplitConfig:
    """Configuration for one reproducible dataset split run."""

    input_path: Path = DEFAULT_INPUT
    output_dir: Path = DEFAULT_OUTPUT_DIR
    label_column: str = DEFAULT_LABEL_COLUMN
    text_columns: tuple[str, ...] = DEFAULT_TEXT_COLUMNS
    train_ratio: float = DEFAULT_TRAIN_RATIO
    validation_ratio: float = DEFAULT_VALIDATION_RATIO
    test_ratio: float = DEFAULT_TEST_RATIO
    random_state: int = DEFAULT_RANDOM_STATE
    min_class_count: int = DEFAULT_MIN_CLASS_COUNT
    require_text: bool = True
    max_rows: int | None = None


@dataclass(frozen=True)
class DatasetSplitResult:
    """Paths and row counts produced by one dataset split run."""

    train_output: Path
    validation_output: Path
    test_output: Path
    summary_output: Path
    manifest_output: Path
    input_rows: int
    usable_rows: int
    dropped_rows: int
    train_rows: int
    validation_rows: int
    test_rows: int
    class_count: int


def parse_text_columns(value: str) -> tuple[str, ...]:
    columns = tuple(column.strip() for column in value.split(",") if column.strip())
    if not columns:
        raise argparse.ArgumentTypeError("at least one text column is required")
    return columns


def validate_config(config: DatasetSplitConfig) -> None:
    ratios = [config.train_ratio, config.validation_ratio, config.test_ratio]
    if any(ratio <= 0 for ratio in ratios):
        raise ValueError("train, validation, and test ratios must all be positive")
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("train, validation, and test ratios must sum to 1.0")
    if config.min_class_count < 1:
        raise ValueError("min_class_count must be at least 1")
    if config.max_rows is not None and config.max_rows < 1:
        raise ValueError("max_rows must be at least 1 when provided")
    if config.require_text and not config.text_columns:
        raise ValueError("at least one text column is required when require_text is true")


def json_ready_dataclass(value: object) -> dict[str, Any]:
    data = asdict(value)
    for key, item in data.items():
        if isinstance(item, Path):
            data[key] = str(item)
        elif isinstance(item, tuple):
            data[key] = list(item)
    return data


def required_columns(config: DatasetSplitConfig) -> list[str]:
    columns = [config.label_column]
    if config.require_text:
        columns.extend(config.text_columns)
    return list(dict.fromkeys(columns))


def add_source_row(frame: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    source_row_column = SOURCE_ROW_COLUMN
    if source_row_column in frame.columns:
        source_row_column = "split_source_row"

    frame = frame.copy()
    frame.insert(0, source_row_column, range(len(frame)))
    return frame, source_row_column


def combined_text(frame: pd.DataFrame, text_columns: tuple[str, ...]) -> pd.Series:
    text = frame[list(text_columns)].fillna("").astype(str).agg(" ".join, axis=1)
    return text.str.replace(r"\s+", " ", regex=True).str.strip()


def clean_identity_value(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    if text.casefold() in BLANK_VALUES:
        return None
    return text


def normalize_identity_text(value: Any) -> str | None:
    text = clean_identity_value(value)
    if text is None:
        return None

    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = IDENTITY_TEXT_RE.sub(" ", normalized.casefold())
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized or None


def normalize_identifier_value(value: Any) -> str | None:
    text = clean_identity_value(value)
    if text is None:
        return None
    return text.casefold().rstrip(".,;:)]}") or None


def publication_year_key(row: pd.Series) -> str | None:
    for column in PUBLICATION_YEAR_COLUMNS:
        if column not in row.index:
            continue
        text = clean_identity_value(row[column])
        if text is None:
            continue
        if match := YEAR_RE.search(text):
            return match.group(1)
    return None


def publication_identity_tokens(row: pd.Series) -> list[str]:
    """Return stable identity tokens used only to keep duplicate rows together."""

    tokens: list[str] = []

    if "doi" in row.index:
        raw_doi = clean_identity_value(row["doi"])
        doi = normalize_doi(raw_doi)
        if raw_doi and doi and is_valid_doi(raw_doi):
            tokens.append(f"doi:{doi}")

    for column in EXACT_IDENTIFIER_COLUMNS:
        if column in row.index and (identifier := normalize_identifier_value(row[column])):
            tokens.append(f"{column}:{identifier}")

    for column in URL_IDENTIFIER_COLUMNS:
        if column in row.index and (identifier := normalize_identifier_value(row[column])):
            tokens.append(f"{column}:{identifier}")

    if "title" in row.index and (title_key := normalize_identity_text(row["title"])):
        if len(title_key) >= TITLE_IDENTITY_MIN_LENGTH:
            if year_key := publication_year_key(row):
                tokens.append(f"title_year:{title_key}|{year_key}")
            tokens.append(f"title:{title_key}")

    return tokens


def publication_group_keys(frame: pd.DataFrame, source_row_column: str | None = None) -> pd.Series:
    parent = {index: index for index in frame.index}
    group_order = {
        index: (
            int(frame.at[index, source_row_column])
            if source_row_column in frame.columns
            else position
        )
        for position, index in enumerate(frame.index)
    }
    token_owner: dict[str, Any] = {}

    def find(index: Any) -> Any:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: Any, right: Any) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return

        if group_order[left_root] <= group_order[right_root]:
            parent[right_root] = left_root
            group_order[left_root] = min(group_order[left_root], group_order[right_root])
        else:
            parent[left_root] = right_root
            group_order[right_root] = min(group_order[left_root], group_order[right_root])

    for index, row in frame.iterrows():
        for token in publication_identity_tokens(row):
            if token in token_owner:
                union(index, token_owner[token])
            else:
                token_owner[token] = index

    return pd.Series(
        [f"publication:{group_order[find(index)]}" for index in frame.index],
        index=frame.index,
        dtype="object",
    )


def dominant_label(values: pd.Series) -> str:
    counts = values.astype(str).value_counts()
    largest_count = counts.max()
    return sorted(str(label) for label, count in counts.items() if count == largest_count)[0]


def publication_group_frame(
    frame: pd.DataFrame,
    *,
    label_column: str,
    source_row_column: str | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    groupby = frame.groupby(PUBLICATION_GROUP_COLUMN, sort=False, dropna=False)

    for group_key, group in groupby:
        if source_row_column in group.columns:
            order = int(group[source_row_column].min())
        else:
            order = int(min(frame.index.get_loc(index) for index in group.index))
        rows.append(
            {
                PUBLICATION_GROUP_COLUMN: group_key,
                PUBLICATION_GROUP_LABEL_COLUMN: dominant_label(group[label_column]),
                PUBLICATION_GROUP_ORDER_COLUMN: order,
            }
        )

    return pd.DataFrame(rows).sort_values(PUBLICATION_GROUP_ORDER_COLUMN).reset_index(drop=True)


def load_split_frame(config: DatasetSplitConfig) -> tuple[pd.DataFrame, int, pd.Series, str]:
    """Load, validate, and filter the source rows used for supervised splits."""

    frame = pd.read_csv(
        config.input_path,
        dtype=str,
        keep_default_na=False,
        nrows=config.max_rows,
        low_memory=False,
    )
    input_rows = len(frame)

    missing_columns = [column for column in required_columns(config) if column not in frame.columns]
    if missing_columns:
        raise ValueError(
            f"Input CSV is missing required column(s): {', '.join(missing_columns)}"
        )

    frame, source_row_column = add_source_row(frame)
    labels = frame[config.label_column].fillna("").astype(str).str.strip()
    usable_mask = labels != ""

    if config.require_text:
        usable_mask &= combined_text(frame, config.text_columns) != ""

    filtered = frame.loc[usable_mask].copy()
    filtered[config.label_column] = labels.loc[usable_mask]

    label_counts = filtered[config.label_column].value_counts()
    eligible_labels = label_counts[label_counts >= config.min_class_count].index
    filtered = filtered[filtered[config.label_column].isin(eligible_labels)].copy()
    label_counts = filtered[config.label_column].value_counts()

    if filtered.empty:
        raise ValueError("No usable rows found after filtering blank text/labels and small classes")
    if len(label_counts) < 2:
        raise ValueError("At least two label classes are required for stratified model splits")

    return filtered, input_rows, label_counts, source_row_column


def stratified_split_frame(
    frame: pd.DataFrame,
    *,
    label_column: str,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    random_state: int,
) -> dict[str, pd.DataFrame]:
    """Split rows with the existing train/validation/test stratification flow."""

    temp_ratio = validation_ratio + test_ratio
    train_frame, temp_frame = train_test_split(
        frame,
        train_size=train_ratio,
        test_size=temp_ratio,
        random_state=random_state,
        stratify=frame[label_column],
        shuffle=True,
    )

    validation_relative_ratio = validation_ratio / temp_ratio
    test_relative_ratio = test_ratio / temp_ratio
    validation_frame, test_frame = train_test_split(
        temp_frame,
        train_size=validation_relative_ratio,
        test_size=test_relative_ratio,
        random_state=random_state,
        stratify=temp_frame[label_column],
        shuffle=True,
    )

    return {
        "train": train_frame,
        "validation": validation_frame,
        "test": test_frame,
    }


def split_frame(
    frame: pd.DataFrame,
    *,
    label_column: str,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    random_state: int,
    source_row_column: str | None = None,
) -> dict[str, pd.DataFrame]:
    working = frame.copy()
    working[PUBLICATION_GROUP_COLUMN] = publication_group_keys(
        working,
        source_row_column=source_row_column,
    )
    groups = publication_group_frame(
        working,
        label_column=label_column,
        source_row_column=source_row_column,
    )
    group_splits = stratified_split_frame(
        groups,
        label_column=PUBLICATION_GROUP_LABEL_COLUMN,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        random_state=random_state,
    )

    return {
        split_name: working[
            working[PUBLICATION_GROUP_COLUMN].isin(set(group_frame[PUBLICATION_GROUP_COLUMN]))
        ]
        .drop(columns=[PUBLICATION_GROUP_COLUMN])
        .copy()
        for split_name, group_frame in group_splits.items()
    }


def publication_group_summary(frame: pd.DataFrame) -> dict[str, int]:
    group_sizes = frame[PUBLICATION_GROUP_COLUMN].value_counts()
    duplicate_group_sizes = group_sizes[group_sizes > 1]

    return {
        "publication_groups": int(len(group_sizes)),
        "duplicate_publication_groups": int(len(duplicate_group_sizes)),
        "duplicate_publication_rows": int(duplicate_group_sizes.sum())
        if not duplicate_group_sizes.empty
        else 0,
        "largest_publication_group_rows": int(group_sizes.max()) if not group_sizes.empty else 0,
    }


def with_split_column(frame: pd.DataFrame, split_name: str, source_row_column: str) -> pd.DataFrame:
    output = frame.copy()
    split_column = SPLIT_COLUMN if SPLIT_COLUMN not in output.columns else "dataset_split"
    insert_at = 1 if source_row_column in output.columns else 0
    output.insert(insert_at, split_column, split_name)
    return output.sort_values(source_row_column).reset_index(drop=True)


def write_dataframe_artifact(path: Path, frame: pd.DataFrame) -> SavedArtifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(file_descriptor)
    temp_path = Path(temp_name)

    try:
        frame.to_csv(temp_path, index=False)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return SavedArtifact(
        path=path,
        bytes=path.stat().st_size,
        sha256=file_sha256(path),
    )


def split_counts(split_frames: dict[str, pd.DataFrame]) -> dict[str, int]:
    return {split_name: len(frame) for split_name, frame in split_frames.items()}


def label_counts_by_split(
    split_frames: dict[str, pd.DataFrame],
    label_column: str,
) -> dict[str, dict[str, int]]:
    return {
        split_name: {
            str(label): int(count)
            for label, count in frame[label_column].value_counts().sort_index().items()
        }
        for split_name, frame in split_frames.items()
    }


def summary_rows(split_frames: dict[str, pd.DataFrame], label_column: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split_name, frame in split_frames.items():
        split_total = len(frame)
        for label, count in frame[label_column].value_counts().sort_index().items():
            rows.append(
                {
                    "split": split_name,
                    "label": str(label),
                    "count": int(count),
                    "split_rows": split_total,
                    "split_fraction": f"{count / split_total:.6f}" if split_total else "0.000000",
                }
            )
    return rows


def artifact_entry(artifact: SavedArtifact) -> dict[str, Any]:
    return artifact.as_manifest_dict()


def create_dataset_splits(config: DatasetSplitConfig) -> DatasetSplitResult:
    """Create train/validation/test CSVs plus summary and manifest artifacts."""

    validate_config(config)
    frame, input_rows, label_counts, source_row_column = load_split_frame(config)
    raw_splits = split_frame(
        frame,
        label_column=config.label_column,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        random_state=config.random_state,
        source_row_column=source_row_column,
    )
    grouped_frame = frame.copy()
    grouped_frame[PUBLICATION_GROUP_COLUMN] = publication_group_keys(
        grouped_frame,
        source_row_column=source_row_column,
    )
    output_splits = {
        split_name: with_split_column(split_frame, split_name, source_row_column)
        for split_name, split_frame in raw_splits.items()
    }

    train_output = config.output_dir / "train.csv"
    validation_output = config.output_dir / "validation.csv"
    test_output = config.output_dir / "test.csv"
    summary_output = config.output_dir / "split_summary.csv"
    manifest_output = config.output_dir / "split_manifest.json"

    train_artifact = write_dataframe_artifact(train_output, output_splits["train"])
    validation_artifact = write_dataframe_artifact(validation_output, output_splits["validation"])
    test_artifact = write_dataframe_artifact(test_output, output_splits["test"])
    summary_artifact = write_csv_artifact(
        summary_output,
        fieldnames=SUMMARY_FIELDNAMES,
        rows=summary_rows(output_splits, config.label_column),
    )

    counts = split_counts(output_splits)
    result = DatasetSplitResult(
        train_output=train_output,
        validation_output=validation_output,
        test_output=test_output,
        summary_output=summary_output,
        manifest_output=manifest_output,
        input_rows=input_rows,
        usable_rows=len(frame),
        dropped_rows=input_rows - len(frame),
        train_rows=counts["train"],
        validation_rows=counts["validation"],
        test_rows=counts["test"],
        class_count=len(label_counts),
    )

    manifest = {
        "artifact_schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "config": json_ready_dataclass(config),
        "result": json_ready_dataclass(result),
        "input": {
            "path": str(config.input_path),
            "bytes": config.input_path.stat().st_size,
            "sha256": file_sha256(config.input_path),
        },
        "label_counts": {str(label): int(count) for label, count in label_counts.items()},
        "publication_grouping": publication_group_summary(grouped_frame),
        "split_counts": counts,
        "label_counts_by_split": label_counts_by_split(output_splits, config.label_column),
        "artifacts": {
            "train": artifact_entry(train_artifact),
            "validation": artifact_entry(validation_artifact),
            "test": artifact_entry(test_artifact),
            "summary": artifact_entry(summary_artifact),
            "manifest": {"path": str(manifest_output)},
        },
    }
    write_json_artifact(manifest_output, manifest)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create reproducible train/validation/test CSVs for supervised "
            "publication text-classifier workflows."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input publication CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for split CSVs and manifest. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--label-column",
        default=DEFAULT_LABEL_COLUMN,
        help="Target label column used for stratification. Default: primary_domain",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns required for model rows. Default: title,abstract,keywords",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=DEFAULT_TRAIN_RATIO,
        help="Training split ratio. Default: 0.70",
    )
    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=DEFAULT_VALIDATION_RATIO,
        help="Validation split ratio. Default: 0.15",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=DEFAULT_TEST_RATIO,
        help="Test split ratio. Default: 0.15",
    )
    parser.add_argument("--random-state", type=int, default=DEFAULT_RANDOM_STATE, help="Random seed.")
    parser.add_argument(
        "--min-class-count",
        type=int,
        default=DEFAULT_MIN_CLASS_COUNT,
        help="Drop label classes with fewer rows. Default: 20",
    )
    parser.add_argument(
        "--allow-blank-text",
        action="store_true",
        help="Keep labeled rows even when all configured text columns are blank.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional source row limit for quick experiments. Default: use all rows.",
    )
    return parser.parse_args()


def result_summary(result: DatasetSplitResult) -> str:
    return "\n".join(
        [
            f"Created dataset splits from {result.usable_rows:,} usable rows.",
            f"Dropped rows: {result.dropped_rows:,}",
            f"Classes: {result.class_count:,}",
            f"Train: {result.train_rows:,} rows -> {result.train_output}",
            f"Validation: {result.validation_rows:,} rows -> {result.validation_output}",
            f"Test: {result.test_rows:,} rows -> {result.test_output}",
            f"Summary: {result.summary_output}",
            f"Manifest: {result.manifest_output}",
        ]
    )


def main() -> None:
    args = parse_args()
    result = create_dataset_splits(
        DatasetSplitConfig(
            input_path=args.input,
            output_dir=args.output_dir,
            label_column=args.label_column,
            text_columns=args.text_columns,
            train_ratio=args.train_ratio,
            validation_ratio=args.validation_ratio,
            test_ratio=args.test_ratio,
            random_state=args.random_state,
            min_class_count=args.min_class_count,
            require_text=not args.allow_blank_text,
            max_rows=args.max_rows,
        )
    )
    print(result_summary(result))


if __name__ == "__main__":
    main()
