"""T-802 / PERF-003: the ticket index is built from an ALREADY-parsed Board.

The ticket says "avoid second BOARD parse", and the tree it shipped honoured
that on one of the two paths that build the index. Scan publication passed
`pre_built=` from `ScanOutcome` rows -- but `refresh_known`, the startup
reconciliation, called `_build_ticket_index(root)` bare, and that fell through
to reading `BOARD.md` off disk again for every changed root. `load_project` had
just parsed that exact file to produce the row.

Measured before the repair, on a 12-project fixture: 12 `BOARD.md` reads per
`refresh_known()`. The startup path is where this is least affordable -- it is
the reconciliation that runs against every durable-cache row.

The claims, each stated so it can fail:

* scan publication performs ZERO parent-board reads (`pre_built`);
* `refresh_known` performs ZERO parent-board reads (`parent_board`);
* both produce the SAME index content the disk path produced -- otherwise the
  saved read is a behaviour change wearing a perf ticket's clothes;
* a vanished root still clears its entry through the disk fallback.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import saipenview.api as api_mod
from saipenview.api import Api
from saipenview.parser import load_project
from saipenview.scanner import ScanOutcome

BOARD_TEXT = (
    "## DOING\n- [/] T-9 [P1] doing one | verify: none\n"
    "## TODO\n- [ ] T-1 [P2] todo one | verify: none\n"
    "- [ ] T-2 [P3] todo two | verify: none\n"
    "## DONE\n- [x] T-5 [P2] done one | verify: none\n"
    "## BLOCKED\n- [ ] T-7 [P1] blocked one | blocker: waiting\n"
)


def _project(base: Path, name: str) -> Path:
    root = base / name
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\nnext_action: PHASE DONE\nblocker: none\n"
        "agent: a\nsaipen_version: 7\nmode: full\ntransition_from: SHIP\n"
        "updated: 2026-08-30T00:00:00Z\nlast_event: 1\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(BOARD_TEXT, encoding="utf-8")
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


def _bare_api(tmp_path: Path, rows: list[dict]) -> Api:
    """An Api exercising only the cache/index surface.

    ``object.__new__`` on purpose: a real ``Api()`` starts a scanner, a watcher
    and a process manager, any of which can touch a BOARD file and make the
    read count measure the harness instead of the subject.
    """
    api = object.__new__(Api)
    api._lock = threading.RLock()
    api._projects = list(rows)
    api._ticket_index = {}
    api._cache_file = tmp_path / "_data" / "cache.json"
    api._cache_file.parent.mkdir(parents=True, exist_ok=True)
    api._config = {}
    api._sort_order = lambda: "smart"
    api._has_scanned = True
    api._scanning = False
    api._scan_epoch = 0
    api._linked_worktrees = []
    api._write_cache = lambda: None
    api._sync_watcher = lambda: None
    api._full_refresh_pending = True
    api._dirty_roots = set()
    api._cache_deleted_roots = set()
    api._registry_rev = 0
    api._refresh_changed_roots = []

    def replace(items, replace_all=False):
        changed = api._projects != list(items)
        api._projects = list(items)
        api._registry_rev += 1
        return changed

    api._replace_projects_locked = replace
    return api


@pytest.fixture
def count_board_reads(monkeypatch):
    """Count `read_doc` calls that target a BOARD.md, by path."""
    counts: dict[str, int] = {}
    real = api_mod.read_doc

    def counting(path, *args, **kwargs):
        p = Path(path)
        if p.name == "BOARD.md":
            counts[str(p)] = counts.get(str(p), 0) + 1
        return real(path, *args, **kwargs)

    monkeypatch.setattr(api_mod, "read_doc", counting)
    return counts


EXPECTED_INDEX = [
    {"id": "T-9", "desc": "[P1] doing one", "section": "DOING"},
    {"id": "T-1", "desc": "[P2] todo one", "section": "TODO"},
    {"id": "T-2", "desc": "[P3] todo two", "section": "TODO"},
    {"id": "T-5", "desc": "[P2] done one", "section": "DONE"},
    {"id": "T-7", "desc": "[P1] blocked one", "section": "BLOCKED"},
]


def _sorted(index: list[dict]) -> list[dict]:
    return sorted(index, key=lambda t: t["id"])


class TestScanPublicationDoesNotReparse:
    def test_zero_board_reads_and_correct_index(
        self, tmp_path, monkeypatch, count_board_reads
    ):
        roots = [_project(tmp_path, f"p{i}") for i in range(3)]
        projects = [load_project(r, with_git=False) for r in roots]
        count_board_reads.clear()

        api = _bare_api(tmp_path, [])
        monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
        api._set_cache(
            ScanOutcome(
                projects=projects,
                complete=True,
                completed_roots=[str(tmp_path)],
                unresolved_roots=[],
            )
        )

        assert count_board_reads == {}, (
            f"scan publication re-read BOARD.md: {count_board_reads}"
        )
        assert len(api._ticket_index) == 3
        for root in roots:
            assert _sorted(api._ticket_index[str(root)]) == _sorted(EXPECTED_INDEX)


class TestRefreshKnownDoesNotReparse:
    def test_zero_board_reads_over_every_changed_root(
        self, tmp_path, monkeypatch, count_board_reads
    ):
        """The startup reconciliation is where the second parse actually lived.

        `load_project` parsed each BOARD.md to build the row; the index build
        then read the same file again. 12 roots meant 12 redundant reads on the
        one path that runs against every cached project.
        """
        roots = [_project(tmp_path, f"p{i}") for i in range(4)]
        api = _bare_api(tmp_path, [_row(r) for r in roots])
        count_board_reads.clear()

        api.refresh_known()

        assert count_board_reads == {}, (
            f"refresh_known re-read BOARD.md after load_project parsed it: "
            f"{count_board_reads}"
        )
        assert len(api._ticket_index) == 4
        for root in roots:
            assert _sorted(api._ticket_index[str(root)]) == _sorted(EXPECTED_INDEX)

    def test_index_equals_what_the_disk_path_produces(self, tmp_path, monkeypatch):
        """Equivalence, not just fewer reads.

        The disk path is the reference implementation: whatever
        `_search_board_for_tickets` extracts from the file must equal what
        `_tickets_from_board` extracts from the parsed Board, or the saved read
        changed behaviour.
        """
        root = _project(tmp_path, "one")
        api = _bare_api(tmp_path, [_row(root)])

        api._build_ticket_index(str(root))
        from_disk = api._ticket_index[str(root)]

        api._ticket_index.clear()
        proj = load_project(root, with_git=False)
        api._build_ticket_index(str(root), parent_board=proj.board)
        from_board = api._ticket_index[str(root)]

        assert _sorted(from_board) == _sorted(from_disk)

    def test_vanished_root_still_clears_its_entry(self, tmp_path):
        """No parsed board means the disk fallback, which now finds nothing.

        A root whose `.saipen/` disappeared is reported as changed but has no
        `parsed_boards` entry. It must not keep a stale ticket payload that
        `quick_search` would keep answering from. The project is genuinely
        removed from disk rather than stubbed away, because the fallback reads
        the file: with the file still present, re-reading it is correct
        behaviour, and a test that stubbed only `load_project` would assert
        against a project that had not actually vanished.
        """
        import shutil

        root = _project(tmp_path, "gone")
        api = _bare_api(tmp_path, [_row(root)])
        api._ticket_index[str(root)] = list(EXPECTED_INDEX)

        shutil.rmtree(root / ".saipen")
        api.refresh_known()

        assert api._projects == [], "a vanished project kept its row"
        assert not api._ticket_index.get(str(root)), (
            "a vanished root kept its ticket payload"
        )
