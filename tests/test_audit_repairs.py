"""Regression guards for the post-audit integration repairs."""

from __future__ import annotations

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
    monkeypatch.setattr(saio, "snapshot", lambda _root, _rels: {".saipen/STATE.md": fake_doc})
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
    """A second distinct home must be refused before global import contamination."""
    home_a = tmp_path / "A"
    home_b = tmp_path / "B"
    for home in (home_a, home_b):
        (home / "tools" / "saipen_engine").mkdir(parents=True)
        (home / "tools" / "freshness.py").write_text("VALUE = 1\n", encoding="utf-8")
        (home / "VERSION").write_text("1\n", encoding="utf-8")

    monkeypatch.setattr(saio, "_ENGINE_CACHE", {})
    # Load from home_a first to populate the engine cache.
    saio._load_freshness_from(home_a)  # type: ignore[attr-defined]
    # Now try to load from a DIFFERENT home -- must be refused.
    try:
        saio._load_freshness_from(home_b)  # type: ignore[attr-defined]
    except saio.SaioUnavailable as exc:
        assert "MULTI-HOME" in str(exc)
    else:
        raise AssertionError("distinct freshness home was not refused")
