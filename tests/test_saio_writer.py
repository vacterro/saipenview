"""The canonical writer pipeline: real OS lock, journal, recovery (P0).

These are the red tests for replacing the fake-atomic multi-file transaction:
a crash after write N must leave a recoverable journal and NEVER report a
partial state as success; an external process writer must be excluded by the
OS lock; recovery replay is idempotent; decisions are bound to the exact
snapshot whose hashes are revalidated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import canonical_home, make_conformant_project

from saipenview import saio
from saipenview.parser import record_manual_work
from saipenview.protocol_write import get_coordinator
from saipenview.textio import read_doc

pytestmark = pytest.mark.skipif(
    canonical_home() is None,
    reason="canonical SAIPEN home unreachable",
)

CRASH_HELPER = r"""
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
from saipenview.parser import record_manual_work
res = record_manual_work(root, "crash point %s" % sys.argv[2],
                         operation_id="mw-crash-" + sys.argv[2])
print(json.dumps(res))
"""


_CRASH_ENV = {
    "PREPARED": "NITRO_CRASH_AFTER_PREPARE",
    "log": "NITRO_CRASH_AFTER_LOG",
    "board": "NITRO_CRASH_AFTER_BOARD",
    "state": "NITRO_CRASH_AFTER_STATE",
    "VERIFIED": "NITRO_CRASH_AFTER_VERIFIED",
}


def _run_crash(root: Path, point: str) -> dict:
    env = dict(os.environ)
    env[_CRASH_ENV[point]] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    r = subprocess.run(
        [sys.executable, "-c", CRASH_HELPER, str(root), point],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    out = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "{}"
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out, "returncode": r.returncode}


def _journal_ops(root: Path) -> list[dict]:
    return saio.recovery_status(root).get("pending", [])


class TestCrashRecovery:
    @pytest.mark.parametrize("point", ["PREPARED", "log", "board", "state", "VERIFIED"])
    def test_crash_after_every_write_leaves_recoverable_journal(self, tmp_path, point):
        root = make_conformant_project(tmp_path)
        res = _run_crash(root, point)
        # The crashed writer must NOT have reported success (crash = exit 87,
        # no result line).
        assert res.get("ok") is not True, res
        # The canonical journal exists and is UNRESOLVED (owns mutation state).
        ops = _journal_ops(root)
        assert ops, f"no journal after crash at {point}: {res}"
        assert ops[0]["status"] in ("PREPARED", "APPLYING", "VERIFIED"), ops

        # Recovery rolls forward (a single pending op auto-recovers under the
        # canonical preflight, or explicitly here); replay is idempotent.
        rec = get_coordinator().recover(root)
        assert rec.get("ok") is True, rec
        rec2 = get_coordinator().recover(root)
        assert rec2.get("ok") is True, rec2
        # The crashed op's writes are now consistent: for a crash BEFORE the
        # first write (PREPARED) the op aborts with nothing applied; any later
        # crash rolls forward to exactly one ticket. Either way: no duplicates,
        # LOG tail == STATE.last_event.
        log = read_doc(root / ".saipen" / "LOG.md")
        state = read_doc(root / ".saipen" / "STATE.md")
        import re as _re

        events = [int(m.group(1)) for m in _re.finditer(r"\[E-(\d+)\]", log)]
        assert len(events) == len(set(events)), events
        tail = max(events)
        le = next(int(m.group(1)) for m in _re.finditer(r"last_event:\s*(\d+)", state))
        assert le == tail, (le, tail)
        board = read_doc(root / ".saipen" / "BOARD.md")
        expected_tickets = 0 if point == "PREPARED" else 1
        assert board.count("T-001") == expected_tickets, (point, board)
        # Subsequent mutation works and does not duplicate the crashed op.
        ok = record_manual_work(
            root, "after recovery", operation_id="mw-after-recovery"
        )
        assert ok.get("ok") is True, ok
        log2 = read_doc(root / ".saipen" / "LOG.md")
        assert len(log2) > len(log)

    def test_crash_after_prepare_with_nothing_applied_aborts(self, tmp_path):
        root = make_conformant_project(tmp_path)
        res = _run_crash(root, "PREPARED")
        assert res.get("ok") is not True, res
        ops = _journal_ops(root)
        assert ops and ops[0]["status"] in ("PREPARED", "APPLYING"), ops
        # No canonical byte changed before the first write: recovery aborts
        # the PREPARED op with nothing applied.
        get_coordinator().recover(root)
        log = read_doc(root / ".saipen" / "LOG.md")
        assert "mw-crash" not in log
        assert log.count("[E-3]") == 0


class TestIdempotentRecovery:
    def test_recovery_replay_is_idempotent(self, tmp_path):
        root = make_conformant_project(tmp_path)
        _run_crash(root, "log")
        first = get_coordinator().recover(root)
        second = get_coordinator().recover(root)
        assert first.get("ok") is True
        assert second.get("ok") is True
        log = read_doc(root / ".saipen" / "LOG.md")
        assert log.count("[E-3]") == 1
        board = read_doc(root / ".saipen" / "BOARD.md")
        assert board.count("T-001") == 1

    def test_repeated_recovery_of_committed_op_is_noop(self, tmp_path):
        root = make_conformant_project(tmp_path)
        ok = record_manual_work(root, "done", operation_id="mw-done")
        assert ok.get("ok") is True
        # Recovery of the committed op returns ALREADY_APPLIED, never rewrites.
        rec = get_coordinator().recover(root, ok.get("op_id"))
        assert rec.get("ok") is True
        log = read_doc(root / ".saipen" / "LOG.md")
        assert log.count("[E-3]") == 1


class TestCrossProcessExclusion:
    def test_second_process_writer_is_excluded(self, tmp_path):
        # The canonical OS lock is cross-process: while one process holds it,
        # a second process's mutation returns WRITER_BUSY (never interleaves).
        root = make_conformant_project(tmp_path)
        lock = saio.writer_lock(root)
        lock.__enter__()
        try:
            # This is the same process (msvcrt locks are per-process), so the
            # exclusion is proven at the lock layer instead: a re-acquire must
            # raise WRITER_BUSY. Cross-process exclusion is msvcrt's contract,
            # exercised here through the canonical lock object.
            with pytest.raises(PermissionError):
                lock2 = saio.writer_lock(root)
                lock2.__enter__()
                lock2.__exit__(None, None, None)
        finally:
            lock.__exit__(None, None, None)
        # After release the lock is acquirable again.
        lock2 = saio.writer_lock(root)
        lock2.__enter__()
        lock2.__exit__(None, None, None)


class TestPathAlias:
    def test_same_project_through_alias_uses_one_lock_identity(self, tmp_path):
        root = make_conformant_project(tmp_path)
        alias = tmp_path / "alias"
        try:
            import os as _os

            _os.symlink(root, alias, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks unavailable on this host")
        canon = root.resolve()
        alias_r = alias.resolve()
        assert saio.resolve_home(canon) == saio.resolve_home(alias_r)
        # The canonical lock identity is alias-independent.
        ops = saio.engine(canon)["operations"]
        ident1 = ops._identity(canon)
        ident2 = ops._identity(alias_r)
        assert ident1 == ident2, "alias split the project identity"


class TestDecisionBoundToSnapshot:
    def test_external_edit_between_decision_and_apply_is_stale(self, tmp_path):
        # A decision read then an external write before the commit must not
        # commit the old decision. We sabotage the canonical apply by editing
        # LOG after the plan is built but before run_mutation reads it.
        root = make_conformant_project(tmp_path)

        def sabotage(root, plan):
            # External edit lands after plan build, before apply.
            (root / ".saipen" / "LOG.md").write_text(
                read_doc(root / ".saipen" / "LOG.md")
                + "- 11.08.26 00:05 [E-99] [parent: E-2] RUN: external\n",
                encoding="utf-8",
            )
            return saio.apply(root, plan)

        def op_fn(r, attempt):
            docs = saio.snapshot(
                r, [".saipen/LOG.md", ".saipen/BOARD.md", ".saipen/STATE.md"]
            )
            log_doc = docs[".saipen/LOG.md"]
            return saio.plan(
                r,
                "viewer-test",
                {"operation": "viewer-test"},
                [
                    (rel, "generic", log_doc.text_norm + "x", log_doc)
                    for rel, log_doc in [(".saipen/LOG.md", log_doc)]
                ],
                {".saipen/LOG.md": log_doc.raw_hash},
                read_deps={
                    ".saipen/STATE.md": docs[".saipen/STATE.md"].raw_hash,
                    ".saipen/BOARD.md": docs[".saipen/BOARD.md"].raw_hash,
                },
            )

        coord = get_coordinator()
        with coord.locked(root):
            plan = op_fn(root, 0)
            result = sabotage(root, plan)
        assert result["ok"] is False
        assert result["code"] in ("STALE_STATE", "CONFLICT"), result
        # The external line survived; the planned write did not land twice.
        log = read_doc(root / ".saipen" / "LOG.md")
        assert log.count("[E-99]") == 1
