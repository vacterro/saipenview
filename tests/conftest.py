"""Shared fixtures for SAIPENVIEW test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_leaked_event_bus_subscribers():
    """Any test that leaves a subscriber on the global event bus leaks state
    into every later test -- an Api's _on_file_changed keeps firing on watcher
    events (the T-190/T-179 flake family). Pin it: teardown must return to the
    pre-test subscriber count."""
    from saipenview.events import event_bus

    before = sum(len(v) for v in event_bus._subscribers.values())
    yield
    after = sum(len(v) for v in event_bus._subscribers.values())
    assert after <= before, (
        f"test leaked {after - before} event-bus subscriber(s) into later tests"
    )


# ── Config fixtures ──


@pytest.fixture
def tmp_config_path(tmp_path: Path, monkeypatch) -> Path:
    """Point config_path to a tmp dir so tests never touch real config.

    Uses the ``_CONFIG_PATH_OVERRIDE`` hook in ``saipenview.config``: config_path()
    consults it at *call* time, so every caller -- including modules imported
    lazily during Api() construction (scanner, protocol_write, ProcessManager,
    ...) -- picks up the override. A plain ``monkeypatch.setattr`` of the bound
    ``config_path`` name leaks across tests because those late-imported modules
    capture the patched value at import time and are never re-patched.
    """
    from saipenview import config as cfg_mod

    fake_dir = tmp_path / "_data"
    fake_dir.mkdir(parents=True, exist_ok=True)
    resolved = fake_dir / "config.json"
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH_OVERRIDE", resolved)
    yield resolved



# ── Project structure helpers ──


def _make_saipen_project(
    root: Path,
    phase: str = "DONE",
    task: str = "none",
    next_action: str = "",
    blocker: str = "none",
    board_text: str | None = None,
    log_text: str | None = None,
) -> Path:
    """Create a minimal .saipen/ project under *root* and return the root."""
    saipen = root / ".saipen"
    saipen.mkdir(parents=True, exist_ok=True)

    state = f"""---
phase: {phase}
task: {task}
next_action: "{next_action}"
blocker: {blocker}
---
"""
    (saipen / "STATE.md").write_text(state, encoding="utf-8")

    if board_text is not None:
        (saipen / "BOARD.md").write_text(board_text, encoding="utf-8")
    else:
        (saipen / "BOARD.md").write_text(
            "# BOARD\n\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )

    if log_text is not None:
        (saipen / "LOG.md").write_text(log_text, encoding="utf-8")
    else:
        (saipen / "LOG.md").write_text("# LOG\n\n", encoding="utf-8")

    return root


def _make_sub_project(
    subs_dir: Path,
    name: str,
    phase: str = "INIT",
    task: str = "scouting",
    outbox_text: str | None = None,
) -> Path:
    """Create a sub-agent project under subs_dir."""
    sub = subs_dir / name
    sub.mkdir(parents=True, exist_ok=True)

    state = f"""---
phase: {phase}
task: {task}
next_action: ""
blocker: none
---
"""
    (sub / "STATE.md").write_text(state, encoding="utf-8")

    (sub / "BOARD.md").write_text(
        "# BOARD\n\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (sub / "LOG.md").write_text("# LOG\n\n", encoding="utf-8")

    if outbox_text is not None:
        kitchen = sub / "kitchen"
        kitchen.mkdir(exist_ok=True)
        (kitchen / "OUTBOX.md").write_text(outbox_text, encoding="utf-8")

    return sub


# ── Project fixtures ──


@pytest.fixture
def saipen_project(tmp_path: Path) -> Path:
    """A minimal SAIPEN project at a tmp location."""
    return _make_saipen_project(
        tmp_path / "my-project", phase="PLAN", task="build widget"
    )


@pytest.fixture
def saipen_project_with_board(tmp_path: Path) -> Path:
    """A SAIPEN project with ticket-bearing BOARD.md."""
    board = """# BOARD

## TODO
- [ ] T-001 | First task
- [ ] T-002 | Second task

## DOING
- [/] T-003 | In progress

## DONE
- [x] T-004 | Done task
- [x] T-005 | Another done

## BLOCKED
- [ ] T-006 | Blocked task
"""
    return _make_saipen_project(
        tmp_path / "project-board",
        phase="BUILD",
        task="ticket handling",
        board_text=board,
    )


@pytest.fixture
def saipen_project_with_subs(tmp_path: Path) -> Path:
    """A SAIPEN project with sub-agents and OUTBOX files."""
    root = _make_saipen_project(
        tmp_path / "project-subs", phase="HUNT", task="bug chasing"
    )

    subs_dir = root / ".saipen" / "extensions" / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    (subs_dir / "MANIFEST.md").write_text(
        "- saihunt -- bug-chasing sub\n- saiwiki -- documentation sub\n",
        encoding="utf-8",
    )

    _make_sub_project(
        subs_dir,
        "saihunt",
        phase="HUNT",
        outbox_text="""# OUTBOX

## HUNT-001: null pointer found
- **status:** ready
- **critical:** true
- **severity:** MEDIUM
- **summary:** Found nullable field in parser.py
- **details:** The `parse_frontmatter` function can return an empty dict.
""",
    )

    _make_sub_project(
        subs_dir,
        "saiwiki",
        phase="INIT",
        outbox_text="""# OUTBOX

## WIKI-001: architecture doc
- **status:** draft
- **critical:** false
- **summary:** Wrote architecture overview
""",
    )

    return root


@pytest.fixture
def saipen_project_with_subs_noncritical(tmp_path: Path) -> Path:
    """A SAIPEN project with a non-critical ready OUTBOX entry."""
    root = _make_saipen_project(
        tmp_path / "project-noncrit", phase="BUILD", task="fixes"
    )

    subs_dir = root / ".saipen" / "extensions" / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    (subs_dir / "MANIFEST.md").write_text(
        "- saihunt -- bug-chasing sub\n", encoding="utf-8"
    )
    (subs_dir / "_shared").mkdir(parents=True, exist_ok=True)

    _make_sub_project(
        subs_dir,
        "saihunt",
        phase="HUNT",
        outbox_text="""# OUTBOX

## HUNT-002: minor lint issue
- **status:** ready
- **critical:** false
- **severity:** LOW
- **summary:** Unused import in test file
""",
    )

    return root


@pytest.fixture
def saipen_project_with_translate(tmp_path: Path) -> Path:
    """A SAIPEN project with an external saitranslate sub (legacy path)."""
    root = _make_saipen_project(
        tmp_path / "project-translate", phase="DONE", task="shipped"
    )

    translate_dir = root / ".saitranslate"
    translate_dir.mkdir(parents=True, exist_ok=True)
    (translate_dir / "STATE.md").write_text(
        "---\nphase: TRANSLATE\ntask: translating docs\n---\n", encoding="utf-8"
    )
    (translate_dir / "BOARD.md").write_text(
        "# BOARD\n\n## TODO\n\n## DONE\n\n", encoding="utf-8"
    )
    (translate_dir / "LOG.md").write_text("# LOG\n\n", encoding="utf-8")

    return root


@pytest.fixture
def saipen_project_with_staleness(tmp_path: Path) -> Path:
    """A SAIPEN project with saipen_home set for staleness checks.

    Creates canonical and local subs/ files with IDENTICAL mtime/size by
    writing them in the same batch before any time delay can occur.
    """
    root = _make_saipen_project(
        tmp_path / "project-stale",
        phase="PLAN",
        task="review",
        next_action="check stale status",
    )

    # Use a subfolder of tmp_path for saipen_home
    saipen_home = tmp_path / "saipen-home"
    saipen_home.mkdir(parents=True, exist_ok=True)

    # Write saipen_home into STATE.md
    state_path = root / ".saipen" / "STATE.md"
    state_path.write_text(
        f"---\nphase: PLAN\ntask: review\nsaipen_home: {saipen_home.as_posix()}\n---\n",
        encoding="utf-8",
    )

    # Create canonical subs/
    canon_subs = saipen_home / "extensions" / "subs"
    canon_subs.mkdir(parents=True, exist_ok=True)

    (canon_subs / "PROTOCOL.md").write_text(
        "# Protocol\n\nCanonical\n", encoding="utf-8"
    )
    (canon_subs / "README.md").write_text("# Subs\n\nReadme\n", encoding="utf-8")
    (canon_subs / "MANIFEST.md").write_text("- test-sub -- test\n", encoding="utf-8")
    (canon_subs / "CREW.md").write_text("# Crew\n", encoding="utf-8")

    templ = canon_subs / "TEMPLATE"
    templ.mkdir(exist_ok=True)
    (templ / "STATE.md").write_text("---\nphase: INIT\n---\n", encoding="utf-8")
    (templ / "BOARD.md").write_text("# BOARD\n", encoding="utf-8")
    (templ / "LOG.md").write_text("# LOG\n", encoding="utf-8")

    # Create local subs/
    subs_dir = root / ".saipen" / "extensions" / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    (subs_dir / "PROTOCOL.md").write_text("# Protocol\n\nCanonical\n", encoding="utf-8")
    (subs_dir / "README.md").write_text("# Subs\n\nReadme\n", encoding="utf-8")
    (subs_dir / "MANIFEST.md").write_text("- test-sub -- test\n", encoding="utf-8")
    (subs_dir / "CREW.md").write_text("# Crew\n", encoding="utf-8")

    local_templ = subs_dir / "TEMPLATE"
    local_templ.mkdir(exist_ok=True)
    (local_templ / "STATE.md").write_text("---\nphase: INIT\n---\n", encoding="utf-8")
    (local_templ / "BOARD.md").write_text("# BOARD\n", encoding="utf-8")
    (local_templ / "LOG.md").write_text("# LOG\n", encoding="utf-8")

    # Copy all canonical mtime/size to local files for true identity
    import os

    for rel in _STALENESS_FILES:
        c_path = canon_subs / rel
        l_path = subs_dir / rel
        if c_path.exists() and l_path.exists():
            c_stat = c_path.stat()
            os.utime(l_path, (c_stat.st_atime, c_stat.st_mtime))

    return root


_STALENESS_FILES = [
    "PROTOCOL.md",
    "README.md",
    "MANIFEST.md",
    "TEMPLATE/STATE.md",
    "TEMPLATE/BOARD.md",
    "TEMPLATE/LOG.md",
]


def canonical_home() -> Path | None:
    """The canonical SAIPEN repo root the canonical writer bridge needs.

    Resolution: SAIPEN_HOME env (CI clones it there), then the known local
    checkout. None means the canonical engine is unreachable and the
    canonical-writer tests must skip (the bridge fails closed in production,
    so the tests skip only when the authority is genuinely absent)."""
    import os

    env = os.environ.get("SAIPEN_HOME")
    if env and (Path(env) / "tools" / "saipen_engine").is_dir():
        return Path(env)
    known = Path(r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN")
    if (known / "tools" / "saipen_engine").is_dir():
        return known
    return None


def make_conformant_project(
    tmp_path: Path,
    phase: str = "DONE",
    task: str = "none",
    next_action: str = "saipen continue",
    agent: str = "testseat",
    board_text: str | None = None,
    log_tail: int = 2,
) -> Path:
    """A canonical-clean project the canonical writer pipeline will mutate:
    full STATE (required fields + saipen_home + last_event == LOG tail), four
    BOARD headings, a conformant LOG. The canonical fast_check postcondition
    requires all of these, so mutation fixtures MUST start here."""
    home = canonical_home()
    assert home is not None, "canonical SAIPEN home unreachable"
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nschema_version: 3\n"
        f"phase: {phase}\ntransition_from: SHIP\ntask: {task}\n"
        f'next_action: "{next_action}"\nblocker: none\n'
        f"agent: {agent}\nsaipen_version: 7\n"
        f"saipen_home: {home}\n"
        "mode: full\nexecution_intent: normal\n"
        "updated: 2026-08-11T00:00:00Z\n"
        f"last_event: {log_tail}\n"
        "style_contract: ded-4ae736e4\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        board_text or "# BOARD\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n",
        encoding="utf-8",
    )
    (saipen / "LOG.md").write_text(
        "- 11.08.26 00:00 [E-1] RUN: boot\n"
        "- 11.08.26 00:01 [E-2] [parent: E-1] RUN: validate.py -> PASS\n"
        + (
            "".join(
                f"- 11.08.26 00:{2 + i:02d} [E-{3 + i}] [parent: E-{2 + i}] "
                f"RUN: extra\n"
                for i in range(max(0, log_tail - 2))
            )
        )
        if log_tail > 2
        else "- 11.08.26 00:00 [E-1] RUN: boot\n"
        "- 11.08.26 00:01 [E-2] [parent: E-1] RUN: validate.py -> PASS\n",
        encoding="utf-8",
    )
    return root


def make_ready_outbox(
    root: Path,
    sub: str,
    entry_id: str,
    title: str,
    critical: str = "true",
    summary: str = "fixture package",
    producer: str | None = None,
    collect_policy: str = "automatic",
) -> Path:
    """Write a COMPLETE, current, role-current `status: ready` OUTBOX entry.

    Every handoff field is bound to the fixture root's CURRENT source identity
    and a project-local charter's CURRENT role revision, so the entry passes
    the collect gate exactly as a real produced package would. The charter
    carries `collect_policy` (default `automatic`; `explicit`/`core-review`
    tests pass the value they need). Callers that want a red mutation
    overwrite one field afterwards."""
    from saipenview.collect import compute_source_identity, current_role_revision

    subs_dir = root / ".saipen" / "extensions" / "subs"
    (subs_dir / sub / "kitchen").mkdir(parents=True, exist_ok=True)
    charter = subs_dir / f"{sub}.md"
    if not charter.is_file():
        charter.write_text(
            f"# {sub} charter\n```yaml\nrole_revision: fixture\n"
            f"collect_policy: {collect_policy}\n```\n"
            f"The {sub} role, as a fixture charter.\n",
            encoding="utf-8",
        )
    identity = compute_source_identity(root)
    rr = current_role_revision(root, sub)
    body = (
        f"# OUTBOX\n\n"
        f"## {entry_id}: {title}\n"
        f"- **status:** ready\n"
        f"- **producer:** {producer or sub}\n"
        f"- **critical:** {critical}\n"
        f"- **summary:** {summary}\n"
        f"- **source_head:** {identity.source_head}\n"
        f"- **source_tree_fingerprint:** {identity.source_tree_fingerprint}\n"
        f"- **role_revision:** {rr}\n"
        f"- **coverage:** fixture root files\n"
        f"- **payload:** kitchen/{entry_id}.md\n"
        f"- **verified:** PASS -- gate fixture\n"
        f"- **instructions:** apply the fixture payload\n"
    )
    outbox = subs_dir / sub / "kitchen" / "OUTBOX.md"
    outbox.write_text(body, encoding="utf-8")
    return outbox
