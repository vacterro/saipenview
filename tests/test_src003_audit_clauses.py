"""SRC-003 (audit/1.md) clause regressions -- one red case per repaired defect.

Every test here first proves the defect is reachable and then pins the repair,
because each of these shipped a plausible-looking guard that did not hold:

- a one-shot obligation cleared before the work it guarded succeeded;
- corruption handling with no way out;
- a semantic invariant enforced on write and not on read;
- a component teardown that cleared a process-global registry;
- an authority loader whose "exactly one home" promise was unsynchronized and
  keyed two different ways;
- a lifecycle check placed before the side effects it was supposed to gate;
- a rollback that named two exception types out of the three its own callback
  documents;
- a secondary index with no eviction on authoritative removal.
"""

from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from saipenview.api import Api
from saipenview.external_changes import ExternalChangeRegistry
from saipenview.scanner import ScanOutcome


def _project(tmp_path: Path, name: str = "proj", last_event: int = 1) -> Path:
    root = tmp_path / name
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\nnext_action: PHASE DONE\nblocker: none\n"
        "agent: a\nsaipen_version: 7\nmode: full\ntransition_from: SHIP\n"
        f"updated: 2026-08-30T00:00:00Z\nlast_event: {last_event}\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "## DOING\n\n## TODO\n- [ ] T-1 [P2] probe ticket | verify: none\n"
        "\n## DONE\n\n## BLOCKED\n",
        encoding="utf-8",
    )
    (saipen / "LOG.md").write_text(
        "# Log\n- 30.08.26 00:00 [E-001] DEC: base\n", encoding="utf-8"
    )
    return root


def _row(root: Path) -> dict:
    return {
        "root": str(root),
        "name": root.name,
        "phase": "DONE",
        "is_pinned": False,
        "task": "none",
        "next_action": "",
        "blocker": "none",
        "mtime": 0,
        "updated": "",
        "updated_kind": "",
        "conformance": {"verdict": "pass", "fails": 0, "warns": 0, "findings": []},
        "git_branch": "",
        "git_dirty": False,
        "board": {},
        "subs": [],
        "translate": None,
        "quick_actions": [],
        "subs_stale": False,
        "subs_stale_details": "",
    }


# ── R001 / CORE-001: the startup reconciliation obligation ────────────────────


class TestStartupObligationSurvivesFailure:
    def test_transient_failure_keeps_the_obligation_pending(self, tmp_path, monkeypatch):
        proj = _project(tmp_path)
        a = Api()
        try:
            a._projects = [_row(proj)]
            a._last_cache_snapshot = {str(proj): a._projects[0]}
            a._full_refresh_pending = True

            calls = {"n": 0}
            real = Api.__module__  # keep the import graph honest; patch the callee

            def flaky(root, with_git=True):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError("transient disk blip")
                from saipenview.parser import load_project as real_load

                return real_load(root, with_git=with_git)

            monkeypatch.setattr("saipenview.api.load_project", flaky)
            assert real  # silence the unused binding without hiding the patch

            a.refresh_known()
            assert calls["n"] == 1
            assert a._full_refresh_pending is True, (
                "a transient read failure must NOT consume the one-shot "
                "startup reconciliation obligation"
            )
            # The row is still the previous one (transient failures never drop).
            assert [p["root"] for p in a._projects] == [str(proj)]

            a.refresh_known()
            assert calls["n"] == 2, "the second poll must retry the failed root"
            assert a._full_refresh_pending is False, (
                "a clean reconciliation discharges the obligation"
            )
        finally:
            a.stop()

    def test_retry_exhaustion_keeps_the_obligation_pending(self, tmp_path, monkeypatch):
        proj = _project(tmp_path)
        a = Api()
        try:
            a._projects = [_row(proj)]
            a._full_refresh_pending = True

            # Bump the registry revision on every parse so all three attempts
            # lose the commit race.
            def racing(root, with_git=True):
                from saipenview.parser import load_project as real_load

                a._registry_rev += 1
                return real_load(root, with_git=with_git)

            monkeypatch.setattr("saipenview.api.load_project", racing)
            a.refresh_known()
            assert a._full_refresh_pending is True, (
                "three lost commit races are not a reconciliation"
            )
        finally:
            a.stop()

    def test_idle_short_circuit_cannot_fire_while_pending(self, tmp_path):
        proj = _project(tmp_path)
        a = Api()
        try:
            a._projects = [_row(proj)]
            a._full_refresh_pending = True
            result = a.refresh_known(a._registry_rev)
            assert isinstance(result, dict)
            assert result["projects"] is not None, (
                "a pending obligation must never be answered with projects=None"
            )
        finally:
            a.stop()


# ── R002 / CORE-002: corrupt registry recovery ────────────────────────────────


class TestCorruptRegistryRecovery:
    def _corrupt(self, tmp_path: Path) -> tuple[ExternalChangeRegistry, Path]:
        persist = tmp_path / "ec.json"
        persist.write_text("{ not json at all", encoding="utf-8")
        reg = ExternalChangeRegistry()
        reg._set_persist_path(persist)
        return reg, persist

    def test_corruption_is_still_fail_closed(self, tmp_path):
        reg, persist = self._corrupt(tmp_path)
        assert reg.is_degraded() is True
        assert reg.load_untrusted() is True
        assert persist.with_suffix(".corrupt").exists(), "evidence not preserved"
        assert reg.record(str(tmp_path), ".saipen/STATE.md", "beef") == -1

    def test_recovery_retains_post_corruption_evidence_and_archives_the_artifact(
        self, tmp_path
    ):
        reg, persist = self._corrupt(tmp_path)
        reg.record(str(tmp_path), ".saipen/STATE.md", "beef")
        assert len(reg.pending()) == 1

        result = reg.recover_from_corrupt()
        assert result["ok"] is True and result["recovered"] is True
        assert result["retained_pending"] == 1
        archived = Path(result["archived"])
        assert archived.exists(), "corrupt artifact must be archived, never deleted"
        assert archived.read_text(encoding="utf-8").startswith("{ not json")
        assert not persist.with_suffix(".corrupt").exists(), (
            "canonical corruption marker must be gone after successful recovery"
        )
        assert reg.is_degraded() is False

        fresh = ExternalChangeRegistry()
        fresh._set_persist_path(persist)
        assert fresh.is_degraded() is False, "recovery must survive restart"
        assert len(fresh.pending()) == 1, "post-corruption evidence must be durable"

        # And the acknowledgement of that record persists too.
        entry = fresh.pending()[0]
        assert fresh.acknowledge(entry.root, entry.rel_path, entry.token) is True
        again = ExternalChangeRegistry()
        again._set_persist_path(persist)
        assert again.pending() == []

    def test_failed_replacement_write_survives_restart(self, tmp_path, monkeypatch):
        """CORE-001 A: a failed replacement commit must not become healthy
        evidence after restart."""
        reg, persist = self._corrupt(tmp_path)
        marker = persist.with_suffix(".corrupt")
        monkeypatch.setattr(ExternalChangeRegistry, "_save", lambda self: False)
        result = reg.recover_from_corrupt()
        assert result["ok"] is False and result["recovered"] is False
        assert marker.exists(), (
            "canonical marker or equivalent durable untrusted indicator must "
            "still exist after a failed replacement commit"
        )
        assert reg.is_degraded() is True, "same process stays degraded"

        fresh = ExternalChangeRegistry()
        fresh._set_persist_path(persist)
        assert fresh.is_degraded() is True, (
            "a fresh registry on the same path must still see the untrusted state"
        )
        assert fresh.load_untrusted() is True
        assert fresh.pending() == []

    def test_corrupt_evidence_archive_survives_failed_recovery(self, tmp_path, monkeypatch):
        """CORE-001 B: the original corrupt bytes must still be recoverable
        from the archived artifact after a failed recovery."""
        reg, persist = self._corrupt(tmp_path)
        marker = persist.with_suffix(".corrupt")
        monkeypatch.setattr(ExternalChangeRegistry, "_save", lambda self: False)
        result = reg.recover_from_corrupt()
        assert result["ok"] is False
        assert result["archived"] is not None, "evidence must be archived first"
        archived = Path(result["archived"])
        assert archived.exists() and archived != marker
        assert archived.read_text(encoding="utf-8").startswith("{ not json"), (
            "original corrupt bytes must survive the failed recovery"
        )
        assert marker.read_text(encoding="utf-8").startswith("{ not json"), (
            "the canonical marker (evidence holder) must also survive"
        )

    def test_failed_recovery_write_stays_fail_closed(self, tmp_path, monkeypatch):
        reg, persist = self._corrupt(tmp_path)
        marker = persist.with_suffix(".corrupt")
        monkeypatch.setattr(ExternalChangeRegistry, "_save", lambda self: False)
        result = reg.recover_from_corrupt()
        assert result["ok"] is False and result["recovered"] is False
        assert reg.is_degraded() is True, "a failed commit may not clear the state"
        assert marker.exists(), "failed recovery must not delete the canonical marker"

    def test_marker_removal_failure_stays_fail_closed_across_restart(
        self, tmp_path, monkeypatch
    ):
        """CORE-001 D: a marker-removal failure after a durable replacement
        commit must remain fail-closed -- this process and the next."""
        reg, persist = self._corrupt(tmp_path)
        marker = persist.with_suffix(".corrupt")

        class _RefuseUnlink(type(marker)):
            def unlink(self, *args, **kwargs):
                raise OSError("injected marker-removal failure")

        monkeypatch.setattr(
            ExternalChangeRegistry,
            "_corrupt_marker",
            lambda self: _RefuseUnlink(marker),
        )
        result = reg.recover_from_corrupt()
        assert result["ok"] is False and result["recovered"] is False
        assert persist.exists(), "the replacement generation may exist"
        assert reg.load_untrusted() is True, "recovery must report degraded"

        fresh = ExternalChangeRegistry()
        fresh._set_persist_path(persist)
        assert fresh.is_degraded() is True, (
            "a restart must still classify the state as degraded"
        )

    def test_recovery_on_a_healthy_registry_is_a_no_op(self, tmp_path):
        reg = ExternalChangeRegistry()
        reg._set_persist_path(tmp_path / "clean.json")
        result = reg.recover_from_corrupt()
        assert result["ok"] is True and result["recovered"] is False


# ── R007 / W2-003: persisted rows must satisfy the registry's invariants ──────


class TestPersistedRowValidation:
    def _load(self, tmp_path: Path, row: dict, next_token: int = 5):
        persist = tmp_path / "ec.json"
        persist.write_text(
            json.dumps({"next_token": next_token, "entries": [row]}), encoding="utf-8"
        )
        reg = ExternalChangeRegistry()
        reg._set_persist_path(persist)
        return reg, persist

    def _valid_row(self) -> dict:
        return {
            "root": "v:\\some\\project",
            "path": ".saipen/STATE.md",
            "fingerprint": "deadbeef",
            "status": "unresolved",
            "observed_at": 1.0,
            "token": 5,
        }

    def test_valid_row_still_loads_trusted(self, tmp_path):
        reg, _ = self._load(tmp_path, self._valid_row())
        assert reg.is_degraded() is False
        assert len(reg.unresolved("v:\\some\\project")) == 1

    @pytest.mark.parametrize(
        "mutation",
        [
            {"status": "garbage"},
            {"status": "acknowledged"},
            {"path": "../STATE.md"},
            {"path": ".saipen\\STATE.md"},
            {"root": "v:\\some\\project\\.."},
            {"root": "V:\\Some\\Project"},
            {"observed_at": "not-a-number"},
            {"token": "not-an-int"},
            {"token": True},
            {"fingerprint": ""},
        ],
        ids=[
            "unknown-status",
            "nonpersistable-status",
            "traversal-path",
            "backslash-path",
            "noncanonical-root",
            "uppercase-root",
            "nonnumeric-observed_at",
            "nonint-token",
            "bool-token",
            "empty-fingerprint",
        ],
    )
    def test_semantic_violation_fails_closed(self, tmp_path, mutation):
        row = self._valid_row()
        row.update(mutation)
        reg, persist = self._load(tmp_path, row)
        assert reg.is_degraded() is True, f"{mutation} loaded as trusted"
        assert reg.load_untrusted() is True
        assert persist.with_suffix(".corrupt").exists(), "evidence not preserved"
        assert reg.pending() == [], "a rejected snapshot may not load partially"

    def test_duplicate_key_fails_closed(self, tmp_path):
        row = self._valid_row()
        persist = tmp_path / "ec.json"
        persist.write_text(
            json.dumps({"next_token": 5, "entries": [row, dict(row)]}),
            encoding="utf-8",
        )
        reg = ExternalChangeRegistry()
        reg._set_persist_path(persist)
        assert reg.is_degraded() is True


# ── R003 / CORE-003: teardown owns only its own subscriptions ────────────────


class TestTeardownSubscriptionOwnership:
    def test_stop_does_not_clear_foreign_subscribers(self, tmp_path):
        from saipenview.events import event_bus

        received: list[dict] = []
        foreign = received.append
        event_bus.subscribe("agent.finished", foreign)
        try:
            a = Api()
            a.start()
            a.stop()
            event_bus.publish("agent.finished", {"root": "x"})
            assert received, (
                "Api.stop() cleared a subscription it never owned -- the bus is "
                "a process-global singleton"
            )
        finally:
            event_bus.unsubscribe("agent.finished", foreign)

    def test_stop_removes_its_own_wrapper_and_restart_binds_exactly_one(self, tmp_path):
        from saipenview.events import event_bus

        def count() -> int:
            return len(event_bus._subscribers.get("saipen.project_changed", []))

        before = count()
        a = Api()
        try:
            a.start()
            assert count() == before + 1
            a.stop()
            assert count() == before, "own wrapper not unsubscribed"
            a.start()
            assert count() == before + 1, "restart must bind exactly one wrapper"
        finally:
            a.stop()


# ── R005 / W2-001: one authority, one key ────────────────────────────────────


class TestCanonicalAuthorityIdentity:
    def test_home_key_collapses_case_and_separator_aliases(self):
        from saipenview.saio import _home_key

        variants = [
            r"C:\Users\x\.agents\skills\saipen",
            r"c:\users\x\.agents\skills\saipen",
            r"C:/Users/x/.agents/skills/saipen",
            r"C:\Users\x\.agents\skills\saipen\.",
        ]
        assert len({_home_key(v) for v in variants}) == 1

    def test_the_loaders_agree_on_one_cache_entry_per_home(self, tmp_path):
        from saipenview import saio

        home = tmp_path / "MixedCaseHome"
        (home / "tools" / "saipen_engine").mkdir(parents=True)
        (home / "tools" / "saipen_engine" / "__init__.py").write_text("", encoding="utf-8")
        (home / "tools" / "freshness.py").write_text("VALUE = 1\n", encoding="utf-8")

        saved = dict(saio._ENGINE_CACHE)
        saio._ENGINE_CACHE.clear()
        try:
            saio._load_freshness_from(home)
            saio._load_freshness_from(Path(str(home).lower()))
            assert len(saio._ENGINE_CACHE) == 1, (
                f"one home produced {len(saio._ENGINE_CACHE)} cache entries: "
                f"{list(saio._ENGINE_CACHE)}"
            )
        finally:
            saio._ENGINE_CACHE.clear()
            saio._ENGINE_CACHE.update(saved)

    def test_a_distinct_second_home_is_refused_fail_closed(self, tmp_path):
        from saipenview import saio
        from saipenview.saio import SaioUnavailable

        saved = dict(saio._ENGINE_CACHE)
        saio._ENGINE_CACHE.clear()
        try:
            saio._ENGINE_CACHE[saio._home_key(tmp_path / "home_a")] = {"operations": object()}
            with pytest.raises(SaioUnavailable):
                saio._load_freshness_from(tmp_path / "home_b")
            with pytest.raises(SaioUnavailable):
                saio._load_codec_from(tmp_path / "home_b")
        finally:
            saio._ENGINE_CACHE.clear()
            saio._ENGINE_CACHE.update(saved)

    def test_the_authority_loader_is_serialized(self):
        from saipenview import saio

        assert isinstance(saio._ENGINE_LOCK, type(threading.RLock()))


# ── R006 / W2-002: stop is a barrier, not a doorbell ─────────────────────────


class TestStopIsABarrier:
    def test_generation_bumped_mid_refresh_blocks_the_js_push(self, tmp_path, monkeypatch):
        proj = _project(tmp_path)
        a = Api(debounce_delay=0)
        window = MagicMock()
        try:
            a._projects = [_row(proj)]
            a._window = window
            gen = a._stop_gen
            a._root_refresh_files[str(proj)] = {"STATE.md": "external"}

            def refresh_then_stop(root, changed=None):
                # Exactly what stop() does first: invalidate the generation.
                a._stop_gen += 1

            monkeypatch.setattr(a, "_refresh_one_project", refresh_then_stop)
            a._do_root_refresh(str(proj), gen)
            assert window.evaluate_js.call_count == 0, (
                "a callback whose generation died mid-flight pushed into the window"
            )
        finally:
            a.stop()

    def test_generation_bumped_before_refresh_blocks_the_cache_mutation(
        self, tmp_path, monkeypatch
    ):
        proj = _project(tmp_path)
        a = Api(debounce_delay=0)
        try:
            a._projects = [_row(proj)]
            gen = a._stop_gen
            a._root_refresh_files[str(proj)] = {"STATE.md": "external"}
            calls = {"n": 0}
            monkeypatch.setattr(
                a,
                "_refresh_one_project",
                lambda *args, **kwargs: calls.__setitem__("n", calls["n"] + 1),
            )
            a._stop_gen += 1
            a._do_root_refresh(str(proj), gen)
            assert calls["n"] == 0
        finally:
            a.stop()

    def test_generation_dying_while_the_refresh_lock_is_held_blocks_the_reparse(
        self, tmp_path, monkeypatch
    ):
        """The real race: stop() lands AFTER the entry check.

        `stop()` bumps `_stop_gen` first and only then cancels timers, so a
        callback sitting on `_root_refresh_lock` has already passed the entry
        check when its generation dies. Without a recheck it went on to reparse
        and publish into a stopped (or restarted) lifecycle.
        """
        proj = _project(tmp_path)
        a = Api(debounce_delay=0)
        try:
            a._projects = [_row(proj)]
            gen = a._stop_gen

            class _StopWhileLocked(dict):
                def pop(self, key, default=None):
                    a._stop_gen += 1  # exactly what stop() does first
                    return super().pop(key, default)

            a._root_refresh_files = _StopWhileLocked(
                {str(proj): {"STATE.md": "external"}}
            )
            calls = {"n": 0}
            monkeypatch.setattr(
                a,
                "_refresh_one_project",
                lambda *args, **kwargs: calls.__setitem__("n", calls["n"] + 1),
            )
            a._do_root_refresh(str(proj), gen)
            assert calls["n"] == 0, (
                "the callback reparsed after its generation died mid-flight"
            )
        finally:
            a.stop()

    def test_a_watch_scheduled_after_stop_is_not_committed(self, tmp_path):
        from saipenview.watcher import SaipenWatcher

        proj = _project(tmp_path)
        w = SaipenWatcher(debounce_delay=0)
        try:
            gen = w._life_gen
            w.stop()
            # A sync that captured `gen` before stop() must refuse to publish.
            w._watch_project_fallback(str(proj), gen)
            assert w._fallback_projects == {}, "topology resurrected after stop()"
            assert w._handlers == {}
        finally:
            w.stop()

    def test_a_scan_root_watch_scheduled_after_stop_is_not_committed(self, tmp_path):
        from saipenview.watcher import SaipenWatcher

        proj = _project(tmp_path)
        w = SaipenWatcher(debounce_delay=0)
        try:
            gen = w._life_gen
            w.stop()
            # `Observer.schedule` can return after stop() already cleared the
            # maps; publishing then would resurrect topology on a dead Observer.
            w._watch_scan_root(str(tmp_path), [str(proj)], gen)
            assert w._watches == {}, "scan-root topology resurrected after stop()"
            assert w._root_router == {}
            assert w._project_to_scope == {}
            assert w._handlers == {}
        finally:
            w.stop()

    def test_revive_invalidates_an_in_flight_sync_generation(self, tmp_path):
        from saipenview.watcher import SaipenWatcher

        proj = _project(tmp_path)
        w = SaipenWatcher(debounce_delay=0)
        try:
            gen = w._life_gen
            w.stop()
            w.revive()
            w._watch_project_fallback(str(proj), gen)
            assert w._fallback_projects == {}, (
                "a generation captured before revive() belongs to the dead Observer"
            )
        finally:
            w.stop()

    def test_normal_sync_still_watches(self, tmp_path):
        from saipenview.watcher import SaipenWatcher

        proj = _project(tmp_path)
        w = SaipenWatcher(debounce_delay=0)
        try:
            w.sync([str(proj)])
            assert str(proj) in w._fallback_projects
            w.sync([])
            assert w._fallback_projects == {}
        finally:
            w.stop()


# ── R008 / W2-004: the hotkey rollback contract ──────────────────────────────


class TestHotkeyBindingRollback:
    def test_import_error_rolls_back_runtime_live_and_disk(self, tmp_path):
        from saipenview.config import load_config

        seen: list[list[str]] = []

        def binder(hotkeys):
            seen.append(list(hotkeys))
            if hotkeys == ["ctrl+alt+z"]:
                raise ImportError("keyboard backend unavailable")

        a = Api(on_hotkeys_changed=binder)
        try:
            previous = list(a._config["hotkeys"])
            result = a.set_hotkeys(["ctrl+alt+z"])
            assert result.get("ok") is False, f"no ok:false contract: {result}"
            assert a._config["hotkeys"] == previous, "live config not reverted"
            assert load_config()["hotkeys"] == previous, "disk not reverted"
            assert seen[-1] == previous, (
                "rollback must rebind the PREVIOUS hotkeys, not leave the "
                "listener on a set nothing claims"
            )
        finally:
            a.stop()

    def test_value_error_rollback_is_preserved(self, tmp_path):
        def binder(hotkeys):
            if hotkeys == ["ctrl+alt+z"]:
                raise ValueError("not a hotkey")

        a = Api(on_hotkeys_changed=binder)
        try:
            previous = list(a._config["hotkeys"])
            result = a.set_hotkeys(["ctrl+alt+z"])
            assert result.get("ok") is False
            assert a._config["hotkeys"] == previous
        finally:
            a.stop()

    def test_successful_binding_still_commits(self, tmp_path):
        a = Api(on_hotkeys_changed=lambda hotkeys: None)
        try:
            result = a.set_hotkeys(["ctrl+alt+j"])
            assert result.get("ok") is not False
            assert a._config["hotkeys"] == ["ctrl+alt+j"]
        finally:
            a.stop()


# ── R011 / PERF-003: the ticket index follows authoritative removal ──────────


class TestTicketIndexReconciliation:
    def test_full_scan_removal_evicts_the_ticket_index(self, tmp_path):
        proj = _project(tmp_path)
        a = Api()
        try:
            a._projects = [_row(proj)]
            a._has_scanned = True
            a._ticket_index[str(proj)] = [
                {"id": "T-1", "desc": "probe", "section": "TODO"}
            ]
            a._set_cache(
                ScanOutcome(
                    projects=[],
                    worktrees=[],
                    complete=True,
                    completed_roots=[str(tmp_path)],
                    unresolved_roots=[],
                )
            )
            assert a._projects == []
            assert str(proj) not in a._ticket_index, (
                "an authoritatively removed root kept its whole ticket payload, "
                "and quick_search kept answering from it"
            )
            assert set(a._ticket_index) <= {p["root"] for p in a._projects}
        finally:
            a.stop()

    def test_partial_scan_preserves_an_unresolved_root(self, tmp_path):
        proj = _project(tmp_path)
        a = Api()
        try:
            a._projects = [_row(proj)]
            a._has_scanned = True
            a._ticket_index[str(proj)] = [
                {"id": "T-1", "desc": "probe", "section": "TODO"}
            ]
            a._set_cache(
                ScanOutcome(
                    projects=[],
                    worktrees=[],
                    complete=False,
                    completed_roots=[],
                    unresolved_roots=[str(tmp_path)],
                )
            )
            assert [p["root"] for p in a._projects] == [str(proj)], (
                "an unresolved scan root must not drop its rows"
            )
            assert a._ticket_index.get(str(proj)), (
                "an incomplete scan must not erase ticket data"
            )
        finally:
            a.stop()


# ── R004 / CORE-004: the truncation regression is clock-independent ──────────


def _frozen_clock(fake_now: datetime.datetime):
    """A datetime whose now() always answers *fake_now*.

    Bound through a default argument rather than a closure over a loop
    variable: a closure would share the LAST simulated instant across every
    iteration, which is exactly the silent-wrong-answer shape this file exists
    to prevent.
    """
    real_datetime = datetime.datetime

    class _FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None, _fixed=fake_now):  # type: ignore[override]
            return _fixed if tz is None else _fixed.astimezone(tz)

    return _FrozenDatetime


@pytest.mark.parametrize("simulated_year", (2031, 2044))
def test_future_stamp_grading_is_calendar_independent(
    tmp_path, monkeypatch, simulated_year: int
):
    """The same derivation must produce future findings at any simulated date.

    The repaired fixture derives its stamps from the clock; this pins the
    property the old hard-coded `30.08.26 23:59` could not have: move "now"
    years away and the grade is unchanged.
    """
    from saipenview import conformance, protocol

    fake_now = datetime.datetime(simulated_year, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    stamp = (
        fake_now + datetime.timedelta(seconds=protocol.LOG_CLOCK_SLACK_SECONDS + 86400)
    ).strftime("%d.%m.%y %H:%M")
    root = tmp_path / f"p{simulated_year}"
    (root / ".saipen").mkdir(parents=True)
    log = root / ".saipen" / "LOG.md"
    log.write_text(
        "# Log\n"
        + "".join(
            f"- {stamp} [E-{i:03d}]"
            + (f" [parent: E-{i - 1:03d}]" if i > 1 else "")
            + f" DEC: future {i}\n"
            for i in range(1, 121)
        ),
        encoding="utf-8",
    )
    conformance._LOG_CACHE.clear()
    monkeypatch.setattr(conformance.datetime, "datetime", _frozen_clock(fake_now))
    try:
        aggregate = conformance._log_aggregate(root, (log,), log)
    finally:
        monkeypatch.undo()
        conformance._LOG_CACHE.clear()
    assert len(aggregate.future) == 120, (
        f"at simulated {simulated_year} only {len(aggregate.future)} of 120 "
        "stamps counted as future"
    )
