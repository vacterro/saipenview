"""Regression guards for the post-audit integration repairs."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from saipenview import saio
from saipenview.protocol_write import WriteCoordinator


def test_state_authority_is_bounded_to_closed_frontmatter():
    fields, errors = saio._strict_frontmatter(  # type: ignore[attr-defined]
        "---\nagent: core-a\nsaipen_home: A\n---\nagent: evil\nsaipen_home: B\n"
    )
    assert not errors
    assert fields["agent"] == "core-a"
    assert fields["saipen_home"] == "A"

    _fields, errors = saio._strict_frontmatter("---\nagent: core-a\n")  # type: ignore[attr-defined]
    assert errors == ["missing closing frontmatter delimiter"]

    _fields, errors = saio._strict_frontmatter(  # type: ignore[attr-defined]
        "---\nagent: a\nagent: b\n---\n"
    )
    assert "duplicate authority key 'agent'" in errors


def test_mutate_doc_rejects_stale_editor_version_before_planning(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    path = root / ".saipen" / "STATE.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nagent: a\n---\n", encoding="utf-8")
    coord = WriteCoordinator()

    fake_doc = SimpleNamespace(raw_hash="new-hash", text_norm="new bytes")
    monkeypatch.setattr(
        saio, "snapshot", lambda _root, _rels: {".saipen/STATE.md": fake_doc}
    )
    monkeypatch.setattr(
        coord,
        "mutate",
        lambda r, planner, **_kw: planner(r, 0),
    )

    result = coord.mutate_doc(
        path,
        lambda _text: "stale replacement",
        stale_retry=False,
        expected_raw_hash="old-hash",
    )
    assert result["ok"] is False
    assert result["code"] == "STALE_STATE"


def test_freshness_loader_uses_same_normalized_home_identity(tmp_path, monkeypatch):
    """Distinct homes get DISTINCT modules, and neither leaks under a global name.

    T-893 replaced the old assertion here. This test used to require the
    second home to be REFUSED outright -- which was IMP-003 itself: one viewer
    process could serve exactly one SAIPEN home, permanently, decided by which
    project was opened first. `tools/freshness.py` imports nothing from
    saipen_engine, so each home now loads under its own name; what must still be
    impossible is a bare `freshness` in sys.modules pointing at whichever home
    got there first."""
    home_a = tmp_path / "A"
    home_b = tmp_path / "B"
    for home in (home_a, home_b):
        (home / "tools" / "saipen_engine").mkdir(parents=True)
        (home / "tools" / "freshness.py").write_text(
            f"VALUE = {1 if home is home_a else 2}\n", encoding="utf-8"
        )
        (home / "VERSION").write_text("1\n", encoding="utf-8")

    monkeypatch.setattr(saio, "_ENGINE_CACHE", {})
    saved_modules = dict(sys.modules)
    saved_path = list(sys.path)
    try:
        mod_a = saio._load_freshness_from(home_a)  # type: ignore[attr-defined]
        mod_b = saio._load_freshness_from(home_b)  # type: ignore[attr-defined]

        assert mod_a is not mod_b
        assert (mod_a.VALUE, mod_b.VALUE) == (1, 2)
        # Same home key -> same object, so the cache still de-duplicates.
        assert saio._load_freshness_from(home_a) is mod_a  # type: ignore[attr-defined]
        # These fixtures carry a distinct VALUE, so a module shared with any
        # other home would answer with the wrong one. (A bare `freshness` entry
        # may exist: engine() binds that name for the WRITER home. It must not
        # be what this loader hands back.)
        for mod, value in ((mod_a, 1), (mod_b, 2)):
            assert mod.VALUE == value
    finally:
        # The stub modules and the tmp tools/ dirs must NOT leak into the
        # process: a later saio.source_identity() would hit a stub and crash
        # with AttributeError. Restore the exact pre-test state.
        sys.modules.clear()
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path
