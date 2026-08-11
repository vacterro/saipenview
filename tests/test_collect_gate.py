"""The collect gate must agree with the canonical SAIPEN package validity.

The viewer does not maintain a second partial idea of "what is current": its
source-identity and role-revision computations are direct ports of
tools/freshness.py, and its `status: ready` gate mirrors tools/validate.py's
`--gate collect:<producer>`. This file proves the two implementations agree
byte-for-byte on the same trees and verdict-for-verdict on the same packages.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import make_ready_outbox

from saipenview import collect
from saipenview.parser import parse_outbox

ROOT = Path(__file__).resolve().parent.parent


def _saipen_home() -> Path | None:
    env = Path(os.environ["SAIPEN_HOME"]) if os.environ.get("SAIPEN_HOME") else None
    if env and (env / "tools" / "validate.py").is_file():
        return env
    state = ROOT / ".saipen" / "STATE.md"
    if state.is_file():
        for line in state.read_text(encoding="utf-8").splitlines():
            if line.startswith("saipen_home:"):
                home = Path(line.split(":", 1)[1].strip().strip("'\""))
                return home if (home / "tools" / "validate.py").is_file() else None
    return None


def _load_canonical_freshness(home: Path):
    path = home / "tools" / "freshness.py"
    spec = importlib.util.spec_from_file_location("_canonical_freshness", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _minimal_project(tmp_path) -> Path:
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nschema_version: 3\nphase: DONE\n"
        "transition_from: SHIP\ntask: none\n"
        'next_action: "saipen continue"\nblocker: none\n'
        "agent: t\nsaipen_version: 7\nmode: full\n"
        "execution_intent: normal\n"
        "updated: 2026-08-07T00:00:00Z\nlast_event: 2\n"
        "style_contract: ded-4ae736e4\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
        encoding="utf-8",
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 00:00 [E-1] RUN: boot\n"
        "- 07.08.26 00:01 [E-2] [parent: E-1] RUN: validate.py -> PASS\n",
        encoding="utf-8",
    )
    return root


def _run_canonical_validate(root: Path, home: Path, extra: list[str]) -> str:
    r = subprocess.run(
        [
            sys.executable,
            str(home / "tools" / "validate.py"),
            "--project-root",
            str(root),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(root),
    )
    return r.stdout + r.stderr


class TestSourceIdentityAgreement:
    def test_no_git_tree_fingerprint_matches_canonical(self, tmp_path):
        home = _saipen_home()
        if home is None:
            pytest.skip("canonical SAIPEN repo not reachable")
        canon = _load_canonical_freshness(home)
        root = tmp_path / "proj"
        root.mkdir()
        (root / "a.txt").write_text("alpha\n", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "b.bin").write_bytes(b"\x00\x01\x02")

        ours = collect.compute_source_identity(root)
        theirs = canon.compute_source_identity(root)
        assert ours.source_head == theirs.source_head
        assert ours.source_tree_fingerprint == theirs.source_tree_fingerprint
        assert ours.discovery_model == theirs.discovery_model

    def test_git_tree_fingerprint_matches_canonical(self, tmp_path):
        home = _saipen_home()
        if home is None:
            pytest.skip("canonical SAIPEN repo not reachable")
        canon = _load_canonical_freshness(home)
        root = tmp_path / "repo"
        root.mkdir()
        for c in (
            ["init", "-q"],
            ["config", "user.email", "t@t.t"],
            ["config", "user.name", "t"],
            ["config", "commit.gpgsign", "false"],
        ):
            subprocess.run(["git", "-C", str(root), *c], capture_output=True)
        (root / "a.txt").write_text("a\n", encoding="utf-8")
        (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "a.txt"], capture_output=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "init"], capture_output=True
        )
        (root / "a.txt").write_text("a2\n", encoding="utf-8")  # working-tree delta

        ours = collect.compute_source_identity(root)
        theirs = canon.compute_source_identity(root)
        assert ours.source_head == theirs.source_head
        assert ours.source_tree_fingerprint == theirs.source_tree_fingerprint
        assert ours.source_head  # a real git HEAD, not the no-git sentinel

    def test_role_revision_matches_canonical(self, tmp_path):
        home = _saipen_home()
        if home is None:
            pytest.skip("canonical SAIPEN repo not reachable")
        canon = _load_canonical_freshness(home)
        charter = tmp_path / "saihunt.md"
        charter.write_text(
            "# saihunt charter\n```yaml\nrole_revision: fixture\n```\nbody here\n",
            encoding="utf-8",
        )
        assert collect.compute_role_revision(charter) == canon.compute_role_revision(
            charter
        )


class TestGateAgreementWithCanonicalValidator:
    @pytest.fixture
    def home(self):
        h = _saipen_home()
        if h is None:
            pytest.skip("canonical SAIPEN repo not reachable")
        return h

    def _entry(self, root, sub, entry_id):
        from saipenview.outbox import parse_outbox_strict

        outbox = (
            root / ".saipen" / "extensions" / "subs" / sub / "kitchen" / "OUTBOX.md"
        )
        entries, errors = parse_outbox_strict(outbox.read_text(encoding="utf-8"))
        assert not errors, errors
        return next(e for e in entries if e.entry_id == entry_id)

    def test_ready_package_passes_both(self, tmp_path, home):
        root = _minimal_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")

        entry = self._entry(root, "saihunt", "HUNT-001")
        ok, _msg, kind, proof = collect.check_package(root, "saihunt", entry)
        assert ok is True, _msg
        assert kind == "ready"
        assert proof["source_head"] and proof["source_tree_fingerprint"]

        out = _run_canonical_validate(root, home, ["--gate", "collect:saihunt"])
        assert "Validation FAILED" not in out, out
        assert "producer gate: saihunt has a ready package" in out, out

    def test_stale_source_head_refused_by_both(self, tmp_path, home):
        root = _minimal_project(tmp_path)
        outbox = make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace(
                "- **source_head:** ", "- **source_head:** deadbeef", 1
            ),
            encoding="utf-8",
        )
        entry = next(
            e
            for e in parse_outbox(outbox.read_text(encoding="utf-8"))
            if e.entry_id == "HUNT-001"
        )
        entry = self._entry(root, "saihunt", "HUNT-001")
        ok, msg, kind, _proof = collect.check_package(root, "saihunt", entry)
        assert ok is False and kind == "stale"

        out = _run_canonical_validate(root, home, ["--gate", "collect:saihunt"])
        assert "source_head" in out and "MUST NOT be collected" in out, out

    def test_not_ready_refused_by_both(self, tmp_path, home):
        root = _minimal_project(tmp_path)
        outbox = make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace(
                "- **status:** ready", "- **status:** draft", 1
            ),
            encoding="utf-8",
        )
        entry = self._entry(root, "saihunt", "HUNT-001")
        ok, _msg, kind, _proof = collect.check_package(root, "saihunt", entry)
        assert ok is False and kind == "not-ready"

        out = _run_canonical_validate(root, home, ["--gate", "collect:saihunt"])
        assert "no OUTBOX entry from that producer is `status: ready`" in out, out

    def test_incomplete_package_refused_by_both(self, tmp_path, home):
        root = _minimal_project(tmp_path)
        outbox = make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace(
                "- **verified:** gate fixture\n", ""
            ),
            encoding="utf-8",
        )
        entry = self._entry(root, "saihunt", "HUNT-001")
        ok, _msg, kind, _proof = collect.check_package(root, "saihunt", entry)
        assert ok is False and kind == "incomplete"

        out = _run_canonical_validate(root, home, ["--gate", "collect:saihunt"])
        assert "**verified:**" in out, out
