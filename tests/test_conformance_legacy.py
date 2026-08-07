"""T-187: the conformance legacy policy stays explicit, bounded and testable.

The policy (docs/conformance-legacy.md) grandfathers pre-cutoff history with
three documented treatments. These tests pin that the migration did NOT turn
off the underlying rules: a NEW skeleton violation or a NEW DONE ticket without
verify must still FAIL the canonical validator, and SAIPENVIEW's own `.saipen/`
memory must stay conformant.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _validator() -> Path | None:
    """Locate the canonical tools/validate.py.

    Resolution order: the SAIPEN_HOME env var (set by CI, which clones the
    protocol repo), then this project's STATE.md saipen_home."""
    env = Path(os.environ["SAIPEN_HOME"]) if os.environ.get("SAIPEN_HOME") else None
    if env:
        v = env / "tools" / "validate.py"
        if v.is_file():
            return v
    state = ROOT / ".saipen" / "STATE.md"
    if not state.is_file():
        return None
    for line in state.read_text(encoding="utf-8").splitlines():
        if line.startswith("saipen_home:"):
            home = line.split(":", 1)[1].strip().strip("'\"")
            v = Path(home) / "tools" / "validate.py"
            return v if v.is_file() else None
    return None


def _run_validator(target: Path) -> str:
    v = _validator()
    assert v is not None, "canonical validator not reachable (no saipen_home)"
    r = subprocess.run(
        [sys.executable, str(v), "--project-root", str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    return r.stdout + r.stderr


def _minimal_project(tmp_path) -> Path:
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nschema_version: 3\nphase: DONE\n"
        "transition_from: SHIP\ntask: none\n"
        'next_action: "PHASE HUNT T-none"\nblocker: none\n'
        "agent: t\nsaipen_version: 7\nmode: full\n"
        "execution_intent: normal\n"
        "updated: 2026-08-07T00:00:00Z\nlast_event: 1\n"
        "style_contract: ded-4ae736e4\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
        encoding="utf-8",
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 00:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    return root


_HAS_LOCAL_MEMORY = (ROOT / ".saipen" / "BOARD.md").is_file()


@pytest.mark.skipif(
    _validator() is None, reason="canonical validator not reachable (no saipen_home)"
)
def test_new_skeleton_violation_still_fails(tmp_path):
    root = _minimal_project(tmp_path)
    (root / ".saipen" / "LOG.md").write_text(
        "2026-08-01T12:48:30Z [E-2] | RUN: bad old-format line\n"
        "- 07.08.26 00:00 [E-1] RUN: boot\n",
        encoding="utf-8",
    )
    out = _run_validator(root)
    assert "violates the Event Graph skeleton" in out, out


@pytest.mark.skipif(
    _validator() is None, reason="canonical validator not reachable (no saipen_home)"
)
def test_new_done_ticket_without_verify_still_fails(tmp_path):
    root = _minimal_project(tmp_path)
    (root / ".saipen" / "BOARD.md").write_text(
        "# BOARD\n## TODO\n\n## DOING\n\n## DONE\n- [x] T-001 new work\n## BLOCKED\n",
        encoding="utf-8",
    )
    out = _run_validator(root)
    assert "sits under ## DONE with no | verify:" in out, out


@pytest.mark.skipif(
    _validator() is None, reason="canonical validator not reachable (no saipen_home)"
)
@pytest.mark.skipif(
    not _HAS_LOCAL_MEMORY,
    reason="own .saipen memory is local-only by contract (T-172); absent in CI checkouts",
)
def test_own_saipen_memory_is_conformant():
    out = _run_validator(ROOT)
    assert "Validation FAILED" not in out, (
        "SAIPENVIEW's own .saipen memory is non-conformant:\n" + out
    )
    assert "Agent is conformant" in out, out


def test_legacy_policy_doc_exists_and_names_a_cutoff():
    doc = ROOT / "docs" / "conformance-legacy.md"
    assert doc.is_file(), "legacy policy doc missing"
    text = doc.read_text(encoding="utf-8")
    assert "02.08.26 07:00" in text, "policy must name an explicit cutoff"
    assert "grandfathered" in text


@pytest.mark.skipif(
    not _HAS_LOCAL_MEMORY,
    reason="own .saipen memory is local-only by contract (T-172); absent in CI checkouts",
)
def test_grandfathered_marker_is_uniform():
    board = (ROOT / ".saipen" / "BOARD.md").read_text(encoding="utf-8")
    import re

    markers = re.findall(r"\| verify: grandfathered [^\n]+", board)
    assert markers, "no grandfathered markers found"
    distinct = set(markers)
    assert len(distinct) == 1, f"markers drifted: {distinct}"
    assert "docs/conformance-legacy.md" in markers[0]
