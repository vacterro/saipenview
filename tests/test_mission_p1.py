"""P1 repair-mission tests: backend external changes, op-id validation,
strict OUTBOX parsing, content-based staleness, typed fingerprint identity."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from conftest import make_conformant_project, make_ready_outbox

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.external_changes import get_registry
from saipenview.outbox import parse_outbox_strict, reviewed_transform
from saipenview.parser import (
    check_subs_staleness,
    collect_outbox_entry,
    record_manual_work,
)
from saipenview.protocol_write import get_coordinator
from saipenview.textio import read_doc


@pytest.fixture(autouse=True)
def _clear_registry():
    reg = get_registry()
    for c in reg.pending():
        reg.acknowledge(c.root, c.rel_path)
    yield
    for c in reg.pending():
        reg.acknowledge(c.root, c.rel_path)


@pytest.fixture
def api(tmp_path) -> Api:
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    with (
        patch("saipenview.api.config_path"),
        patch("saipenview.api.load_config", return_value=cfg),
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner"),
    ):
        api = Api()
        try:
            yield api
        finally:
            api.stop()


# --- #7 backend external-change registry -----------------------------------


def test_external_change_to_hidden_project_is_recorded(api, tmp_path):
    root = make_conformant_project(tmp_path)
    # The change happens while ANOTHER project is selected (no UI state).
    state = root / ".saipen" / "STATE.md"
    state.write_text(read_doc(state) + "# external\n", encoding="utf-8")
    fp = get_coordinator().fingerprint(state)
    get_registry().record(str(root), "STATE.md", fp)
    pending = get_registry().pending(str(root))
    assert len(pending) == 1
    assert pending[0].rel_path == "STATE.md"


def test_multiple_roots_and_files_coexist(api, tmp_path):
    root_a = make_conformant_project(tmp_path / "a")
    root_b = make_conformant_project(tmp_path / "b")
    get_registry().record(str(root_a), "BOARD.md", "fpa")
    get_registry().record(str(root_a), "LOG.md", "fpl")
    get_registry().record(str(root_b), "STATE.md", "fpb")
    assert len(get_registry().pending(str(root_a))) == 2
    assert len(get_registry().pending(str(root_b))) == 1


def test_external_violation_survives_a_later_app_write(api, tmp_path):
    # P1 #8: an external boundary violation is NOT erased by a later app write
    # that happens to produce matching bytes -- only an explicit acknowledge
    # or a verified protocol resolution clears it.
    root = make_conformant_project(tmp_path)
    state = root / ".saipen" / "STATE.md"
    state.write_text(read_doc(state) + "# external\n", encoding="utf-8")
    fp = get_coordinator().fingerprint(state)
    get_registry().record(str(root), "STATE.md", fp)
    # A later write (even byte-identical content) does not clear it.
    state.write_text(read_doc(state) + "# external\n", encoding="utf-8")
    assert len(get_registry().pending(str(root))) == 1
    assert get_registry().unresolved(str(root))
    # Explicit acknowledge clears it.
    assert get_registry().acknowledge(str(root), "STATE.md") is True
    assert get_registry().pending(str(root)) == []


def test_registry_keys_are_canonicalized(tmp_path):
    root = make_conformant_project(tmp_path)
    # Case / slash variants of the SAME root+file are ONE key.
    get_registry().record(str(root), "STATE.md", "fp1")
    root_lower = str(root).lower()
    assert len(get_registry().pending(root_lower)) == 1
    assert get_registry().acknowledge(root_lower, "STATE.md") is True
    # Forward/backslash variants are one key.
    get_registry().record(
        str(root), r"extensions\subs\saihunt\kitchen\OUTBOX.md", "fp2"
    )
    assert len(get_registry().pending(str(root))) == 1
    assert get_registry().pending(str(root))[0].rel_path == (
        "extensions/subs/saihunt/kitchen/OUTBOX.md"
    )
    assert (
        get_registry().acknowledge(
            str(root), "extensions/subs/saihunt/kitchen/OUTBOX.md"
        )
        is True
    )


@pytest.mark.parametrize(
    "bad",
    [
        "/absolute/path.md",
        "C:/absolute.md",
        "../escape.md",
        "a/../b.md",
        "./leading.md",
    ],
)
def test_registry_rejects_invalid_rel_paths(tmp_path, bad):
    from saipenview.external_changes import ExternalChangeRegistry, normalize_rel

    with pytest.raises(ValueError):
        normalize_rel(bad)
    root = make_conformant_project(tmp_path)
    with pytest.raises(ValueError):
        ExternalChangeRegistry().record(str(root), bad, "fp")


def test_collect_blocked_by_unresolved_external_change(tmp_path):
    root = make_conformant_project(tmp_path)
    make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")
    # An unexplained external edit to the main BOARD.md blocks collect.
    board = root / ".saipen" / "BOARD.md"
    board.write_text(read_doc(board) + "# stray\n", encoding="utf-8")
    get_registry().record(str(root), "BOARD.md", get_coordinator().fingerprint(board))
    res = collect_outbox_entry(root, "saihunt", "HUNT-001")
    assert res["ok"] is False
    assert res["code"] == "BOUNDARY_VIOLATION", res
    assert "HUNT-001" not in read_doc(board)


# --- #2/#3 self-write attribution through the real watcher path -------------


def _origin(api, root, file) -> str:
    """Simulate the watcher firing for a changed file; return the origin.
    `file` is relative to `.saipen/` (the watcher's own contract)."""
    pushed = {}
    api._debounce_delay = 0  # CORE-005: force synchronous publish
    api._window = type(
        "W", (), {"evaluate_js": lambda self, s: pushed.setdefault("js", s)}
    )()
    with patch.object(api, "_refresh_one_project"):
        api._on_file_changed({"root": str(root), "file": file})
    return "self" if pushed.get("js") and '"self"' in pushed["js"] else "external"


def test_mutate_doc_watcher_event_is_self(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    board = root / ".saipen" / "BOARD.md"
    res = get_coordinator().mutate_doc(
        board, lambda t: t.replace("## TODO\n", "## TODO\n- [ ] T-099 x\n", 1)
    )
    assert res.get("ok") is True, res
    assert _origin(api, root, "BOARD.md") == "self"
    # An unrelated file the app did NOT write reports external.
    state = root / ".saipen" / "STATE.md"
    state.write_text(read_doc(state) + "# ext\n", encoding="utf-8")
    assert _origin(api, root, "STATE.md") == "external"


def test_collect_watcher_events_all_self(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")
    res = collect_outbox_entry(root, "saihunt", "HUNT-001")
    assert res.get("ok") is True, res
    # EVERY written protocol file of the collect is attributed to the app.
    # The watcher's `file` is relative to `.saipen/`.
    for rel in res.get("changed_files", []):
        watcher_rel = rel[len(".saipen/") :]
        assert _origin(api, root, watcher_rel) == "self", f"{rel} not attributed self"


def test_registry_empty_after_own_transaction(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    res = record_manual_work(root, "own write", operation_id="mw-own-1")
    assert res.get("ok") is True
    assert get_registry().pending(str(root)) == [], (
        "own writes must never poison ExternalChangeRegistry"
    )


def test_external_edit_after_own_write_is_external(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    board = root / ".saipen" / "BOARD.md"
    res = get_coordinator().mutate_doc(
        board, lambda t: t.replace("## TODO\n", "## TODO\n- [ ] T-099 x\n", 1)
    )
    assert res.get("ok") is True, res
    assert _origin(api, root, "BOARD.md") == "self"
    board.write_text(read_doc(board) + "external noise\n", encoding="utf-8")
    assert _origin(api, root, "BOARD.md") == "external"


def test_failed_and_noop_writes_register_nothing(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    board = root / ".saipen" / "BOARD.md"
    # No-op transform -> NOOP, nothing registered.
    noop = get_coordinator().mutate_doc(board, lambda t: t)
    assert noop.get("code") == "NOOP"
    assert get_coordinator().self_writes.consume(str(root), "BOARD.md", "x") is False
    # Failed write (stale baseline) registers nothing.
    def transform(t):
        board.write_text(t + "external", encoding="utf-8")
        return t + "- [ ] T-999 y\n"
    failed = get_coordinator().mutate_doc(
        board, transform, stale_retry=False
    )
    assert failed.get("ok") is False
    assert failed.get("ok") is False
    assert get_coordinator().self_writes.consume(str(root), "BOARD.md", "x") is False


def test_multiple_changed_files_consume_own_fingerprints(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    res = record_manual_work(root, "multi", operation_id="mw-multi-1")
    assert res.get("ok") is True
    coord = get_coordinator()
    for rel in res.get("changed_files", []):
        path = root / rel
        # Each file's OWN post-write fingerprint is consumed; a foreign one is not.
        assert (
            coord.self_writes.consume(str(root), path.name, coord.fingerprint(path))
            is True
        )
        assert coord.self_writes.consume(str(root), path.name, "nope") is False


# --- #8 operation_id end-to-end + validation --------------------------------


def test_api_validates_operation_id(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    bad = api.record_manual_work(str(root), "x", operation_id="bad id!")
    assert bad["ok"] is False
    assert bad["code"] == "INVALID_ID", bad
    ok = api.record_manual_work(str(root), "x", operation_id="mw-ok-1")
    assert ok["ok"] is True
    retry = api.record_manual_work(str(root), "x", operation_id="mw-ok-1")
    assert retry["code"] == "ALREADY_RECORDED", retry
    log = read_doc(root / ".saipen" / "LOG.md")
    assert log.count("[op: mw-ok-1]") == 1
    assert log.count("manual work recorded -- x") == 1


# --- #9/#10/#11 strict OUTBOX parser -----------------------------------------


def test_duplicate_field_is_structural_error():
    text = (
        "# OUTBOX\n\n## HUNT-1: x\n- **status:** ready\n"
        "- **status:** ready\n- **producer:** saihunt\n"
    )
    entries, errors = parse_outbox_strict(text)
    assert errors or entries[0].errors, "duplicate status must be an error"


def test_duplicate_entry_id_is_structural_error():
    text = (
        "# OUTBOX\n\n## HUNT-1: a\n- **status:** ready\n\n"
        "## HUNT-1: b\n- **status:** ready\n"
    )
    entries, errors = parse_outbox_strict(text)
    assert any("duplicate entry id" in e for e in errors), errors


@pytest.mark.parametrize("value", ["yes", "no", "1", "TRUE", "Falsee", "on"])
def test_junk_critical_is_rejected(value):
    text = (
        "# OUTBOX\n\n## HUNT-1: x\n- **status:** ready\n"
        f"- **critical:** {value}\n- **producer:** saihunt\n"
    )
    entries, _errors = parse_outbox_strict(text)
    assert entries[0].errors, f"critical {value!r} must be rejected"


def test_typed_critical():
    text = (
        "# OUTBOX\n\n## HUNT-1: x\n- **status:** ready\n"
        "- **critical:** false\n- **producer:** saihunt\n"
    )
    entries, errors = parse_outbox_strict(text)
    assert not errors and not entries[0].errors
    assert entries[0].critical is False


@pytest.mark.parametrize(
    "spacing",
    [
        "- **status:** ready\n",
        "- **status:**   ready   \n",
        "- **status:**\tready\n",
    ],
)
def test_status_transform_handles_spacing_and_is_exact(tmp_path, spacing):
    from conftest import canonical_home

    home = canonical_home()
    if home is None:
        pytest.skip("canonical home unreachable")
    root = make_conformant_project(tmp_path)
    outbox = root / ".saipen" / "extensions" / "subs" / "saihunt" / "kitchen"
    outbox.mkdir(parents=True, exist_ok=True)
    text = (
        "# OUTBOX\n\n## HUNT-1: doc\n"
        + spacing
        + "- **critical:** true\n- **producer:** saihunt\n"
        "- **summary:** s\n- **source_head:** no-git\n"
        "- **source_tree_fingerprint:** x\n- **role_revision:** y\n"
        "- **coverage:** c\n- **payload:** p\n- **verified:** v\n"
        "- **instructions:** i\n"
    )
    (outbox / "OUTBOX.md").write_text(text, encoding="utf-8")
    flipped = reviewed_transform(text, "HUNT-1")
    assert flipped is not None
    entries, errors = parse_outbox_strict(flipped)
    assert not errors
    assert next(e for e in entries if e.entry_id == "HUNT-1").status == "reviewed"
    # Exactly one replacement: the reviewed token appears once, whitespace
    # tolerance preserved.
    assert flipped.count("reviewed") == 1


def test_status_transform_aborts_on_duplicate_status(tmp_path):
    text = "# OUTBOX\n\n## HUNT-1: x\n- **status:** ready\n- **status:** ready\n"
    assert reviewed_transform(text, "HUNT-1") is None


# --- #12 content-based staleness ---------------------------------------------


def test_staleness_is_content_based(tmp_path):
    # Self-contained: a FAKE canonical root (never the real saipen_home).
    home = tmp_path / "saipen-home"
    (home / "extensions" / "subs").mkdir(parents=True)
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    (saipen / "extensions" / "subs").mkdir(parents=True)
    subs = saipen / "extensions" / "subs"
    canon = home / "extensions" / "subs"
    state = {"saipen_home": str(home)}
    for rel in ("PROTOCOL.md", "README.md", "MANIFEST.md"):
        (subs / rel).write_text("same\n", encoding="utf-8")
        (canon / rel).write_text("same\n", encoding="utf-8")
    stale, _ = check_subs_staleness(root, state)
    assert stale is False
    # False-fresh case: same size + PRESERVED mtime, different bytes.
    for rel in ("PROTOCOL.md", "README.md", "MANIFEST.md"):
        p = subs / rel
        mtime = p.stat().st_mtime
        p.write_text("CHANGED\n", encoding="utf-8")
        os.utime(p, (mtime, mtime))
    stale, details = check_subs_staleness(root, state)
    assert stale is True, "preserved mtime + different bytes read FRESH -- bug"
    assert "content differs" in details
    # False-stale case: identical bytes copied at another time.
    for rel in ("PROTOCOL.md", "README.md", "MANIFEST.md"):
        p = subs / rel
        p.write_text("same\n", encoding="utf-8")
    stale, _ = check_subs_staleness(root, state)
    assert stale is False, "same bytes at a new mtime read STALE -- bug"


# --- #13 typed fingerprint: MISSING != empty ---------------------------------


def test_fingerprint_missing_differs_from_empty(tmp_path):
    root = make_conformant_project(tmp_path)
    coord = get_coordinator()
    missing = root / ".saipen" / "nope.md"
    empty = root / ".saipen" / "empty.md"
    empty.write_text("", encoding="utf-8")
    assert coord.fingerprint(missing) == "MISSING"
    assert (
        coord.fingerprint(empty)
        == "FILE\x00" + __import__("hashlib").sha256(b"").hexdigest()
    )
    assert coord.fingerprint(missing) != coord.fingerprint(empty)


# --- #10 fail closed on duplicate STATE authority keys ----------------------


def test_duplicate_authority_key_refuses_mutation(tmp_path):
    root = make_conformant_project(tmp_path)
    state = root / ".saipen" / "STATE.md"
    # Duplicate the authority-bearing `phase` key.
    state.write_text(
        read_doc(state).replace("phase: DONE\n", "phase: DONE\nphase: HUNT\n", 1),
        encoding="utf-8",
    )
    res = record_manual_work(root, "x", operation_id="mw-dup-1")
    assert res["ok"] is False
    assert res["code"] in ("SAIO_UNAVAILABLE", "VALIDATION_FAILED"), res
    # Nothing was written.
    assert "T-001" not in read_doc(root / ".saipen" / "BOARD.md")


def test_duplicate_saipen_home_refuses_resolution(tmp_path):
    root = make_conformant_project(tmp_path)
    state = root / ".saipen" / "STATE.md"
    text = read_doc(state)
    dup = text.replace("saipen_home:", "saipen_home:\nsaipen_home:", 1)
    state.write_text(dup, encoding="utf-8")
    from saipenview import saio

    with pytest.raises(saio.SaioUnavailable):
        saio.resolve_home(root)
