"""T-815: the scan-publication ticket index silently omitted SubSaipen and
saitranslate boards.

``_set_cache`` passed ``_tickets_from_board(p.board)`` -- the parent board
only -- while the disk-reading rebuild also indexed sub/translate boards.
A sub-only ticket id was invisible to ``quick_search`` immediately after every
scan publication until some unrelated event rebuilt that root's index from
disk. A correctness defect wearing a perf optimisation's clothes.

Root cause: ``load_project`` parsed every sub BOARD through
``load_sub_board()`` but kept only ``board_counts``; the parsed Board was
discarded, so the publication path could not build the complete index without
going back to disk. The fix keeps the parsed Board on ``SubStatus`` (internal
state, never serialized), derives ``board_counts`` from that same parse, and
index-building goes through one helper with one contract:
``_tickets_from_project_status`` -- parent tickets without ``sub_name``, sub
and translate tickets with it.

The claims, each stated so it can fail:

* load_project parses parent/sub/translate tickets correctly;
* after scan publication, quick_search IMMEDIATELY finds the SubSaipen-only
  and saitranslate-only tickets, with correct sub_name;
* parent tickets stay parent tickets (never misclassified as sub tickets);
* publication performs ZERO BOARD reads after load_project already parsed the
  project (parent, sub AND translate boards counted);
* refresh_known performs zero redundant BOARD reads for successfully parsed
  roots while still rebuilding a complete index;
* the in-memory complete index equals the disk reference path;
* vanished roots still evict their stale index entries;
* quick_search reflects a SubSaipen-only BOARD change after the normal
  refresh path.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import saipenview.api as api_mod
from saipenview.api import Api
from saipenview.parser import load_project
from saipenview.scanner import ScanOutcome

PARENT_BOARD = (
    "## DOING\n- [/] P-100 parent doing | verify: none\n"
    "## TODO\n- [ ] P-101 parent todo | verify: none\n"
    "## DONE\n## BLOCKED\n"
)
SAIUI_BOARD = (
    "## DOING\n## TODO\n- [ ] UI-006 sub-only ticket | verify: none\n"
    "## DONE\n## BLOCKED\n"
)
SAIPY_BOARD = (
    "## DOING\n- [/] PY-007 second sub doing | verify: none\n"
    "## DONE\n## BLOCKED\n"
)
TRANSLATE_BOARD = (
    "## DOING\n## TODO\n- [ ] SAIT-042 translate-only ticket | verify: none\n"
    "## DONE\n## BLOCKED\n"
)


def _write_board(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _project_with_subs(base: Path) -> Path:
    """Parent + two SubSaipens (canonical .saipen/extensions/subs layout) +
    a legacy-path saitranslate, each with a distinct ticket."""
    root = base / "fleet"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nphase: BUILD\ntask: none\nnext_action: work\nblocker: none\n"
        "agent: a\nsaipen_version: 7\nmode: full\ntransition_from: SHIP\n"
        "updated: 2026-09-01T00:00:00Z\nlast_event: 1\n---\n",
        encoding="utf-8",
    )
    _write_board(saipen / "BOARD.md", PARENT_BOARD)
    (saipen / "LOG.md").write_text("# Log\n- 01.09.26 00:00 [E-001] DEC: base\n", encoding="utf-8")

    subs_dir = saipen / "extensions" / "subs"
    subs_dir.mkdir(parents=True)
    (subs_dir / "MANIFEST.md").write_text(
        "- saiui -- ui sub\n- saipy -- python sub\n", encoding="utf-8"
    )
    for name, board in (("saiui", SAIUI_BOARD), ("saipy", SAIPY_BOARD)):
        sub = subs_dir / name
        sub.mkdir(parents=True)
        (sub / "STATE.md").write_text(
            "---\nphase: HUNT\ntask: none\n---\n", encoding="utf-8"
        )
        _write_board(sub / "BOARD.md", board)
        (sub / "LOG.md").write_text("# LOG\n", encoding="utf-8")

    translate = root / ".saitranslate"
    translate.mkdir()
    (translate / "STATE.md").write_text(
        "---\nphase: TRANSLATE\ntask: none\n---\n", encoding="utf-8"
    )
    _write_board(translate / "BOARD.md", TRANSLATE_BOARD)
    (translate / "LOG.md").write_text("# LOG\n", encoding="utf-8")
    return root


def _row(root: Path) -> dict:
    return {
        "root": str(root),
        "name": root.name,
        "phase": "BUILD",
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
    """An Api exercising only the cache/index surface (no scanner/watcher)."""
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


@pytest.fixture(autouse=True)
def _no_fixture_garbage(monkeypatch):
    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)


@pytest.fixture
def count_board_reads(monkeypatch):
    """Count read_doc calls on any BOARD.md (parent, sub, translate), by path."""
    counts: dict[str, int] = {}
    real = api_mod.read_doc

    def counting(path, *args, **kwargs):
        p = Path(path)
        if p.name == "BOARD.md":
            counts[str(p)] = counts.get(str(p), 0) + 1
        return real(path, *args, **kwargs)

    monkeypatch.setattr(api_mod, "read_doc", counting)
    return counts


def _sub_tickets(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        out.extend(r.get("sub_matched_tickets") or [])
    return out


def _parent_tickets(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        out.extend(r.get("matched_tickets") or [])
    return out


# ── parse layer ──────────────────────────────────────────────────────────────


class TestLoadProjectParsesAllTickets:
    def test_subs_and_translate_retain_parsed_boards(self, tmp_path):
        root = _project_with_subs(tmp_path)
        proj = load_project(root, with_git=False)
        assert [t.ticket_id for t in proj.board.todo] == ["P-101"]
        by_name = {s.name: s for s in proj.subs}
        assert [t.ticket_id for t in by_name["saiui"].board.todo] == ["UI-006"]
        assert [t.ticket_id for t in by_name["saipy"].board.doing] == ["PY-007"]
        assert [t.ticket_id for t in proj.translate.board.todo] == ["SAIT-042"]

    def test_board_counts_derived_from_the_same_parse(self, tmp_path, monkeypatch):
        import saipenview.parser as parser_mod

        calls = {"n": 0}
        real = parser_mod.read_doc

        def counting(path, *a, **kw):
            if Path(path).name == "BOARD.md":
                calls["n"] += 1
            return real(path, *a, **kw)

        monkeypatch.setattr(parser_mod, "read_doc", counting)
        root = _project_with_subs(tmp_path)
        proj = load_project(root, with_git=False)
        # Parent(1) + 2 subs + 1 translate = 4 BOARD parses total, not more.
        assert calls["n"] == 4
        by_name = {s.name: s for s in proj.subs}
        assert by_name["saiui"].board_counts["todo"] == 1
        assert proj.translate.board_counts["todo"] == 1


# ── scan publication ─────────────────────────────────────────────────────────


class TestScanPublicationCompleteIndex:
    def test_quick_search_finds_sub_only_ticket_immediately(
        self, tmp_path, count_board_reads
    ):
        """The T-815 reproduction: UI-006 was invisible until a disk rebuild."""
        root = _project_with_subs(tmp_path)
        projects = [load_project(root, with_git=False)]
        count_board_reads.clear()

        api = _bare_api(tmp_path, [])
        api._set_cache(
            ScanOutcome(
                projects=projects,
                complete=True,
                completed_roots=[str(tmp_path)],
                unresolved_roots=[],
            )
        )
        hits = api.quick_search("UI-006")
        assert len(hits) == 1
        subs = _sub_tickets(hits)
        assert [t["id"] for t in subs] == ["UI-006"]
        assert subs[0]["sub_name"] == "saiui"

    def test_quick_search_finds_translate_only_ticket_immediately(
        self, tmp_path, count_board_reads
    ):
        root = _project_with_subs(tmp_path)
        projects = [load_project(root, with_git=False)]
        count_board_reads.clear()

        api = _bare_api(tmp_path, [])
        api._set_cache(
            ScanOutcome(projects=projects, complete=True, completed_roots=[str(tmp_path)])
        )
        hits = api.quick_search("SAIT-042")
        subs = _sub_tickets(hits)
        assert [t["id"] for t in subs] == ["SAIT-042"]
        assert subs[0]["sub_name"] == "saitranslate"

    def test_parent_tickets_not_misclassified_as_sub(self, tmp_path):
        root = _project_with_subs(tmp_path)
        projects = [load_project(root, with_git=False)]
        api = _bare_api(tmp_path, [])
        api._set_cache(
            ScanOutcome(projects=projects, complete=True, completed_roots=[str(tmp_path)])
        )
        hits = api.quick_search("P-101")
        assert hits, "parent ticket vanished from search"
        assert [t["id"] for t in _parent_tickets(hits)] == ["P-101"]
        assert _sub_tickets(hits) == [], "parent ticket misclassified as sub ticket"

    def test_publication_zero_board_reads_after_parse(
        self, tmp_path, count_board_reads
    ):
        """All four BOARD.md files (parent + 2 subs + translate) must stay
        un-read during publication -- load_project already parsed each."""
        root = _project_with_subs(tmp_path)
        projects = [load_project(root, with_git=False)]
        count_board_reads.clear()

        api = _bare_api(tmp_path, [])
        api._set_cache(
            ScanOutcome(projects=projects, complete=True, completed_roots=[str(tmp_path)])
        )
        assert count_board_reads == {}, (
            f"publication re-read BOARD.md files: {count_board_reads}"
        )

    def test_complete_index_equivalent_to_disk_reference(self, tmp_path):
        """The optimized path must equal the reference disk path, not be a
        different approximation of it."""
        root = _project_with_subs(tmp_path)
        projects = [load_project(root, with_git=False)]

        api = _bare_api(tmp_path, [])
        api._set_cache(
            ScanOutcome(projects=projects, complete=True, completed_roots=[str(tmp_path)])
        )
        optimized = sorted(
            api._ticket_index[str(root)], key=lambda t: t["id"]
        )

        # Reference: the disk-reading rebuild (pre_built deliberately absent).
        # The registry row must carry the sub/translate paths the disk path
        # reads, exactly as _project_to_dict produces them.
        proj = projects[0]
        row = _row(root)
        row["subs"] = [
            {"name": s.name, "path": str(s.path)} for s in proj.subs
        ]
        row["translate"] = {"name": "saitranslate", "path": str(proj.translate.path)}
        api._ticket_index.clear()
        api._projects = [row]
        api._build_ticket_index(str(root))
        from_disk = sorted(api._ticket_index[str(root)], key=lambda t: t["id"])

        assert optimized == from_disk


# ── refresh_known ────────────────────────────────────────────────────────────


class TestRefreshKnownCompleteIndex:
    def test_zero_redundant_board_reads_and_complete_index(
        self, tmp_path, count_board_reads
    ):
        root = _project_with_subs(tmp_path)
        api = _bare_api(tmp_path, [_row(root)])
        count_board_reads.clear()

        api.refresh_known()

        # Startup reconciliation: load_project parses 4 boards; the index
        # build must add ZERO more.
        assert count_board_reads == {}, (
            f"refresh_known re-read BOARD.md files: {count_board_reads}"
        )
        index = api._ticket_index[str(root)]
        ids = {t["id"] for t in index}
        assert {"P-100", "P-101", "UI-006", "PY-007", "SAIT-042"} <= ids
        sub_named = {t["id"]: t.get("sub_name") for t in index if "sub_name" in t}
        assert sub_named["UI-006"] == "saiui"
        assert sub_named["SAIT-042"] == "saitranslate"

    def test_sub_only_board_change_reflected_after_refresh(self, tmp_path):
        """The normal refresh path must pick up a SubSaipen-only BOARD change."""
        root = _project_with_subs(tmp_path)
        api = _bare_api(tmp_path, [_row(root)])
        api.refresh_known()
        assert api.quick_search("UI-006"), "pre-change ticket missing"

        sub_board = root / ".saipen" / "extensions" / "subs" / "saiui" / "BOARD.md"
        _write_board(
            sub_board,
            "## DOING\n## TODO\n- [ ] UI-999 fresh sub ticket | verify: none\n## DONE\n## BLOCKED\n",
        )
        api.refresh_known()

        hits = api.quick_search("UI-999")
        assert hits, "SubSaipen-only change invisible after refresh"
        subs = _sub_tickets(hits)
        assert [t["id"] for t in subs] == ["UI-999"]
        assert subs[0]["sub_name"] == "saiui"

    def test_vanished_root_still_evicts_stale_index(self, tmp_path):
        import shutil

        root = _project_with_subs(tmp_path)
        api = _bare_api(tmp_path, [_row(root)])
        api.refresh_known()
        assert api.quick_search("UI-006")

        shutil.rmtree(root)
        api.refresh_known()

        assert api._projects == []
        assert not api._ticket_index.get(str(root)), (
            "vanished root kept a stale ticket payload"
        )


# ── watcher path (the route a real file change takes) ───────────────────────


class TestWatcherPathCompleteIndex:
    def test_sub_board_file_event_reindexes_complete_board(
        self, tmp_path, count_board_reads
    ):
        """A sub-BOARD.md write reaches the index through _refresh_one_project
        (the watcher entry point), not refresh_known -- it must also produce
        the COMPLETE index with zero extra BOARD reads."""
        root = _project_with_subs(tmp_path)
        api = _bare_api(tmp_path, [])
        api._config = {"pinned_roots": []}
        api._set_cache(
            ScanOutcome(
                projects=[load_project(root, with_git=False)],
                complete=True,
                completed_roots=[str(tmp_path)],
            )
        )
        assert api.quick_search("UI-006"), "precondition: publication indexed the sub"

        sub_board = root / ".saipen" / "extensions" / "subs" / "saiui" / "BOARD.md"
        _write_board(
            sub_board,
            "## DOING\n## TODO\n- [ ] UI-777 watched change | verify: none\n## DONE\n## BLOCKED\n",
        )
        count_board_reads.clear()
        api._refresh_one_project(str(root), changed_files={"extensions/subs/saiui/BOARD.md"})

        assert count_board_reads == {}, (
            f"watcher refresh re-read BOARD.md files: {count_board_reads}"
        )
        hits = api.quick_search("UI-777")
        subs = _sub_tickets(hits)
        assert [t["id"] for t in subs] == ["UI-777"]
        assert subs[0]["sub_name"] == "saiui"
