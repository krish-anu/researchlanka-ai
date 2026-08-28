"""Durable artifact saving for trained models and evaluation outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib


ARTIFACT_SCHEMA_VERSION = 1
PREDICTION_FIELDNAMES = ["source_row", "label", "prediction", "correct", "text"]
LABEL_COUNT_FIELDNAMES = ["label", "count"]


@dataclass(frozen=True)
class SavedArtifact:
    """Metadata for one file saved by the model artifact process."""

    path: Path
    bytes: int
    sha256: str

    def as_manifest_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CsvArtifactSpec:
    """A named CSV to save and checksum alongside the standard artifacts.

    Used for outputs that belong to a run but are not part of every run's fixed
    set -- the evaluation artifacts, for instance.
    """

    name: str
    path: Path
    fieldnames: Sequence[str]
    rows: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class SavedModelArtifacts:
    """Metadata for the files produced by one model-saving run."""

    model: SavedArtifact
    metrics: SavedArtifact
    label_counts: SavedArtifact
    predictions: SavedArtifact
    manifest: SavedArtifact
    extra: dict[str, SavedArtifact] = field(default_factory=dict)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 checksum for a saved artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_artifact(path: Path) -> SavedArtifact:
    return SavedArtifact(
        path=path,
        bytes=path.stat().st_size,
        sha256=file_sha256(path),
    )


def fsync_directory(path: Path) -> None:
    """Best-effort directory fsync so atomic replacements survive crashes.

    Flushing the *directory* entry is what makes a completed ``os.replace``
    durable across a power loss on POSIX. Windows supports neither opening a
    directory as a file descriptor nor fsyncing one, so both calls are treated
    as best-effort and any ``OSError`` is swallowed -- the artifact itself has
    already been fsynced by the writer at this point.
    """

    try:
        directory_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return

    try:
        os.fsync(directory_fd)
    except OSError:
        return
    finally:
        os.close(directory_fd)


def atomic_write_artifact(
    path: Path,
    writer: Callable[[Path], None],
) -> SavedArtifact:
    """Write an artifact through a temp file, then atomically replace the target."""

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(file_descriptor)
    temp_path = Path(temp_name)

    try:
        writer(temp_path)
        os.replace(temp_path, path)
        fsync_directory(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return describe_artifact(path)


def write_text_artifact(path: Path, text: str, *, encoding: str = "utf-8") -> SavedArtifact:
    def writer(temp_path: Path) -> None:
        with temp_path.open("w", encoding=encoding) as output_file:
            output_file.write(text)
            output_file.flush()
            os.fsync(output_file.fileno())

    return atomic_write_artifact(path, writer)


def write_json_artifact(path: Path, payload: Mapping[str, Any]) -> SavedArtifact:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return write_text_artifact(path, text)


def write_csv_artifact(
    path: Path,
    *,
    fieldnames: list[str],
    rows: Iterable[Mapping[str, Any]],
) -> SavedArtifact:
    def writer(temp_path: Path) -> None:
        with temp_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            output_file.flush()
            os.fsync(output_file.fileno())

    return atomic_write_artifact(path, writer)


def dump_joblib_artifact(path: Path, model: Any) -> SavedArtifact:
    """Pickle ``model`` to ``path`` durably, via the shared atomic-write helper.

    ``joblib.dump`` closes the file itself, so the bytes must be forced to disk
    through a second handle. That handle is opened ``"r+b"`` rather than
    ``"rb"``: Windows rejects ``os.fsync`` on a read-only descriptor with
    ``OSError(EBADF)``, while ``"r+b"`` is writable, does not truncate, and
    behaves identically on POSIX.
    """

    def writer(temp_path: Path) -> None:
        joblib.dump(model, temp_path)
        # Opened read-write, not "rb": Windows refuses to flush a handle that
        # was not opened for writing, so a read-only handle here fails the whole
        # save with EBADF.
        with temp_path.open("rb+") as output_file:
            os.fsync(output_file.fileno())

    return atomic_write_artifact(path, writer)


def label_count_rows(label_counts: Any) -> list[dict[str, Any]]:
    return [
        {"label": str(label), "count": int(count)}
        for label, count in label_counts.items()
    ]


def artifact_manifest_entries(
    *,
    model: SavedArtifact,
    metrics: SavedArtifact,
    label_counts: SavedArtifact,
    predictions: SavedArtifact,
    manifest_output: Path,
    extra: Mapping[str, SavedArtifact] | None = None,
) -> dict[str, dict[str, Any]]:
    entries = {
        "model": model.as_manifest_dict(),
        "metrics": metrics.as_manifest_dict(),
        "label_counts": label_counts.as_manifest_dict(),
        "predictions": predictions.as_manifest_dict(),
        "manifest": {"path": str(manifest_output)},
    }
    entries.update(
        {name: artifact.as_manifest_dict() for name, artifact in (extra or {}).items()}
    )
    return entries


def save_model_artifacts(
    *,
    model: Any,
    model_output: Path,
    metrics_text: str,
    metrics_output: Path,
    label_counts: Any,
    label_counts_output: Path,
    predictions: Iterable[Mapping[str, Any]],
    predictions_output: Path,
    manifest_output: Path,
    manifest_config: Mapping[str, Any],
    manifest_result: Mapping[str, Any],
    created_at: str | None = None,
    extra_csv_artifacts: Sequence[CsvArtifactSpec] = (),
) -> SavedModelArtifacts:
    """Save all model-training artifacts and write a checksum manifest."""

    saved_model = dump_joblib_artifact(model_output, model)
    saved_metrics = write_text_artifact(metrics_output, metrics_text)
    saved_labels = write_csv_artifact(
        label_counts_output,
        fieldnames=LABEL_COUNT_FIELDNAMES,
        rows=label_count_rows(label_counts),
    )
    saved_predictions = write_csv_artifact(
        predictions_output,
        fieldnames=PREDICTION_FIELDNAMES,
        rows=predictions,
    )
    saved_extra = {
        spec.name: write_csv_artifact(
            spec.path, fieldnames=list(spec.fieldnames), rows=spec.rows
        )
        for spec in extra_csv_artifacts
    }

    result_payload = dict(manifest_result)
    if not result_payload.get("model_sha256"):
        result_payload["model_sha256"] = saved_model.sha256

    manifest = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "config": dict(manifest_config),
        "result": result_payload,
        "label_counts": {str(label): int(count) for label, count in label_counts.items()},
        "artifacts": artifact_manifest_entries(
            model=saved_model,
            metrics=saved_metrics,
            label_counts=saved_labels,
            predictions=saved_predictions,
            manifest_output=manifest_output,
            extra=saved_extra,
        ),
    }
    saved_manifest = write_json_artifact(manifest_output, manifest)

    return SavedModelArtifacts(
        model=saved_model,
        metrics=saved_metrics,
        label_counts=saved_labels,
        predictions=saved_predictions,
        manifest=saved_manifest,
        extra=saved_extra,
    )
