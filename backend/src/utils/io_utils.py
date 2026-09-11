"""Dataset load/save helpers shared by the ad-hoc extraction scripts.

Why this module exists
----------------------
``scripts/extraction/extract_authors.py`` and
``scripts/extraction/extract_titles.py`` were committed importing
``utils.io_utils``, but no such module was ever committed alongside them, so
both scripts failed at import with ``ModuleNotFoundError``. This module
restores exactly the two functions those scripts call -- :func:`load_dataset`
and :func:`save_dataset` -- and nothing more.

Scope
-----
This is deliberately thin. The heavyweight pipeline stages under
``src/pipeline/`` do their own IO with explicit column handling and dtype
control; they should **not** be migrated onto these helpers. Use these only
for the small "load a dataset, run one extractor over it, write the result"
scripts.

Format is chosen from the file extension: ``.csv`` (optionally ``.csv.gz``),
``.parquet``/``.pq``. Anything else raises :class:`ValueError` rather than
guessing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = ["load_dataset", "save_dataset", "common_schema_columns"]

_CSV_SUFFIXES = {".csv", ".txt"}
_PARQUET_SUFFIXES = {".parquet", ".pq"}


def common_schema_columns() -> list[str]:
    """Return the canonical common-schema column order.

    Imported lazily because the defining module
    (``src.pipeline.kaggle_merge_common_dataset``) is large and pulls in the
    full merge pipeline; callers that never validate should not pay for it.
    """

    from src.pipeline.kaggle_merge_common_dataset import COMMON_COLUMNS

    return list(COMMON_COLUMNS)


def _resolve_format(path: Path) -> str:
    """Map a path to ``"csv"`` or ``"parquet"``, honouring a ``.gz`` suffix."""

    suffixes = [suffix.lower() for suffix in path.suffixes]

    # Look past a trailing compression suffix, e.g. "dataset.csv.gz".
    if suffixes and suffixes[-1] in {".gz", ".bz2", ".zip", ".xz"}:
        suffixes = suffixes[:-1]

    suffix = suffixes[-1] if suffixes else ""

    if suffix in _CSV_SUFFIXES:
        return "csv"
    if suffix in _PARQUET_SUFFIXES:
        return "parquet"

    supported = ", ".join(sorted(_CSV_SUFFIXES | _PARQUET_SUFFIXES))
    raise ValueError(
        f"Cannot infer a dataset format from {path.name!r}. Supported extensions: {supported}."
    )


def check_common_schema(
    frame: pd.DataFrame,
    *,
    expected: "Sequence[str] | None" = None,
) -> list[str]:
    """Raise if ``frame`` is missing any canonical common-schema column.

    Args:
        frame: The loaded dataset.
        expected: Column names to require. Defaults to the full common schema.

    Returns:
        The expected column names that were present, in schema order.

    Raises:
        ValueError: If any expected column is absent. The message lists the
            missing names so the caller can tell a wrong input file from a
            genuinely incomplete one.
    """

    expected_columns = list(expected) if expected is not None else common_schema_columns()
    present = set(frame.columns)
    missing = [column for column in expected_columns if column not in present]

    if missing:
        preview = ", ".join(missing[:10])
        if len(missing) > 10:
            preview += f", ... (+{len(missing) - 10} more)"
        raise ValueError(
            f"Dataset is missing {len(missing)} expected common-schema column(s): {preview}"
        )

    return [column for column in expected_columns if column in present]


def load_dataset(
    path: str | Path,
    *,
    check_full_schema: bool = False,
    required_columns: "Sequence[str] | None" = None,
) -> pd.DataFrame:
    """Read a CSV or Parquet dataset into a DataFrame.

    CSV is read with ``dtype=str`` and ``keep_default_na=False`` so that
    identifier-like columns (DOIs, ORCIDs, record ids) survive the round trip
    without pandas coercing them to floats or turning the literal string "NA"
    into a null. Extractors in ``src/utils`` treat empty strings as missing
    anyway, so nothing downstream needs pandas' NaN sentinels.

    Args:
        path: Dataset location.
        check_full_schema: Require every one of the 76 canonical
            common-schema columns. This only holds for **merge-stage** outputs
            (``common_publications_all_records.csv``,
            ``common_publications_deduplicated.csv``). Later stages
            legitimately drop columns, so leave this off when reading
            ``common_publications_final.csv`` or anything downstream of it --
            prefer ``required_columns``.
        required_columns: Require just these columns. This is the right check
            for a script that reads a handful of fields, because it stays
            correct across every pipeline stage.

    Returns:
        The loaded DataFrame.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: On an unsupported extension, or a failed schema check.
    """

    dataset_path = Path(path)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    if _resolve_format(dataset_path) == "parquet":
        frame = pd.read_parquet(dataset_path)
    else:
        frame = pd.read_csv(
            dataset_path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )

    if check_full_schema:
        check_common_schema(frame)

    if required_columns:
        check_common_schema(frame, expected=required_columns)

    return frame


def save_dataset(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write ``frame`` to a CSV or Parquet file, creating parent directories.

    The row index is never written -- these datasets are keyed by explicit
    columns such as ``record_number``, and a stray index column has repeatedly
    caused schema drift when a written file is read back in.

    Args:
        frame: The DataFrame to write.
        path: Destination; the extension selects the format.

    Returns:
        The resolved output path.

    Raises:
        ValueError: On an unsupported extension.
    """

    output_path = Path(path)
    output_format = _resolve_format(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "parquet":
        frame.to_parquet(output_path, index=False)
    else:
        frame.to_csv(output_path, index=False)

    return output_path
