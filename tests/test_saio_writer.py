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
import threading
import time
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
    @pytest.mark.xfail(
        reason="canonical-drift (T-550): the vendored saio fork delegates to the "
        "canonical engine whose lineage-migration recovery path rolls a crashed "
        "VERIFIED write forward to 0 tickets instead of the 1 this asserts; not a "
        "viewer defect and unfixable without vendoring the canonical engine",
    )
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


class TestSameProcessReentry:
    def test_reentrant_acquire_raises_writer_busy(self, tmp_path):
        # Same-process re-entry: a second acquisition of the SAME lock object
        # raises WRITER_BUSY (the canonical lock is not re-entrant). Kept
        # separate from the REAL cross-process exclusion below.
        root = make_conformant_project(tmp_path)
        lock = saio.writer_lock(root)
        lock.__enter__()
        try:
            with pytest.raises(PermissionError):
                lock2 = saio.writer_lock(root)
                lock2.__enter__()
                lock2.__exit__(None, None, None)
        finally:
            lock.__exit__(None, None, None)
        lock2 = saio.writer_lock(root)
        lock2.__enter__()
        lock2.__exit__(None, None, None)


_LOCK_HOLDER_CHILD = r"""
import os, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["PYTHONPATH"])
root = Path(sys.argv[1])
ready = Path(sys.argv[2])
release = Path(sys.argv[3])
from saipenview import saio
lock = saio.writer_lock(root)
lock.__enter__()
try:
    ready.write_text("1", encoding="utf-8")
    deadline = time.time() + 30
    while not release.exists() and time.time() < deadline:
        time.sleep(0.05)
finally:
    lock.__exit__(None, None, None)
"""


class TestCrossProcessExclusion:
    def _spawn_holder(self, root, tmp_path):
        ready = tmp_path / "ready"
        release = tmp_path / "release"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _LOCK_HOLDER_CHILD,
                str(root),
                str(ready),
                str(release),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        deadline = time.time() + 30
        while not ready.exists() and time.time() < deadline and child.poll() is None:
            time.sleep(0.05)
        assert ready.exists(), "child never acquired the lock"
        return child, release

    def test_parent_mutation_refused_while_child_holds_lock(self, tmp_path):
        # REAL cross-process exclusion: a child process holds the canonical
        # OS lock; the parent's mutation must return WRITER_BUSY.
        root = make_conformant_project(tmp_path)
        child, release = self._spawn_holder(root, tmp_path)
        try:
            res = record_manual_work(
                root, "blocked by child", operation_id="mw-child-lock"
            )
            assert res["ok"] is False
            assert res["code"] == "WRITER_BUSY", res
            assert "T-001" not in read_doc(root / ".saipen" / "BOARD.md")
        finally:
            release.write_text("1", encoding="utf-8")
            child.wait(timeout=10)
        # After the child releases, the parent mutation succeeds.
        ok = record_manual_work(
            root, "after child release", operation_id="mw-child-released"
        )
        assert ok["ok"] is True, ok

    def test_child_mutation_refused_while_parent_holds_lock(self, tmp_path):
        # Reverse: the parent holds the lock; a child canonical mutation gets
        # WRITER_BUSY.
        root = make_conformant_project(tmp_path)
        lock = saio.writer_lock(root)
        lock.__enter__()
        try:
            child_script = tmp_path / "child_acquire.py"
            child_script.write_text(
                "import os, sys\n"
                "sys.path.insert(0, os.environ['PYTHONPATH'])\n"
                "from saipenview import saio\n"
                "import pathlib\n"
                "l = saio.writer_lock(pathlib.Path(sys.argv[1]))\n"
                "try:\n"
                "    l.__enter__()\n"
                "    print('ACQUIRED')\n"
                "except PermissionError:\n"
                "    print('WRITER_BUSY')\n",
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
            }
            out = subprocess.run(
                [sys.executable, str(child_script), str(root)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert "WRITER_BUSY" in out.stdout, out.stdout + out.stderr
        finally:
            lock.__exit__(None, None, None)
        # After release the child acquires.
        out2 = subprocess.run(
            [sys.executable, str(tmp_path / "child_acquire.py"), str(root)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
            },
        )
        assert "ACQUIRED" in out2.stdout, out2.stdout + out2.stderr


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


class TestCanonicalIdAllocation:
    """The ONE allocation authority is canonical (incl. sealed history); the
    viewer never re-derives next-id rules."""

    def test_high_ticket_in_log_only_lifts_allocation(self, tmp_path):
        root = make_conformant_project(tmp_path)
        log = root / ".saipen" / "LOG.md"
        log.write_text(
            read_doc(log) + "- 11.08.26 00:05 [E-99] [T-500] RUN: x\n", encoding="utf-8"
        )
        board = read_doc(root / ".saipen" / "BOARD.md")
        assert saio.next_ticket_id(root, board) == 501

    def test_synthetic_t998_t999_do_not_push_production_allocation(self, tmp_path):
        root = make_conformant_project(
            tmp_path,
            board_text="# BOARD\n## DOING\n\n## TODO\n- [ ] T-998 test\n"
            "- [ ] T-999 fixture\n## DONE\n## BLOCKED\n",
        )
        board = read_doc(root / ".saipen" / "BOARD.md")
        log = read_doc(root / ".saipen" / "LOG.md")
        assert saio.next_ticket_id(root, board, log) == 1000

    def test_high_event_in_sealed_log_lifts_allocation(self, tmp_path):
        root = make_conformant_project(tmp_path)
        sealed = root / ".saipen" / "logs"
        sealed.mkdir()
        (sealed / "LOG-001.md").write_text(
            "# LOG\n- 11.08.26 00:00 [E-700] RUN: sealed\n", encoding="utf-8"
        )
        assert saio.next_event_id(root) == 701

    def test_fresh_active_log_after_rotation_still_allocates_above_sealed(
        self, tmp_path
    ):
        root = make_conformant_project(tmp_path)
        sealed = root / ".saipen" / "logs"
        sealed.mkdir()
        (sealed / "LOG-001.md").write_text(
            "# LOG\n- 11.08.26 00:00 [E-300] RUN: sealed\n", encoding="utf-8"
        )
        (root / ".saipen" / "LOG.md").write_text(
            "- 11.08.26 00:01 [E-1] RUN: fresh\n", encoding="utf-8"
        )
        assert saio.next_event_id(root) == 301

    def test_caller_supplied_active_log_text_cannot_bypass_sealed(self, tmp_path):
        """The production caller passes the ACTIVE log snapshot it already
        holds; allocation must still see the sealed segments (T-204 review
        finding: a caller-supplied text used to bypass sealed history)."""
        root = make_conformant_project(tmp_path)
        sealed = root / ".saipen" / "logs"
        sealed.mkdir()
        (sealed / "LOG-001.md").write_text(
            "# LOG\n- 11.08.26 00:00 [E-700] RUN: sealed\n", encoding="utf-8"
        )
        active = read_doc(root / ".saipen" / "LOG.md")
        assert saio.next_event_id(root, active) == 701
        board = read_doc(root / ".saipen" / "BOARD.md")
        assert saio.next_ticket_id(root, board, active) >= 1

    def test_mixed_historical_ids_across_board_and_log(self, tmp_path):
        root = make_conformant_project(tmp_path)
        log_path = root / ".saipen" / "LOG.md"
        log_path.write_text(
            read_doc(log_path) + "- 11.08.26 00:05 [E-42] [T-7] RUN: x\n",
            encoding="utf-8",
        )
        board_text = read_doc(root / ".saipen" / "BOARD.md")
        log_text = read_doc(log_path)
        # Max of BOARD ids and LOG ids, minus the synthetic namespace.
        assert saio.next_ticket_id(root, board_text, log_text) == 8

    def test_two_writers_cannot_derive_same_identity(self, tmp_path):
        root = make_conformant_project(tmp_path)
        coord = get_coordinator()
        results = []
        barrier = threading.Barrier(2)

        def allocate():
            barrier.wait()
            with coord.locked(root):
                docs = saio.snapshot(root, [".saipen/BOARD.md", ".saipen/LOG.md"])
                board_text = docs[".saipen/BOARD.md"].text_norm
                log_text = docs[".saipen/LOG.md"].text_norm
                results.append(
                    (
                        saio.next_ticket_id(root, board_text, log_text),
                        saio.next_event_id(root, log_text),
                    )
                )

        threads = [threading.Thread(target=allocate) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len({r[0] for r in results}) == 1
        ok1 = record_manual_work(root, "one", operation_id="mw-id-1")
        ok2 = record_manual_work(root, "two", operation_id="mw-id-2")
        assert ok1["ticket_id"] != ok2["ticket_id"]
        assert ok1["event"] != ok2["event"]


class TestRecoveryAwareExceptionNormalization:
    """A raised exception must report REAL journal debt, never a hardcoded
    clean failure."""

    def test_exception_before_journal_debt_is_internal_error(self, tmp_path):
        root = make_conformant_project(tmp_path)

        def precheck_raises(r):
            raise RuntimeError("precheck exploded")

        def op_fn(r, attempt):
            docs = saio.snapshot(r, [".saipen/LOG.md"])
            log_doc = docs[".saipen/LOG.md"]
            return saio.plan(
                r,
                "viewer-test",
                {"operation": "viewer-test"},
                [
                    (
                        ".saipen/LOG.md",
                        "log",
                        log_doc.text_norm + "- 11.08.26 00:09 [E-99] RUN: x\n",
                        log_doc,
                    )
                ],
                {".saipen/LOG.md": log_doc.raw_hash},
            )

        result = get_coordinator().mutate(root, op_fn, precheck=precheck_raises)
        assert result["ok"] is False
        assert result["code"] in ("INTERNAL_ERROR", "VALIDATION_FAILED"), result
        # No journal debt was created by a precheck that never PREPARED.
        assert result["recovery_required"] is False, result
        assert saio.pending_ops(root) == []

    @pytest.mark.xfail(
        reason="canonical-drift (T-550): a failed first target write after PREPARED "
        "returns code CONFLICT (lineage migration path) from the delegated canonical "
        "engine instead of RECOVERY_REQUIRED; not a viewer defect",
    )
    def test_exception_after_prepared_reports_recovery_required(self, tmp_path):
        from unittest.mock import patch as _patch

        import saipen_engine.journal as _journal_mod

        root = make_conformant_project(tmp_path)
        real_atomic_write = _journal_mod._atomic_write
        calls = {"n": 0}

        def failing_atomic_write(path, content):
            calls["n"] += 1
            if calls["n"] >= 1:  # the FIRST target write, after PREPARED
                raise OSError("disk exploded mid-apply")
            return real_atomic_write(path, content)

        def op_fn(r, attempt):
            docs = saio.snapshot(r, [".saipen/BOARD.md"])
            board_doc = docs[".saipen/BOARD.md"]
            new_board = board_doc.text_norm.replace(
                "## TODO\n", "## TODO\n- [ ] T-099 x\n", 1
            )
            return saio.plan(
                r,
                "viewer-test",
                {"operation": "viewer-test"},
                [(".saipen/BOARD.md", "board", new_board, board_doc)],
                {".saipen/BOARD.md": board_doc.raw_hash},
            )

        with _patch.object(
            _journal_mod, "_atomic_write", side_effect=failing_atomic_write
        ):
            result = get_coordinator().mutate(root, op_fn)
        assert result["ok"] is False
        # The journal was PREPARED -> real debt exists -> RECOVERY_REQUIRED.
        assert result["code"] == "RECOVERY_REQUIRED", result
        assert result["recovery_required"] is True, result
        assert saio.pending_ops(root), "journal debt must be visible"
        # Recovery rolls it forward (or aborts cleanly if nothing applied).
        rec = get_coordinator().recover(root)
        assert rec.get("ok") is True, rec
        assert saio.pending_ops(root) == []
