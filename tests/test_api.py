"""Mock-based tests for saipenview.api.Api — no real file/scan/parser dependency."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saipenview.api import Api, _project_sort_key
from saipenview.config import DEFAULTS
from saipenview.parser import Board, ProjectStatus, Ticket

# ── Fixtures ──


@pytest.fixture
def mock_config(tmp_path: Path) -> dict:
    """Return a base config dict."""
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["sort_order"] = "smart"
    cfg["scan_roots"] = None
    return cfg


@pytest.fixture
def mock_project_status() -> ProjectStatus:
    """A simple ProjectStatus object for testing."""
    return ProjectStatus(
        root=Path("/mock/project"),
        state={"phase": "DONE", "task": "done"},
        board=Board(
            doing=[Ticket("T-001", "/", "in progress")],
            todo=[Ticket("T-002", " ", "to do")],
            done=[Ticket("T-003", "x", "completed")],
            blocked=[],
        ),
        mtime=1000,
        git_branch="",
        git_dirty=False,
        subs=[],
    )


@pytest.fixture(autouse=True)
def api_patches(mock_config, tmp_path):
    """Monkey-patch all Api external dependencies for testing."""
    with (
        patch("saipenview.api.config_path") as mock_cfg_path,
        patch("saipenview.api.load_config", return_value=mock_config),
        patch("saipenview.api.save_config") as mock_save,
        patch("saipenview.api.BackgroundScanner") as mock_scanner,
    ):
        data_dir = tmp_path / "_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        mock_cfg_path.return_value = data_dir / "config.json"

        mock_scanner_instance = MagicMock()
        mock_scanner.return_value = mock_scanner_instance

        yield {
            "mock_config": mock_config,
            "mock_save": mock_save,
            "mock_scanner": mock_scanner_instance,
            "data_dir": data_dir,
        }


@pytest.fixture
def api(api_patches) -> Api:
    """Construct an Api with all external dependencies mocked."""
    instance = Api()
    try:
        yield instance
    finally:
        instance.stop()  # stop the real SaipenWatcher + unsubscribe the bus handler


def _make_project(
    name: str,
    root: str,
    phase: str,
    mtime: int,
    git_dirty: bool = False,
    is_pinned: bool = False,
) -> dict:
    return {
        "name": name,
        "root": root,
        "phase": phase,
        "mtime": mtime,
        "git_dirty": git_dirty,
        "is_pinned": is_pinned,
        "task": "none",
        "next_action": "",
        "blocker": "none",
        "updated": "",
        "board": {"doing": 0, "todo": 0, "done": 0, "blocked": 0},
        "subs": [],
        "translate": None,
        "quick_actions": [],
        "subs_stale": False,
        "subs_stale_details": "",
        "git_branch": "",
    }


def _seed_verified_root(api, root: Path) -> Path:
    """Make *root* a verified project root the Api will act on (T-164).

    The T-164 boundary means scan roots grant nothing: a root is actionable
    only when it holds a real .saipen/STATE.md and the Api knows about it.
    This helper builds both halves -- the file and a pinned-root entry.

    CORE-001: STATE.md is seeded with a saipen_home field so the canonical
    codec can read it back. Tests that exercise the read/write CAS path need
    a canonical-readable file or the codec fails closed (per audit).
    """
    from conftest import canonical_home

    saipen = root / ".saipen"
    saipen.mkdir(parents=True, exist_ok=True)
    home = canonical_home()
    home_line = f"saipen_home: {home}\n" if home else ""
    (saipen / "STATE.md").write_text(
        f"---\nphase: DONE\ntask: none\nnext_action: RUN: noop\n"
        f"blocker: none\n{home_line}---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "# BOARD\n\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    api._config["pinned_roots"] = [str(root)]
    return root


@pytest.fixture
def api_with_projects(api, tmp_path) -> Api:
    """Api with pre-populated _projects cache sorted in smart order."""
    api._has_scanned = True
    # Make beta actually pinned in config (not just the UI field)
    api._config["pinned_roots"] = [str(tmp_path / "beta")]
    api._projects = [
        _make_project("alpha", str(tmp_path / "alpha"), "DONE", 500),
        _make_project(
            "beta",
            str(tmp_path / "beta"),
            "BUILD",
            1000,
            git_dirty=True,
            is_pinned=True,
        ),
        _make_project("gamma", str(tmp_path / "gamma"), "BLOCKED", 100),
    ]
    # Sort to match what _set_cache would produce
    api._projects.sort(key=lambda x: _project_sort_key(x, "smart"))
    # PERF-002: tests that expect refresh_known to actually reparse must
    # set the pending flag; idle polls (the default production state) must
    # not trigger an O(projects) reparse.
    api._full_refresh_pending = True
    return api


# ── get_projects ──


class TestGetProjects:
    def test_returns_all_when_no_hidden(self, api_with_projects):
        projects = api_with_projects.get_projects()
        assert len(projects) == 3

    def test_filters_hidden_projects(self, api_with_projects, tmp_path):
        api_with_projects._config["hidden_roots"] = [str(tmp_path / "alpha")]
        projects = api_with_projects.get_projects()
        assert len(projects) == 2
        names = [p["name"] for p in projects]
        assert "alpha" not in names

    def test_returns_empty_when_all_hidden(self, api_with_projects, tmp_path):
        api_with_projects._config["hidden_roots"] = [
            str(tmp_path / "alpha"),
            str(tmp_path / "beta"),
            str(tmp_path / "gamma"),
        ]
        assert api_with_projects.get_projects() == []

    def test_returns_copy_not_reference(self, api_with_projects):
        result = api_with_projects.get_projects()
        result.clear()
        assert len(api_with_projects.get_projects()) == 3


# ── toggle_pin ──


class TestTogglePin:
    def test_pin_project(self, api_with_projects, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.toggle_pin(root)
        assert root in api_with_projects._config.get("pinned_roots", [])
        alpha = next(
            p for p in api_with_projects.get_projects() if p["name"] == "alpha"
        )
        assert alpha["is_pinned"] is True

    def test_unpin_project(self, api_with_projects, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.toggle_pin(root)
        api_with_projects.toggle_pin(root)
        assert root not in api_with_projects._config.get("pinned_roots", [])
        alpha = next(
            p for p in api_with_projects.get_projects() if p["name"] == "alpha"
        )
        assert alpha["is_pinned"] is False

    def test_pin_persists_to_config(self, api_with_projects, api_patches, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.toggle_pin(root)
        assert root in api_with_projects._config.get("pinned_roots", [])
        api_patches["mock_save"].assert_called_once()

    def test_pinned_sorts_first(self, api_with_projects, tmp_path):
        """Pinned projects sort before unpinned regardless of phase rank."""
        root_a = str(tmp_path / "alpha")
        api_with_projects.toggle_pin(root_a)
        projects = api_with_projects.get_projects()
        # Both beta (BUILD rank 2) and alpha (DONE rank 4) are pinned now.
        # Among pinned: beta (rank 2) sorts before alpha (rank 4).
        assert projects[0]["name"] == "beta"
        assert projects[1]["name"] == "alpha"
        assert projects[2]["name"] == "gamma"


# ── hide_project ──


class TestHideProject:
    def test_hide_project_removes_from_list(self, api_with_projects, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.hide_project(root)
        assert root in api_with_projects._config.get("hidden_roots", [])
        names = [p["name"] for p in api_with_projects.get_projects()]
        assert "alpha" not in names

    def test_hide_then_get_projects_filters(self, api_with_projects, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.hide_project(root)
        names = [p["name"] for p in api_with_projects.get_projects()]
        assert "alpha" not in names

    def test_hide_twice_is_idempotent(self, api_with_projects, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.hide_project(root)
        api_with_projects.hide_project(root)
        assert len(api_with_projects._config.get("hidden_roots", [])) == 1

    def test_hide_saves_config(self, api_with_projects, api_patches, tmp_path):
        root = str(tmp_path / "alpha")
        api_with_projects.hide_project(root)
        api_patches["mock_save"].assert_called_once()


# ── set_sort_order ──


class TestSetSortOrder:
    def test_default_sort_is_smart(self, api):
        assert api._sort_order() == "smart"

    def test_change_to_name_asc(self, api_with_projects):
        api_with_projects.set_sort_order("name_asc")
        assert api_with_projects._config["sort_order"] == "name_asc"

    def test_name_asc_sorts_pinned_first_then_alphabetical(self, api_with_projects):
        """name_asc: pinned (beta) first, then alphabetical."""
        api_with_projects.set_sort_order("name_asc")
        projects = api_with_projects.get_projects()
        names = [p["name"] for p in projects]
        assert names == ["beta", "alpha", "gamma"]

    def test_name_desc_sorts_correctly(self, api_with_projects):
        api_with_projects.set_sort_order("name_desc")
        projects = api_with_projects.get_projects()
        names = [p["name"] for p in projects]
        # beta pinned first, then gamma, alpha in desc
        assert names[0] == "beta"
        assert names[1] == "gamma"
        assert names[2] == "alpha"

    def test_recent_sort(self, api_with_projects):
        api_with_projects.set_sort_order("recent")
        projects = api_with_projects.get_projects()
        # beta pinned first (mtime=1000), alpha next (500), gamma last (100)
        assert projects[0]["name"] == "beta"
        assert projects[1]["name"] == "alpha"
        assert projects[2]["name"] == "gamma"

    def test_oldest_sort(self, api_with_projects):
        api_with_projects.set_sort_order("oldest")
        projects = api_with_projects.get_projects()
        # beta pinned first, gamma (100) before alpha (500)
        assert projects[0]["name"] == "beta"
        assert projects[1]["name"] == "gamma"
        assert projects[2]["name"] == "alpha"

    def test_saves_config(self, api_with_projects, api_patches):
        api_with_projects.set_sort_order("name_asc")
        api_patches["mock_save"].assert_called()


# ── refresh_known ──


class TestRefreshKnown:
    def test_returns_same_when_no_projects(self, api):
        """refresh_known with no cached projects returns []."""
        assert api.refresh_known() == []

    def test_calls_load_project_for_each_root(self, api_with_projects, tmp_path):
        """Each project root gets load_project called."""
        with patch("saipenview.api.load_project") as mock_load:
            mock_load.return_value = None
            api_with_projects.refresh_known()
            assert mock_load.call_count == 3

    def test_preserves_previous_on_transient_failure(self, api_with_projects, tmp_path):
        """W2-008: a transient read failure (load_project raises) keeps the
        previous project rows; only a clean absence (load_project returns None
        without raising) drops them."""
        with patch("saipenview.api.load_project", side_effect=OSError("disk blip")):
            result = api_with_projects.refresh_known()
            assert len(result) == 3

    def test_refreshes_with_new_data(
        self, api_with_projects, tmp_path, mock_project_status
    ):
        """When load_project returns new data, it replaces the row."""
        mock_project_status.root = tmp_path / "alpha"
        mock_project_status.state = {"phase": "BUILD", "task": "rebuilding"}

        with patch("saipenview.api.load_project", return_value=mock_project_status):
            result = api_with_projects.refresh_known()
            alpha = next(p for p in result if p["name"] == "alpha")
            assert alpha["phase"] == "BUILD"

    def test_skips_hidden_roots(self, api_with_projects, tmp_path):
        """Hidden roots are excluded from refresh_known *results* (visibility is
        applied in get_projects), but CORE-006 still refreshes them so their
        registry rows stay current and pending external changes keep getting
        tracked. W2-008: a clean absence (load_project returns None) drops the
        row, but the hidden root is still *loaded*."""
        api_with_projects._config["hidden_roots"] = [str(tmp_path / "alpha")]

        with patch("saipenview.api.load_project") as mock_load:
            mock_load.return_value = None
            result = api_with_projects.refresh_known()
            # All roots cleanly absent -> every row dropped.
            assert len(result) == 0
            # CORE-006: hidden roots are still loaded/refreshed even though hidden.
            roots_called = [call.args[0].name for call in mock_load.call_args_list]
            assert "alpha" in roots_called

    def test_carries_git_state_forward(
        self, api_with_projects, tmp_path, mock_project_status
    ):
        """Git branch/dirty from previous row is carried forward."""
        api_with_projects._projects[0]["git_branch"] = "feature-x"
        api_with_projects._projects[0]["git_dirty"] = True

        mock_project_status.root = tmp_path / "alpha"

        with patch("saipenview.api.load_project", return_value=mock_project_status):
            result = api_with_projects.refresh_known()
            alpha = next(p for p in result if p["name"] == "alpha")
            assert alpha["git_branch"] == "feature-x"
            assert alpha["git_dirty"] is True

    def test_writes_cache_when_changed(
        self, api_with_projects, tmp_path, mock_project_status
    ):
        """When projects change, cache is written."""
        mock_project_status.root = tmp_path / "alpha"

        with (
            patch("saipenview.api.load_project", return_value=mock_project_status),
            patch.object(api_with_projects, "_write_cache") as mock_cache,
        ):
            api_with_projects.refresh_known()
            assert mock_cache.called

    def test_skips_cache_write_when_unchanged(self, api_with_projects):
        """When projects don't change, cache is NOT written. W2-008: a transient
        failure (raises) keeps the identical prev rows, so nothing changed and
        the cache stays untouched."""
        with (
            patch("saipenview.api.load_project", side_effect=OSError("disk blip")),
            patch.object(api_with_projects, "_write_cache") as mock_cache,
        ):
            api_with_projects.refresh_known()
            assert not mock_cache.called

    def test_uses_with_git_false(self, api_with_projects):
        """refresh_known passes with_git=False to load_project."""
        with patch("saipenview.api.load_project") as mock_load:
            mock_load.return_value = None
            api_with_projects.refresh_known()
            for call in mock_load.call_args_list:
                assert call.kwargs.get("with_git") is False


# ── quick_search ──


class TestQuickSearch:
    def test_empty_query_returns_empty(self, api_with_projects):
        assert api_with_projects.quick_search("") == []
        assert api_with_projects.quick_search("   ") == []

    def test_search_by_name(self, api_with_projects):
        result = api_with_projects.quick_search("alpha")
        assert len(result) == 1
        assert result[0]["name"] == "alpha"
        assert result[0]["matched_field"] == "name"

    def test_search_by_name_case_insensitive(self, api_with_projects):
        result = api_with_projects.quick_search("ALPHA")
        assert len(result) == 1
        assert result[0]["name"] == "alpha"

    def test_no_match_returns_empty(self, api_with_projects):
        assert api_with_projects.quick_search("nonexistent") == []

    def test_search_partial_name(self, api_with_projects):
        """Partial name match works."""
        result = api_with_projects.quick_search("alp")
        assert len(result) == 1
        assert result[0]["name"] == "alpha"

    def test_matches_multiple_projects(self, api_with_projects):
        """Multiple projects can match the same query."""
        api_with_projects._projects.append(
            _make_project("alpha-plus", "/some/alpha-plus", "INIT", 0)
        )
        result = api_with_projects.quick_search("alpha")
        assert len(result) == 2

    def test_search_empty_projects_list(self, api):
        assert api.quick_search("anything") == []

    def test_result_has_correct_fields(self, api_with_projects):
        """Each search result has the required fields."""
        result = api_with_projects.quick_search("beta")
        assert len(result) == 1
        r = result[0]
        assert "root" in r
        assert "name" in r
        assert "phase" in r
        assert "matched_field" in r
        assert "matched_tickets" in r
        assert "sub_matched_tickets" in r

    def test_ticket_search_via_mock(self, api_with_projects, tmp_path):
        """quick_search reads the in-memory ticket index (PERF-008); injecting a
        match there exercises the real search path end-to-end."""
        matched = [{"id": "T-001", "desc": "fix parser", "section": "DOING"}]
        beta_root = str(tmp_path / "beta")
        api_with_projects._ticket_index = {beta_root: matched}
        result = api_with_projects.quick_search("fix")
        assert len(result) >= 1
        r = result[0]
        assert len(r["matched_tickets"]) >= 1
        assert r["matched_tickets"][0]["id"] == "T-001"


# ── get_status ──


class TestGetStatus:
    def test_initial_state(self, api):
        status = api.get_status()
        assert status["scanned"] is False
        assert status["scanning"] is False
        assert status["count"] == 0

    def test_returns_counts(self, api_with_projects):
        status = api_with_projects.get_status()
        assert status["count"] == 3
        assert status["revision"] == api_with_projects._registry_rev


# ── get_config / get_locales / get_wiki_pages ──


class TestSimpleGetters:
    def test_get_config_returns_copy(self, api):
        cfg = api.get_config()
        cfg["locale"] = "zh-CN"
        assert api.get_config()["locale"] == "en"

    def test_get_locales(self, api):
        locales = api.get_locales()
        assert len(locales) == 34
        codes = [loc["code"] for loc in locales]
        assert "en" in codes
        assert "zh-CN" in codes
        assert "ru" in codes
        assert "ded" in codes

    def test_get_wiki_pages(self, api):
        pages = api.get_wiki_pages()
        assert len(pages) == 5
        assert pages[0]["id"] == "WIKI-001"

    def test_set_locale(self, api):
        result = api.set_locale("zh-CN")
        assert result["locale"] == "zh-CN"
        assert api._config["locale"] == "zh-CN"

    def test_set_locale_saves_config(self, api, api_patches):
        api.set_locale("zh-CN")
        api_patches["mock_save"].assert_called_once()


# ── Additional API methods ──


class TestGetProjectDetail:
    """get_project_detail loads a project and formats it for the detail pane."""

    def test_returns_none_for_missing_project(self, api):
        with patch("saipenview.api.load_project", return_value=None):
            result = api.get_project_detail("/nonexistent")
            assert result is None

    def test_includes_custom_commands(self, api, tmp_path, mock_project_status):
        mock_project_status.root = tmp_path / "test-proj"
        root = _seed_verified_root(api, tmp_path / "test-proj")
        api._config["custom_commands"] = [{"label": "Deploy", "command": "deploy.bat"}]

        with patch("saipenview.api.load_project", return_value=mock_project_status):
            result = api.get_project_detail(str(root))
            assert result is not None
            assert len(result["custom_commands"]) == 1
            assert result["custom_commands"][0]["label"] == "Deploy"


class TestOpenFolder:
    """open_folder uses os.startfile to open folder in Explorer."""

    def test_returns_false_for_nonexistent_path(self, api):
        assert api.open_folder("Z:\\nonexistent") is False

    def test_returns_true_for_existing_path(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("os.startfile") as mock_startfile:
            result = api.open_folder(str(d))
            assert result is True
            from saipenview.paths import canonical

            assert mock_startfile.call_args.args[0].lower() == canonical(d).lower()

    def test_handles_startfile_exception(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("os.startfile", side_effect=OSError("access denied")):
            result = api.open_folder(str(d))
            assert result is False

    def test_unverified_root_rejected(self, api, tmp_path):
        d = tmp_path / "plain-dir"
        d.mkdir()
        with patch("os.startfile") as mock_startfile:
            assert api.open_folder(str(d)) is False
            mock_startfile.assert_not_called()


class TestOpenTerminal:
    """open_terminal opens cmd.exe in project folder."""

    def test_returns_false_for_nonexistent_path(self, api):
        assert api.open_terminal("Z:\\nonexistent") is False

    def test_returns_true_and_opens_cmd(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("subprocess.Popen") as mock_popen:
            result = api.open_terminal(str(d))
            assert result is True
            mock_popen.assert_called_once()

    def test_handles_popen_exception(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("subprocess.Popen", side_effect=OSError("cmd not found")):
            result = api.open_terminal(str(d))
            assert result is False


class TestOpenEditor:
    """open_editor opens VS Code in project folder."""

    def test_returns_false_for_nonexistent_path(self, api):
        assert api.open_editor("Z:\\nonexistent") is False

    def test_returns_false_when_code_not_found(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("shutil.which", return_value=None):
            result = api.open_editor(str(d))
            assert result is False

    def test_returns_true_and_launches_code(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with (
            patch("shutil.which", return_value="C:\\Program Files\\VS Code\\code.exe"),
            patch("subprocess.Popen") as mock_popen,
        ):
            result = api.open_editor(str(d))
            assert result is True
            mock_popen.assert_called_once()

    def test_handles_popen_exception(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with (
            patch("shutil.which", return_value="code.exe"),
            patch("subprocess.Popen", side_effect=OSError("launch failed")),
        ):
            result = api.open_editor(str(d))
            assert result is False


class TestReadWriteFile:
    """read_file_text and write_file_text are contained to known roots (T-138)."""

    def _seed_root(self, api, tmp_path):
        return _seed_verified_root(api, tmp_path)

    def test_read_existing_file(self, api, tmp_path):
        from conftest import canonical_home

        if canonical_home() is None:
            pytest.skip("canonical SAIPEN home unreachable")
        self._seed_root(api, tmp_path)
        f = tmp_path / ".saipen" / "STATE.md"
        result = api.read_file_text(str(f))
        # CORE-001: protocol files return {text, edit_version}.
        assert isinstance(result, dict)
        assert "text" in result and "edit_version" in result
        assert result["text"].startswith("---")

    def test_read_nonexistent_file(self, api, tmp_path):
        self._seed_root(api, tmp_path)
        assert api.read_file_text(str(tmp_path / "missing.md")) is None

    def test_write_file(self, api, tmp_path):
        self._seed_root(api, tmp_path)
        f = tmp_path / "STATE.md"
        result = api.write_file_text(str(f), "written\n")
        assert result is True
        assert f.read_text(encoding="utf-8") == "written\n"

    def test_write_fails_on_bad_path(self, api, tmp_path):
        self._seed_root(api, tmp_path)
        result = api.write_file_text(str(tmp_path / "missing" / "out.md"), "data")
        assert result is False

    def test_read_outside_root_rejected(self, api, tmp_path):
        """A path that escapes every known root is rejected, not read."""
        self._seed_root(api, tmp_path)
        outside = tmp_path.parent / "outside.md"
        outside.write_text("secret\n", encoding="utf-8")
        assert api.read_file_text(str(outside)) is None

    def test_write_non_markdown_rejected(self, api, tmp_path):
        """Only .md/.json may be written; .txt is a boundary violation."""
        self._seed_root(api, tmp_path)
        f = tmp_path / "evil.txt"
        assert api.write_file_text(str(f), "pwned") is False
        assert not f.exists()

    def test_read_unknown_extension_rejected(self, api, tmp_path):
        self._seed_root(api, tmp_path)
        f = tmp_path / "secret.bin"
        f.write_bytes(b"\x00\x01")
        assert api.read_file_text(str(f)) is None

    def test_dot_dot_escape_rejected(self, api, tmp_path):
        self._seed_root(api, tmp_path)
        assert api.read_file_text(str(tmp_path / ".." / "etc" / "passwd.md")) is None


class TestUpdateProjectState:
    """update_project_state calls update_state and rescans."""

    def test_returns_none_when_update_fails(self, api):
        with patch("saipenview.parser.update_state", return_value=False):
            result = api.update_project_state("/test", {"task": "x"})
            assert result is None


class TestRescan:
    """rescan triggers a full scan and returns projects."""

    def test_rescan_calls_scan_and_returns_projects(self, api, api_patches):
        with (
            patch("saipenview.api.scan") as mock_scan,
            patch.object(api, "_set_cache") as mock_set_cache,
        ):
            mock_scan.return_value = []
            result = api.rescan()
            assert isinstance(result, list)
            mock_scan.assert_called_once()
            mock_set_cache.assert_called_once()


class TestSetScanTuning:
    """set_scan_tuning updates config and rebuilds scanner."""

    def test_clamps_values(self, api):
        result = api.set_scan_tuning(99, 9999, 5)
        assert result["scan_depth"] == 8  # max 8
        assert result["scan_delay_ms"] == 9999
        assert result["rescan_interval"] == 10  # min 10

    def test_starts_scanner_when_auto_scan(self, api):
        api._auto_scan = True
        with patch.object(api.background_scanner, "stop"):
            with patch.object(api.background_scanner, "start"):
                result = api.set_scan_tuning(3, 50, 120)
                assert result["scan_depth"] == 3


class TestSetScanRoots:
    """set_scan_roots updates roots and rescans."""

    def test_sets_roots_and_rescans(self, api):
        with (
            patch.object(api, "_set_cache"),
            patch("saipenview.api.scan", return_value=[]),
        ):
            result = api.set_scan_roots(["D:\\projects"])
            assert api._config["scan_roots"] == ["D:\\projects"]
            assert isinstance(result, list)


class TestSetExcludeDirs:
    """set_exclude_dirs updates config and rescans."""

    def test_sets_excludes_and_rescans(self, api):
        with patch.object(api, "rescan", return_value=[]):
            result = api.set_exclude_dirs(["node_modules", "dist"])
            assert api._config["exclude_dirs"] == ["node_modules", "dist"]
            assert isinstance(result, list)


class TestClipboardCopy:
    """clipboard_copy uses PowerShell Set-Clipboard."""

    def test_copies_text(self, api):
        with patch("subprocess.run") as mock_run:
            result = api.clipboard_copy("test text")
            assert result is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "powershell"
            # Command rides as a base64 UTF-16LE blob, so the payload is data.
            decoded = base64.b64decode(args[3]).decode("utf-16-le")
            assert decoded == "Set-Clipboard -Value 'test text'"

    def test_handles_exception(self, api):
        with patch("subprocess.run", side_effect=OSError("no powershell")):
            result = api.clipboard_copy("test")
            assert result is False

    def test_payload_is_data_not_powershell_code(self, api):
        # A copied string containing $()/backtick must be passed as a literal
        # value, never parsed as PowerShell. EncodedCommand base64 must decode
        # to a single-quoted Set-Clipboard literal that cannot interpolate.
        payload = '$(Start-Process calc) `evil` "quote"'
        with patch("subprocess.run") as mock_run:
            result = api.clipboard_copy(payload)
            assert result is True
            args = mock_run.call_args[0][0]
            assert args[0] == "powershell"
            assert args[2] == "-EncodedCommand"
            decoded = base64.b64decode(args[3]).decode("utf-16-le")
            assert decoded.startswith("Set-Clipboard -Value '")
            # The raw payload must appear inside the PS single-quoted literal
            # with only ' doubled -- never as live PS code after the string.
            assert "$(Start-Process calc)" in decoded
            assert decoded.count("'" ) == 2 + payload.count("'")

    def test_run_has_a_timeout(self, api):
        with patch("subprocess.run") as mock_run:
            api.clipboard_copy("x")
            kwargs = mock_run.call_args[1]
            assert kwargs.get("timeout") is not None


class TestStartStop:
    """start/stop lifecycle."""

    def test_start_starts_scanner(self, api):
        api._auto_scan = True
        with patch.object(api.background_scanner, "start") as mock_start:
            api.start()
            mock_start.assert_called_once()

    def test_stop_stops_scanner(self, api):
        with patch.object(api.background_scanner, "stop") as mock_stop:
            api.stop()
            mock_stop.assert_called_once()


class TestAutoScan:
    """set_auto_scan toggles background scanning."""

    def test_enable_starts_scanner(self, api):
        with patch.object(api.background_scanner, "start") as mock_start:
            result = api.set_auto_scan(True)
            assert result["auto_scan"] is True
            mock_start.assert_called_once()

    def test_disable_stops_scanner(self, api):
        with patch.object(api.background_scanner, "stop") as mock_stop:
            result = api.set_auto_scan(False)
            assert result["auto_scan"] is False
            mock_stop.assert_called_once()


class TestSetAlwaysOnTop:
    """set_always_on_top updates config."""

    def test_sets_config(self, api):
        result = api.set_always_on_top(False)
        assert result["always_on_top"] is False


class TestGetAutostart:
    """get_autostart_enabled/delegates to autostart module."""

    def test_returns_autostart_state(self, api):
        with patch("saipenview.autostart.is_enabled", return_value=True):
            assert api.get_autostart_enabled() is True


class TestRunCommand:
    """run_command opens cmd.exe with the given command."""

    def test_runs_command(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("subprocess.Popen") as mock_popen:
            result = api.run_command(str(d), "npm test")
            assert result is True
            mock_popen.assert_called_once()

    def test_handles_exception(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "test-dir")
        with patch("subprocess.Popen", side_effect=OSError("cmd failed")):
            result = api.run_command(str(d), "npm test")
            assert result is False


class TestCollectOutboxAPI:
    """collect_outbox delegates to parser.collect_outbox_entry and rescans."""

    def test_collect_calls_entry_and_rescans(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "proj")

        with (
            patch("saipenview.parser.collect_outbox_entry") as mock_collect,
            patch.object(api, "rescan"),
            patch.object(api, "get_project_detail", return_value={"name": "proj"}),
        ):
            mock_collect.return_value = {
                "ok": True,
                "ticket_id": "T-001",
                "message": "created",
            }
            result = api.collect_outbox(str(d), "saihunt", "HUNT-001")
            assert result["ok"] is True
            assert "updated_detail" in result


class TestToggleTicketStatus:
    """toggle_ticket_status calls move_ticket and returns updated detail."""

    def test_returns_detail_on_success(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "proj")
        (tmp_path / "proj" / ".saipen" / "BOARD.md").write_text(
            "# BOARD\n\n## TODO\n- [ ] T-001 | test\n\n## DOING\n\n## DONE\n\n",
            encoding="utf-8",
        )

        with (
            patch(
                "saipenview.parser.move_ticket",
                return_value={"ok": True, "code": "CLAIMED"},
            ),
            patch.object(api, "get_project_detail", return_value={"name": "proj"}),
        ):
            result = api.toggle_ticket_status(str(d), "T-001", "start")
            assert result is not None
            assert result["updated_detail"]["name"] == "proj"

    def test_returns_refusal_on_failure(self, api, tmp_path):
        d = _seed_verified_root(api, tmp_path / "proj")
        with patch(
            "saipenview.parser.move_ticket",
            return_value={"ok": False, "code": "ILLEGAL_PHASE", "message": "no"},
        ):
            result = api.toggle_ticket_status(str(d), "T-001", "done")
            assert result is not None
            assert result["ok"] is False
            assert result["code"] == "ILLEGAL_PHASE"


class TestGetLinkedWorktrees:
    """get_linked_worktrees returns cached worktree list."""

    def test_returns_copy_of_linked_worktrees(self, api):
        api._linked_worktrees = [{"name": "wt1"}]
        result = api.get_linked_worktrees()
        assert len(result) == 1
        assert result[0]["name"] == "wt1"


class TestQuit:
    """quit calls the registered callback."""

    def test_calls_quit_callback(self, api):
        called = False

        def on_quit():
            nonlocal called
            called = True

        api._on_quit = on_quit
        api.quit()
        assert called is True

    def test_noop_when_no_callback(self, api):
        api._on_quit = None
        api.quit()  # Should not raise


class TestMoveBy:
    """move_by delegates to window."""

    def test_calls_window_move_by(self, api):
        mock_window = MagicMock()
        api._window = mock_window
        api.move_by(10, 20)
        mock_window.move_by.assert_called_once_with(10, 20)

    def test_noop_when_no_window(self, api):
        api._window = None
        api.move_by(10, 20)  # Should not raise


class TestSaveViewConfig:
    """save_view_config merges settings and persists."""

    def test_merges_settings(self, api, api_patches):
        result = api.save_view_config({"compact_mode": True, "locale": "zh-CN"})
        assert result["compact_mode"] is True
        assert result["locale"] == "zh-CN"


class TestSetHotkeys:
    """set_hotkeys validates and registers hotkeys."""

    def test_reverts_on_failure(self, api):
        # First call raises, revert call succeeds
        fail = MagicMock(side_effect=[ValueError("invalid"), None])
        api._on_hotkeys_changed = fail
        api._config["hotkeys"] = ["ctrl+alt+x"]
        result = api.set_hotkeys(["ctrl+alt+bad"])
        assert result is not None

    def test_noop_without_callback(self, api):
        api._on_hotkeys_changed = None
        result = api.set_hotkeys(["ctrl+alt+x"])
        assert result is not None


class TestGetLocales:
    """get_locales returns available locale list."""

    def test_returns_two_locales(self, api):
        locales = api.get_locales()
        assert len(locales) == 34
        codes = [loc["code"] for loc in locales]
        assert "en" in codes
        assert "zh-CN" in codes


class TestGetLocalDrives:
    """get_local_drives delegates to scanner.local_drives."""

    def test_returns_drives(self, api):
        with patch("saipenview.scanner.local_drives", return_value=["C:\\", "D:\\"]):
            drives = api.get_local_drives()
            assert "C:\\" in drives


class TestBrowseFolderQuarantine:
    """browse_folder must not forget stale roots (T-165)."""

    def test_missing_root_survives_browse_folder(self, api, tmp_path):
        stale = str(tmp_path / "gone-drive")
        new_dir = tmp_path / "picked"
        new_dir.mkdir()
        api._config["scan_roots"] = [stale]

        with (
            patch("saipenview.api.tk.Tk"),
            patch("saipenview.api.filedialog.askdirectory", return_value=str(new_dir)),
            patch("saipenview.api.scan", return_value=[]),
            patch("saipenview.api.save_config"),
        ):
            api.browse_folder()

        roots = api._config["scan_roots"]
        assert any("gone-drive" in r for r in roots), (
            "a missing root was dropped from scan_roots by browse_folder -- "
            "the quarantine invariant T-138 built requires it to stay"
        )
        assert any("picked" in r for r in roots), (
            "the newly picked folder was not added"
        )

    def test_single_worktree_scan_in_rescan(self, api, api_patches):
        with (
            patch("saipenview.api.scan", return_value=[]),
            patch.object(api, "_scan_linked_worktrees") as mock_wt,
        ):
            api.rescan()
            assert mock_wt.call_count == 1, (
                f"_scan_linked_worktrees ran {mock_wt.call_count} times per rescan -- "
                "_set_cache is its single owner, rescan must not repeat it"
            )

    def test_single_worktree_scan_in_browse_folder(self, api, tmp_path):
        new_dir = tmp_path / "picked"
        new_dir.mkdir()
        with (
            patch("saipenview.api.tk.Tk"),
            patch("saipenview.api.filedialog.askdirectory", return_value=str(new_dir)),
            patch("saipenview.api.scan", return_value=[]),
            patch("saipenview.api.save_config"),
            patch.object(api, "_scan_linked_worktrees") as mock_wt,
        ):
            api.browse_folder()
        assert mock_wt.call_count == 1, (
            f"_scan_linked_worktrees ran {mock_wt.call_count} times per browse -- "
            "_set_cache is its single owner"
        )


# ── T-591 / PERF-002: idle polling must not re-parse the whole tree ──


class TestIdlePolling:
    @pytest.fixture
    def idle_api(self, api):
        calls = {"load": 0}

        class _FakeProj:
            def __init__(self, root):
                self.root = Path(root)

        def fake_load(*args, **kwargs):
            calls["load"] += 1
            root = args[0] if args else Path("/mock/project")
            return _FakeProj(root)

        def fake_to_dict(project, pinned=None):
            return {
                "root": str(project.root),
                "name": "mock",
                "phase": "X",
                "mtime": 0,
                "is_pinned": False,
                "conformance": {"verdict": "pass"},
            }

        api._build_ticket_index = MagicMock()
        api._write_cache = MagicMock()
        api._sync_watcher = MagicMock()
        import saipenview.api as api_mod

        orig_load = api_mod.load_project
        orig_to = api_mod._project_to_dict
        api_mod.load_project = fake_load
        api_mod._project_to_dict = fake_to_dict
        api._projects = [
            {
            "root": "/mock/project",
            "name": "mock",
            "phase": "X",
            "mtime": 0,
            "is_pinned": False,
            "conformance": {"verdict": "pass"},
            "git_branch": "",
            "git_dirty": False,
            }
        ]
        api._has_scanned = True
        api._scanning = False
        api._full_refresh_pending = True  # startup -> one full parse
        yield api, calls
        api_mod.load_project = orig_load
        api_mod._project_to_dict = orig_to

    def test_idle_revision_refresh_returns_metadata(self, idle_api):
        api, calls = idle_api
        api.refresh_known()
        calls["load"] = 0
        revision = api.get_status()["revision"]
        result = api.refresh_known(revision)
        assert result == {"revision": revision, "changed_roots": [], "projects": None}
        assert calls["load"] == 0

    def test_idle_poll_skips_reparse(self, idle_api):
        api, calls = idle_api
        # First call: startup pending -> full reconciliation parse.
        api.refresh_known()
        assert calls["load"] == 1, calls
        # Second call: idle (pending cleared, not scanning) -> NO re-parse.
        calls["load"] = 0
        api.refresh_known()
        assert calls["load"] == 0, "idle poll must not call load_project"
        # A scan result flips the pending flag -> next poll reconciles once.
        api._full_refresh_pending = True
        api.refresh_known()
        assert calls["load"] == 1, "post-scan poll must reconcile"

    def test_idle_poll_reports_no_changes(self, idle_api):
        api, calls = idle_api
        api.refresh_known()  # startup pending -> one full reconciliation parse
        calls["load"] = 0
        api._full_refresh_pending = False
        api.refresh_known()  # idle -> no re-parse, preserves existing changed set
        assert calls["load"] == 0, "idle poll must not call load_project"
        # After first refresh populates changed_roots, idle poll must NOT clear
        # them -- get_changed_roots should still deliver the prior refresh's roots
        # (T-39 / W2-029: destructive mailbox must not leak-unread entries).
        assert api.get_changed_roots() == ["/mock/project"]

    def test_idle_poll_preserves_unread_changed_roots(self, idle_api):
        """T-39: an idle refresh between change population and consumption
        must not swallow an unread changed set.
        R1 populates ['rootA']; idle R2 arrives before consumer reads;
        get_changed_roots() still returns ['rootA'].
        """
        api, calls = idle_api
        api.refresh_known()  # startup -> populates _refresh_changed_roots
        calls["load"] = 0
        # Simulate: a second idle refresh arrives BEFORE the frontend consumed.
        api._full_refresh_pending = False
        api.refresh_known()  # idle short-circuit -- must NOT clear preserved set
        # First consumer call still sees the original changed roots.
        assert api.get_changed_roots() == ["/mock/project"]


# ── T-590 / PERF-001: scan worktrees must pass through, not be re-walked ──


class TestWorktreePassthrough:
    def test_scanoutcome_worktrees_skip_second_walk(self, api):
        from saipenview.scanner import ScanOutcome

        api._scan_linked_worktrees = MagicMock()
        outcome = ScanOutcome(
            projects=[], worktrees=[{"root": "/x", "git_dir": "/x/.git"}]
        )
        api._set_cache(outcome)
        assert api._scan_linked_worktrees.call_count == 0, (
            "worktrees from ScanOutcome must skip the linked-worktree walk"
        )
        assert api._linked_worktrees == [{"root": "/x", "git_dir": "/x/.git"}]

    def test_worktree_kwarg_skip_second_walk(self, api):
        api._scan_linked_worktrees = MagicMock()
        api._set_cache([], worktrees=[{"root": "/y"}])
        assert api._scan_linked_worktrees.call_count == 0
        assert api._linked_worktrees == [{"root": "/y"}]

    def test_no_worktrees_falls_back_to_walk(self, api):
        api._scan_linked_worktrees = MagicMock()
        api._set_cache([])  # plain list, no worktrees -> must still walk
        assert api._scan_linked_worktrees.call_count == 1


# ── T-589 / W2-010: setter result contracts must surface failure (ok:false) ──


class TestSetterResultContracts:
    def test_hotkeys_binding_failure_is_ok_false(self, api):
        # First call (new binding) raises; revert (second call) succeeds.
        api._on_hotkeys_changed = MagicMock(side_effect=[ValueError("bad combo"), None])
        api._config["hotkeys"] = []
        result = api.set_hotkeys(["ctrl+x"])
        assert result.get("ok") is False, result
        assert "error" in result

    def test_hotkeys_success_returns_config(self, api):
        api._on_hotkeys_changed = MagicMock()
        api._config["hotkeys"] = []
        result = api.set_hotkeys(["ctrl+x"])
        # Success path has no `ok` key (it is a config dict) -> not a failure.
        assert result.get("ok") is not False

    def test_snap_hotkey_binding_failure_is_ok_false(self, api):
        api._on_snap_hotkey_changed = MagicMock(
            side_effect=[Exception("kbd fail"), None]
        )
        api._config["snap_hotkey"] = []
        result = api.set_snap_hotkey(["ctrl+s"])
        assert result.get("ok") is False, result

    def test_engine_overrides_invalid_is_ok_false(self, api):
        # `path` must be a string -> 123 is invalid.
        result = api.set_engine_overrides({"openai": {"path": 123}})
        assert result.get("ok") is False, result

    def test_autostart_false_is_not_counted_as_applied(self, api):
        # set_autostart_enabled returns a bool; a False return is a failure
        # signal that runSeq must NOT count as applied.
        import saipenview.autostart as autostart_mod

        with patch.object(autostart_mod, "set_enabled", return_value=False):
            assert api.set_autostart_enabled(True) is False


# ── T-587 / W2-008: clean disappearance vs transient read failure ──


class TestRefreshKnownDisappearance:
    @pytest.fixture
    def fresh_api(self, api):
        import saipenview.api as api_mod

        api._build_ticket_index = MagicMock()
        api._write_cache = MagicMock()
        api._sync_watcher = MagicMock()
        orig_to = api_mod._project_to_dict
        api_mod._project_to_dict = lambda p, pin=None: {
            "root": str(p.root),
            "name": "m",
            "phase": "X",
            "mtime": 0,
            "is_pinned": False,
            "conformance": {"verdict": "pass"},
            "git_branch": "",
            "git_dirty": False,
        }
        api._projects = [
            {
                "root": "/mock/project",
                "name": "m",
                "phase": "X",
                "mtime": 0,
                "is_pinned": False,
                "conformance": {"verdict": "pass"},
                "git_branch": "",
                "git_dirty": False,
            }
        ]
        api._has_scanned = True
        api._scanning = False
        api._full_refresh_pending = True
        yield api
        api_mod._project_to_dict = orig_to

    def test_clean_disappearance_drops_row_and_signals(self, fresh_api):
        import saipenview.api as api_mod

        orig = api_mod.load_project
        api_mod.load_project = lambda *a, **k: None  # STATE.md gone, no raise
        try:
            fresh_api.refresh_known()
        finally:
            api_mod.load_project = orig
        assert all(p["root"] != "/mock/project" for p in fresh_api._projects)
        assert "/mock/project" in fresh_api.get_changed_roots()

    def test_transient_failure_keeps_row(self, fresh_api):
        import saipenview.api as api_mod

        orig = api_mod.load_project

        def boom(*a, **k):
            raise OSError("disk blip")

        api_mod.load_project = boom
        try:
            fresh_api.refresh_known()
        finally:
            api_mod.load_project = orig
        assert any(p["root"] == "/mock/project" for p in fresh_api._projects)
        assert "/mock/project" not in fresh_api.get_changed_roots()


# ── CORE-003 / PERF-007: get_hidden_projects must not scan ──


class TestHiddenProjectsNoScan:
    def test_returns_registry_rows_no_scan(self, api_with_projects):
        """CORE-003/PERF-007: get_hidden_projects snaps _projects, never calls scan()."""
        api_with_projects._config["hidden_roots"] = [
            str(api_with_projects._projects[0]["root"])
        ]
        with patch("saipenview.api.scan") as mock_scan:
            result = api_with_projects.get_hidden_projects()
            assert len(result) >= 1
            assert mock_scan.call_count == 0

    def test_empty_when_none_hidden(self, api_with_projects):
        api_with_projects._config["hidden_roots"] = []
        result = api_with_projects.get_hidden_projects()
        assert result == []
