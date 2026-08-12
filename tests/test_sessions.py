"""Agent transcripts have to outlive the process that produced them.

Before `saipenview/sessions.py`, output lived in a `deque(maxlen=5000)` on the
`AgentProcess` and nowhere else: closing the window, crashing, or rebooting
erased both the transcript and any evidence a run had happened.
"""

from __future__ import annotations

import json
import os

import pytest

from saipenview.sessions import (
    MAX_RUNS_PER_PROJECT,
    MAX_TRANSCRIPT_BYTES,
    SessionStore,
    project_key,
)

ROOT = r"V:\proj\alpha"
OTHER = r"V:\proj\beta"


@pytest.fixture
def store(tmp_path):
    return SessionStore(base_dir=tmp_path / "sessions")


def _run(store, root=ROOT, engine="codex", lines=("one", "two"), status="done", code=0):
    rec = store.start(root, engine, engine.title(), "saipen continue", pid=123)
    for line in lines:
        store.append(rec.run_id, line)
    store.finish(rec.run_id, status, code)
    return rec


class TestProjectKey:
    def test_same_project_reached_differently_is_one_project(self):
        # A project opened as V:\proj and v:/proj/ must not grow two histories.
        assert project_key(r"V:\proj\alpha") == project_key("v:/proj/alpha")
        assert project_key(r"V:\proj\alpha") == project_key(r"V:\proj\alpha\.")

    def test_different_projects_differ(self):
        assert project_key(ROOT) != project_key(OTHER)


class TestRoundTrip:
    def test_transcript_survives_a_new_store_object(self, tmp_path):
        # The point of the whole module: a fresh SessionStore is what a
        # restarted SAIPENVIEW has, and it must still find the run.
        first = SessionStore(base_dir=tmp_path / "s")
        rec = _run(first, lines=("hello", "world"))

        reopened = SessionStore(base_dir=tmp_path / "s")
        body = reopened.transcript(rec.run_id)
        assert body["found"] is True
        assert body["lines"] == ["hello", "world"]

    def test_history_records_the_run(self, store):
        rec = _run(store, lines=("a", "b", "c"))
        hist = store.history(ROOT)
        assert len(hist) == 1
        assert hist[0]["run_id"] == rec.run_id
        assert hist[0]["engine"] == "codex"
        assert hist[0]["status"] == "done"
        assert hist[0]["exit_code"] == 0
        assert hist[0]["line_count"] == 3

    def test_history_is_per_project(self, store):
        _run(store, root=ROOT)
        _run(store, root=OTHER)
        assert len(store.history(ROOT)) == 1
        assert len(store.history(OTHER)) == 1

    def test_last_run_is_the_newest(self, store):
        _run(store, engine="aider")
        newest = _run(store, engine="gemini")
        assert store.last_run(ROOT)["run_id"] == newest.run_id

    def test_last_run_is_none_for_an_unknown_project(self, store):
        assert store.last_run(r"V:\never\ran") is None

    def test_transcript_of_an_unknown_run_reports_not_found(self, store):
        assert store.transcript("no-such-run")["found"] is False


class TestCrashPaths:
    def test_a_run_left_running_reads_as_interrupted(self, tmp_path):
        # SAIPENVIEW died mid-run: the metadata still says "running" and
        # nothing will ever finish it. Reporting that verbatim would show an
        # agent that has been working since Tuesday.
        first = SessionStore(base_dir=tmp_path / "s")
        rec = first.start(ROOT, "codex", "Codex", "saipen continue")
        first.append(rec.run_id, "started")

        reopened = SessionStore(base_dir=tmp_path / "s")
        assert reopened.history(ROOT)[0]["status"] == "interrupted"

    def test_a_live_run_is_not_called_interrupted_by_its_own_store(self, store):
        rec = store.start(ROOT, "codex", "Codex", "saipen continue")
        store.append(rec.run_id, "still going")
        assert store.history(ROOT)[0]["status"] == "running"

    def test_a_corrupt_record_costs_one_run_not_the_history(self, store, tmp_path):
        good = _run(store)
        broken = store._dir / f"20200101T000000-{project_key(ROOT)}-codex.json"
        broken.write_text("{not json", encoding="utf-8")
        hist = store.history(ROOT)
        assert [h["run_id"] for h in hist] == [good.run_id]

    def test_appending_to_a_finished_run_is_ignored(self, store):
        rec = _run(store, lines=("a",))
        store.append(rec.run_id, "late")
        assert store.transcript(rec.run_id)["lines"] == ["a"]

    def test_an_unwritable_directory_does_not_take_down_the_run(self, tmp_path):
        # A file where the sessions directory should be: mkdir fails, start()
        # must return None rather than raise into the launch path.
        blocker = tmp_path / "sessions"
        blocker.write_text("not a directory", encoding="utf-8")
        store = SessionStore(base_dir=blocker)
        assert store.start(ROOT, "codex", "Codex", "go") is None


class TestLimits:
    def test_old_runs_are_pruned(self, store):
        for _ in range(MAX_RUNS_PER_PROJECT + 5):
            _run(store, lines=("x",))
        metas = list(store._dir.glob("*.json"))
        assert len(metas) <= MAX_RUNS_PER_PROJECT

    def test_pruning_removes_the_transcript_too(self, store):
        for _ in range(MAX_RUNS_PER_PROJECT + 3):
            _run(store, lines=("x",))
        assert len(list(store._dir.glob("*.log"))) <= MAX_RUNS_PER_PROJECT

    def test_a_runaway_agent_cannot_fill_the_disk(self, store):
        rec = store.start(ROOT, "codex", "Codex", "go")
        chunk = "y" * 4096
        for _ in range(MAX_TRANSCRIPT_BYTES // len(chunk) + 20):
            store.append(rec.run_id, chunk)
        store.finish(rec.run_id, "done", 0)
        size = (store._dir / f"{rec.run_id}.log").stat().st_size
        assert size < MAX_TRANSCRIPT_BYTES * 1.05
        assert (
            json.loads((store._dir / f"{rec.run_id}.json").read_text(encoding="utf-8"))[
                "truncated"
            ]
            is True
        )

    def test_transcript_tail_is_capped_on_read(self, store):
        rec = store.start(ROOT, "codex", "Codex", "go")
        for i in range(50):
            store.append(rec.run_id, f"line {i}")
        store.finish(rec.run_id, "done", 0)
        body = store.transcript(rec.run_id, max_lines=10)
        assert len(body["lines"]) == 10
        assert body["total"] == 50
        assert body["lines"][-1] == "line 49"

    def test_history_honours_its_limit(self, store):
        for _ in range(5):
            _run(store, lines=("x",))
        assert len(store.history(ROOT, limit=2)) == 2

    def test_runs_started_in_the_same_instant_do_not_collide(self, store, monkeypatch):
        # run_id used to be second-resolution, so two runs in one second shared
        # an id and silently overwrote each other's metadata AND transcript --
        # a goal-mode chain launching back-to-back agents hits that at once.
        import saipenview.sessions as sessions

        frozen = sessions.datetime.now(sessions.timezone.utc)

        class _FrozenClock(sessions.datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen

        monkeypatch.setattr(sessions, "datetime", _FrozenClock)

        first = _run(store, lines=("first",))
        second = _run(store, lines=("second",))
        assert first.run_id != second.run_id
        assert store.transcript(first.run_id)["lines"] == ["first"]
        assert store.transcript(second.run_id)["lines"] == ["second"]
        assert len(store.history(ROOT)) == 2

    def test_identical_started_at_orders_by_creation_not_engine_name(self, store):
        # Regression (T-532): two runs started in the same clock tick tie on
        # started_at, and the old sort key (started_at alone) fell back to the
        # stable _meta_files order -- alphabetical by run_id, so "aider" beat
        # "gemini" even though gemini started second, and last_run returned the
        # older run. Tie-break must be file mtime (creation order).
        first = _run(store, engine="aider")
        second = _run(store, engine="gemini")
        same = first.to_dict()["started_at"]
        for rec in (first, second):
            path = store._dir / f"{rec.run_id}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["started_at"] = same
            path.write_text(json.dumps(data), encoding="utf-8")
            # Rewriting bumps mtime; force the intended creation order back.
            os.utime(path, ns=(1_000_000_000, 1_000_000_000 if rec is first else 2_000_000_000))
        assert store.last_run(ROOT)["run_id"] == second.run_id


class TestUnicode:
    def test_non_ascii_output_round_trips(self, store):
        rec = _run(store, lines=("тест — ok", "日本語", "emoji 🤖"))
        assert store.transcript(rec.run_id)["lines"] == [
            "тест — ok",
            "日本語",
            "emoji 🤖",
        ]
