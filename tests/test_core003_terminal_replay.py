"""CORE-003: terminal session facts survive metadata write failure + restart."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saipenview.sessions import SessionStore, project_key


def _fallback_path(store: SessionStore, run_id: str, root: str) -> Path:
    return (
        store._dir
        / ".pending-final"
        / project_key(root)
        / f"{run_id}.json"
    )


def _start(store: SessionStore, root: str):
    record = store.start(root, "codex", "Codex", "continue")
    assert record is not None
    store.append(record.run_id, "final output")
    return record


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [("done", 0), ("failed", 7), ("killed", -9)],
)
def test_terminal_fact_replays_after_restart_and_reconciles(
    tmp_path: Path, status: str, exit_code: int
):
    root = str(tmp_path / "project")
    first = SessionStore(base_dir=tmp_path / "sessions")
    record = _start(first, root)
    first._write_meta = lambda _record: False  # type: ignore[assignment]

    first.finish(record.run_id, status, exit_code)
    fallback = _fallback_path(first, record.run_id, root)
    assert fallback.is_file()
    running = json.loads((first._dir / f"{record.run_id}.json").read_text())
    assert running["status"] == "running"

    reopened = SessionStore(base_dir=first._dir)
    reopened._write_meta = lambda _record: False  # type: ignore[assignment]
    history = reopened.history(root)
    assert len(history) == 1
    assert history[0]["status"] == status
    assert history[0]["exit_code"] == exit_code
    assert history[0]["finished_at"] is not None
    assert history[0]["line_count"] == 1
    assert fallback.is_file()

    recovered = SessionStore(base_dir=first._dir)
    assert recovered.history(root)[0]["status"] == status
    canonical = json.loads((first._dir / f"{record.run_id}.json").read_text())
    assert canonical["status"] == status
    assert canonical["exit_code"] == exit_code
    assert canonical["finished_at"] == history[0]["finished_at"]
    assert not fallback.exists()

    second_reopen = SessionStore(base_dir=first._dir)
    assert second_reopen.history(root)[0]["status"] == status


def test_evicted_pending_terminal_is_replayed_after_restart(
    tmp_path: Path,
):
    root = str(tmp_path / "project")
    first = SessionStore(base_dir=tmp_path / "sessions")
    first._MAX_PENDING_FINAL = 2
    records = [_start(first, root) for _ in range(3)]
    first._write_meta = lambda _record: False  # type: ignore[assignment]

    for index, record in enumerate(records):
        first.finish(record.run_id, "done" if index < 2 else "killed", index)

    assert len(first._pending_final) <= first._MAX_PENDING_FINAL
    evicted = records[0]
    assert _fallback_path(first, evicted.run_id, root).is_file()

    reopened = SessionStore(base_dir=first._dir)
    history = {row["run_id"]: row for row in reopened.history(root, limit=10)}
    assert history[records[0].run_id]["status"] == "done"
    assert history[records[1].run_id]["status"] == "done"
    assert history[records[2].run_id]["status"] == "killed"


def test_corrupt_fallback_degrades_only_its_record(tmp_path: Path):
    root = str(tmp_path / "project")
    first = SessionStore(base_dir=tmp_path / "sessions")
    records = [_start(first, root) for _ in range(2)]
    first._write_meta = lambda _record: False  # type: ignore[assignment]
    first.finish(records[0].run_id, "failed", 4)
    first.finish(records[1].run_id, "done", 0)

    damaged = _fallback_path(first, records[0].run_id, root)
    healthy = _fallback_path(first, records[1].run_id, root)
    assert damaged.is_file() and healthy.is_file()
    damaged.write_text("{truncated", encoding="utf-8")

    reopened = SessionStore(base_dir=first._dir)
    history = {row["run_id"]: row for row in reopened.history(root, limit=10)}
    assert history[records[0].run_id]["status"] == "interrupted"
    assert history[records[1].run_id]["status"] == "done"


def test_running_record_without_terminal_fallback_is_interrupted(tmp_path: Path):
    root = str(tmp_path / "project")
    first = SessionStore(base_dir=tmp_path / "sessions")
    record = _start(first, root)

    reopened = SessionStore(base_dir=first._dir)
    history = reopened.history(root)
    assert history[0]["run_id"] == record.run_id
    assert history[0]["status"] == "interrupted"
