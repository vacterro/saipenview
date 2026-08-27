"""T-26 / W2-016: watcher tracks nested OUTBOX/MANIFEST parser inputs.

The watcher only recognized STATE.md, BOARD.md, LOG.md in _TRACKED.
Nested kitchen/OUTBOX.md and subs MANIFEST.md were ignored even though
parser.load_subs() and load_outbox() depend on both. With auto_scan=False,
changes to these files left live state, persisted cache and ticket index
stale.

Fix: add OUTBOX.md and MANIFEST.md to _TRACKED; extend _file_affects_index/
_cache in api.py to include these filenames.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.api import Api
from saipenview.watcher import _TRACKED


def test_tracked_includes_outbox_and_manifest():
    """OUTBOX.md and MANIFEST.md must be in the watcher's tracked set."""
    assert "OUTBOX.md" in _TRACKED, "OUTBOX.md must be watched"
    assert "MANIFEST.md" in _TRACKED, "MANIFEST.md must be watched"
    # Existing tracked files still present
    assert "STATE.md" in _TRACKED
    assert "BOARD.md" in _TRACKED
    assert "LOG.md" in _TRACKED


def test_file_affects_index_catches_outbox_and_manifest():
    """_file_affects_index returns True for OUTBOX and MANIFEST at any depth."""
    assert Api._file_affects_index("OUTBOX.md") is True
    assert Api._file_affects_index("MANIFEST.md") is True
    assert Api._file_affects_index("extensions/subs/saihunt/kitchen/OUTBOX.md") is True
    assert Api._file_affects_index(".saipen/extensions/subs/x/MANIFEST.md") is True
    # Existing tracked files still work
    assert Api._file_affects_index("STATE.md") is True
    assert Api._file_affects_index("BOARD.md") is True
    assert Api._file_affects_index("BOARD") is True
    # Unrelated files still rejected
    assert Api._file_affects_index("LOG.md") is False
    assert Api._file_affects_index("config.json") is False


def test_file_affects_cache_catches_outbox_and_manifest():
    """_file_affects_cache delegates to _file_affects_index."""
    assert Api._file_affects_cache("OUTBOX.md") is True
    assert Api._file_affects_cache("MANIFEST.md") is True
    assert Api._file_affects_cache("STATE.md") is True
    assert Api._file_affects_cache("LOG.md") is False


def test_refresh_one_project_uses_changed_files_classifier(api: Api, tmp_path: Path):
    """_refresh_one_project passes changed_files through _file_affects_index."""
    from unittest.mock import MagicMock, patch

    # Patch load_project to return a valid ProjectStatus
    mock_proj = MagicMock()
    mock_proj.root = tmp_path
    mock_proj.state = {"phase": "PLAN", "task": "none"}
    mock_proj.board = MagicMock()
    mock_proj.board.counts.return_value = {"doing": 0, "todo": 0, "done": 0, "blocked": 0}
    mock_proj.subs = []
    mock_proj.translate = None
    mock_proj.mtime = 0
    mock_proj.subs_stale = False
    mock_proj.subs_stale_details = []
    mock_proj.quick_actions = []
    mock_proj.git_branch = ""
    mock_proj.git_dirty = False

    with patch("saipenview.api.load_project", return_value=mock_proj):
        api._projects = [{"root": str(tmp_path), "name": "test"}]
        api._write_cache = patch.object(api, "_write_cache")
        api._build_ticket_index = patch.object(api, "_build_ticket_index")
        api._write_cache.start()
        api._build_ticket_index.start()

        # OUTBOX change should trigger both cache and index
        api._refresh_one_project(
            str(tmp_path),
            changed_files={"extensions/subs/saihunt/kitchen/OUTBOX.md"},
        )
        api._write_cache.assert_called_once()
        api._build_ticket_index.assert_called_once()

        api._write_cache.stop()
        api._build_ticket_index.stop()


@pytest.fixture
def api(tmp_path: Path):
    from unittest.mock import MagicMock
    with (
        patch("saipenview.api.config_path") as mock_cfg_path,
        patch("saipenview.api.load_config") as mock_load,
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner") as mock_scanner_cls,
        patch("saipenview.api.SaipenWatcher") as mock_watcher_cls,
        patch("saipenview.api.ProcessManager") as mock_pm_cls,
        patch("saipenview.protocol_write.get_coordinator") as mock_coord,
    ):
        mock_load.return_value = {
            "pinned_roots": [], "hidden_roots": [], "sort_order": "smart",
            "scan_roots": None, "auto_scan": False, "rescan_interval": 30,
            "scan_depth": 6, "scan_delay_ms": 10, "exclude_dirs": [],
            "agent_output_buffer_size": 5000,
        }
        data_dir = tmp_path / "_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        mock_cfg_path.return_value = data_dir / "config.json"
        m = MagicMock()
        mock_scanner_cls.return_value = m
        mock_watcher_cls.return_value = m
        mock_pm_cls.return_value = m
        mock_coord.return_value.is_protocol_file.return_value = False
        mock_coord.return_value.root_for.return_value = None

        instance = Api(debounce_delay=0.0)
        try:
            yield instance
        finally:
            instance.stop()
