"""Shared fixtures for SAIPENVIEW test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

# ── Config fixtures ──


@pytest.fixture
def tmp_config_path(tmp_path: Path) -> Path:
    """Point config_path to a tmp dir so tests never touch real config."""
    from saipenview import config as cfg_mod

    fake_dir = tmp_path / "_data"
    fake_dir.mkdir(parents=True, exist_ok=True)
    orig = cfg_mod.config_path
    cfg_mod.config_path = lambda: fake_dir / "config.json"
    yield fake_dir / "config.json"
    cfg_mod.config_path = orig


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
            "# BOARD\n\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
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
    return _make_saipen_project(tmp_path / "my-project", phase="PLAN", task="build widget")


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
    root = _make_saipen_project(tmp_path / "project-subs", phase="HUNT", task="bug chasing")

    subs_dir = root / ".saipen" / "extensions" / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    (subs_dir / "MANIFEST.md").write_text(
        "- saihunt -- bug-chasing sub\n- saiwiki -- documentation sub\n", encoding="utf-8"
    )

    _make_sub_project(
        subs_dir, "saihunt",
        phase="HUNT",
        outbox_text="""# OUTBOX

## HUNT-001: null pointer found
- **status:** ready
- **critical:** true
- **severity:** MEDIUM
- **summary:** Found nullable field in parser.py
- **details:** The `parse_frontmatter` function can return an empty dict.
"""
    )

    _make_sub_project(
        subs_dir, "saiwiki",
        phase="INIT",
        outbox_text="""# OUTBOX

## WIKI-001: architecture doc
- **status:** draft
- **critical:** false
- **summary:** Wrote architecture overview
"""
    )

    return root


@pytest.fixture
def saipen_project_with_subs_noncritical(tmp_path: Path) -> Path:
    """A SAIPEN project with a non-critical ready OUTBOX entry."""
    root = _make_saipen_project(tmp_path / "project-noncrit", phase="BUILD", task="fixes")

    subs_dir = root / ".saipen" / "extensions" / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    (subs_dir / "MANIFEST.md").write_text("- saihunt -- bug-chasing sub\n", encoding="utf-8")
    (subs_dir / "_shared").mkdir(parents=True, exist_ok=True)

    _make_sub_project(
        subs_dir, "saihunt",
        phase="HUNT",
        outbox_text="""# OUTBOX

## HUNT-002: minor lint issue
- **status:** ready
- **critical:** false
- **severity:** LOW
- **summary:** Unused import in test file
"""
    )

    return root


@pytest.fixture
def saipen_project_with_translate(tmp_path: Path) -> Path:
    """A SAIPEN project with an external saitranslate sub (legacy path)."""
    root = _make_saipen_project(tmp_path / "project-translate", phase="DONE", task="shipped")

    translate_dir = root / ".saitranslate"
    translate_dir.mkdir(parents=True, exist_ok=True)
    (translate_dir / "STATE.md").write_text("---\nphase: TRANSLATE\ntask: translating docs\n---\n", encoding="utf-8")
    (translate_dir / "BOARD.md").write_text("# BOARD\n\n## TODO\n\n## DONE\n\n", encoding="utf-8")
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

    (canon_subs / "PROTOCOL.md").write_text("# Protocol\n\nCanonical\n", encoding="utf-8")
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
