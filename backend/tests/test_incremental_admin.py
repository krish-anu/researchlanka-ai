from __future__ import annotations

from pathlib import Path

from src.api.services import incremental_admin
from src.pipeline.refresh_policy import (
    DEFAULT_CONFIDENCE_REVIEW_THRESHOLD,
    DEFAULT_DB_LABELS,
)


class FakeProcess:
    pid = 12345


def test_admin_incremental_launcher_uses_shared_refresh_policy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(incremental_admin.subprocess, "Popen", fake_popen)

    status = incremental_admin.start_incremental_update(
        {},
        status_path=tmp_path / "status.json",
        log_dir=tmp_path / "logs",
    )

    args = seen["args"]
    assert isinstance(args, list)
    assert args[args.index("--db-labels") + 1] == ",".join(DEFAULT_DB_LABELS)
    assert (
        args[args.index("--confidence-review-threshold") + 1]
        == str(DEFAULT_CONFIDENCE_REVIEW_THRESHOLD)
    )
    assert status["db_labels"] == list(DEFAULT_DB_LABELS)
