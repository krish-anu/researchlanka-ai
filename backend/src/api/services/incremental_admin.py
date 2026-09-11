"""Internal admin helpers for triggering incremental publication updates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.api.core.errors import APIError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATUS_PATH = PROJECT_ROOT / "outputs" / "incremental" / "ui_status.json"
DEFAULT_LOG_DIR = PROJECT_ROOT / "outputs" / "incremental" / "ui_logs"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_incremental_status(
    status_path: Path = DEFAULT_STATUS_PATH,
) -> dict[str, Any]:
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return idle_status()
    except json.JSONDecodeError as exc:
        raise APIError(
            "invalid_incremental_status",
            "Incremental update status file is invalid.",
            status=500,
        ) from exc

    if not isinstance(payload, dict):
        raise APIError(
            "invalid_incremental_status",
            "Incremental update status payload is invalid.",
            status=500,
        )
    return normalize_status(payload)


def start_incremental_update(
    payload: dict[str, Any],
    *,
    status_path: Path = DEFAULT_STATUS_PATH,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> dict[str, Any]:
    current = read_incremental_status(status_path)
    if current["status"] == "running" and is_process_running(current.get("pid")):
        raise APIError(
            "incremental_update_running",
            "An incremental update is already running.",
            status=409,
        )

    log_dir.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{utc_now().replace(':', '').replace('-', '')}.log"

    args = [
        sys.executable,
        "scripts/admin/run_incremental_update_job.py",
        "--status",
        str(status_path),
        "--log-path",
        str(log_path),
        "--db-labels",
        "AI",
    ]

    model_path = str(
        payload.get("model")
        or os.getenv("RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH")
        or "data/models/ai_relevance/ai_relevance_linear_svm.joblib"
    ).strip()
    if model_path:
        args.extend(["--model", model_path])

    for field, argument in (
        ("from_date", "--from-date"),
        ("to_date", "--to-date"),
        ("confidence_review_threshold", "--confidence-review-threshold"),
    ):
        value = str(payload.get(field) or "").strip()
        if value:
            args.extend([argument, value])

    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            args,
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    status_payload = {
        "status": "running",
        "pid": process.pid,
        "started_at": utc_now(),
        "finished_at": None,
        "message": "Incremental AI publication update started.",
        "model": model_path,
        "db_labels": ["AI"],
        "log_path": str(log_path),
    }
    write_status(status_path, status_payload)
    return normalize_status(status_payload)


def idle_status() -> dict[str, Any]:
    return {
        "status": "idle",
        "pid": None,
        "started_at": None,
        "finished_at": None,
        "message": "No manual update has been started from this console.",
        "model": None,
        "db_labels": ["AI"],
        "log_path": None,
    }


def normalize_status(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "idle")
    if status not in {"idle", "running", "succeeded", "failed"}:
        status = "idle"
    return {
        "status": status,
        "pid": payload.get("pid") if isinstance(payload.get("pid"), int) else None,
        "started_at": payload.get("started_at") if isinstance(payload.get("started_at"), str) else None,
        "finished_at": payload.get("finished_at") if isinstance(payload.get("finished_at"), str) else None,
        "message": str(payload.get("message") or "No status message is available."),
        "model": payload.get("model") if isinstance(payload.get("model"), str) else None,
        "db_labels": payload.get("db_labels") if isinstance(payload.get("db_labels"), list) else ["AI"],
        "log_path": payload.get("log_path") if isinstance(payload.get("log_path"), str) else None,
        "result": payload.get("result") if isinstance(payload.get("result"), dict) else None,
    }


def write_status(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def is_process_running(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
