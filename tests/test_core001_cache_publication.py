from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import saipenview.api as api_module
import saipenview.scanner as scanner_module
from saipenview.api import Api
from saipenview.parser import Board, ProjectStatus
from saipenview.scanner import BackgroundScanner, ScanOutcome


def _status(root: Path, task: str) -> ProjectStatus:
    return ProjectStatus(
        root=root,
        state={"phase": "BUILD", "task": task, "next_action": task},
        board=Board(),
    )


def _seed_api(api: Api, root_a: Path, root_b: Path, cache_path: Path) -> list[tuple[list[str], list[str]]]:
    api._cache_file = cache_path
    api._cache_file.parent.mkdir(parents=True, exist_ok=True)
    api._config["scan_roots"] = [str(root_a), str(root_b)]
    api._projects = [
        api_module._project_to_dict(_status(root_a, "old-a")),
        api_module._project_to_dict(_status(root_b, "old-b")),
    ]
    api._has_scanned = True
    api._linked_worktrees = [
        {"root": str(root_a), "name": "a-old", "git_dir": "a.git"},
        {"root": str(root_b), "name": "b-old", "git_dir": "b.git"},
    ]
    api._ticket_index = {str(root_a): [{"id": "T-1"}], str(root_b): [{"id": "T-2"}]}

    build_calls: list[tuple[str, list[dict] | None]] = []

    def build_ticket_index(root: str, pre_built: list[dict] | None = None) -> None:
        build_calls.append((root, pre_built))
        if pre_built is not None:
            api._ticket_index[root] = pre_built
        elif root not in api._ticket_index:
            api._ticket_index[root] = []

    api._build_ticket_index = build_ticket_index
    watch_calls: list[tuple[list[str], list[str]]] = []
    api._watcher.sync = lambda projects, scan_roots: watch_calls.append(
        (list(projects), list(scan_roots))
    )
    return watch_calls


def _patch_project_conversion(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_is_garbage_root", lambda _root: False)
    monkeypatch.setattr(
        api_module,
        "check_project",
        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"verdict": "pass"}),
    )


def test_background_scanner_callback_preserves_plain_list_root_authority(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_project_conversion(monkeypatch)
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    api = Api()
    try:
        watch_calls = _seed_api(api, root_a, root_b, tmp_path / "cache" / "cache.json")
        outcome = ScanOutcome(
            projects=[_status(root_a, "new-a")],
            worktrees=[{"root": str(root_a), "name": "a-new", "git_dir": "a2.git"}],
            complete=False,
            completed_roots=[str(root_a)],
            unresolved_roots=[str(root_b)],
        )
        monkeypatch.setattr(scanner_module, "scan", lambda *_args, **_kwargs: outcome)
        scanner = BackgroundScanner(
            on_result=api._set_cache,
            scan_roots=[str(root_a), str(root_b)],
            epoch_source=lambda: api._scan_epoch,
        )

        scanner._do_scan()

        rows = {row["root"]: row for row in api._projects}
        assert rows[str(root_a)]["task"] == "new-a"
        assert rows[str(root_b)]["task"] == "old-b"
        worktrees = {row["root"]: row for row in api._linked_worktrees}
        assert worktrees[str(root_a)]["name"] == "a-new"
        assert worktrees[str(root_b)]["name"] == "b-old"
        assert api._ticket_index[str(root_b)] == [{"id": "T-2"}]
        assert {row["root"] for row in json.loads(api._cache_file.read_text())} == {
            str(root_a),
            str(root_b),
        }
        assert set(watch_calls[-1][0]) == {str(root_a), str(root_b)}
    finally:
        api.stop()


def test_plain_list_provenance_removes_completed_root_and_preserves_unresolved(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_project_conversion(monkeypatch)
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    api = Api()
    try:
        watch_calls = _seed_api(api, root_a, root_b, tmp_path / "cache" / "cache.json")

        api._set_cache(
            [],
            complete=False,
            worktrees=[],
            completed_roots=[str(root_a)],
            unresolved_roots=[str(root_b)],
        )

        assert [row["root"] for row in api._projects] == [str(root_b)]
        assert api._linked_worktrees == [
            {"root": str(root_b), "name": "b-old", "git_dir": "b.git"}
        ]
        assert str(root_a) not in api._ticket_index
        assert api._ticket_index[str(root_b)] == [{"id": "T-2"}]
        assert [row["root"] for row in json.loads(api._cache_file.read_text())] == [
            str(root_b)
        ]
        assert watch_calls[-1][0] == [str(root_b)]
    finally:
        api.stop()
