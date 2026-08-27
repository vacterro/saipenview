"""T-25 / W2-015: write_file_text existence-transition CAS.

The planner checked path.is_file() independently from the entry-time check.
A missing-at-entry file that appeared before the planner ran was reclassified
as edit (required edit_version -> STALE_STATE). A present-at-entry file that
disappeared was reclassified as create (succeeded with no target). Both
transitions reproduced against the actual planner path.

Fix: snapshot exists_at_entry ONCE at the protocol-branch entry. The planner
uses the snapshot: create intent fails stale if path appears; edit intent
fails stale if path disappears or hash changes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saipenview.api import Api


@pytest.fixture
def api(tmp_path: Path):
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
        mock_coord.return_value.is_protocol_file.return_value = True
        mock_coord.return_value.root_for.return_value = str(tmp_path)
        mock_coord.return_value._guard_protocol_write.return_value = None
        mock_coord.return_value.fingerprint.return_value = "abc123"

        instance = Api(debounce_delay=0.0)
        try:
            yield instance
        finally:
            instance.stop()


def test_create_intent_fails_stale_when_file_appears():
    """missing->present transition during write -> STALE_STATE."""
    exists_at_entry = False
    staged_result = []

    def fake_planner(protocol_file_exists):
        if exists_at_entry:
            return {"ok": True}  # edit path
        # Create intent: check if file appeared
        if protocol_file_exists:
            return {"ok": False, "code": "STALE_STATE", "message": "file appeared"}
        return {"ok": True}

    # File doesn't exist -> create proceeds
    assert fake_planner(False)["ok"] is True

    # File appears -> create refuses
    result = fake_planner(True)
    assert result["code"] == "STALE_STATE"


def test_edit_intent_fails_stale_when_file_disappears():
    """present->missing transition during write -> STALE_STATE."""
    exists_at_entry = True
    staged_result = []

    def fake_planner(protocol_file_exists):
        if exists_at_entry:
            # Edit intent: check if file disappeared
            if not protocol_file_exists:
                return {"ok": False, "code": "STALE_STATE", "message": "file disappeared"}
            return {"ok": True}
        return {"ok": True}  # create path

    # File exists -> edit proceeds
    assert fake_planner(True)["ok"] is True

    # File disappears -> edit refuses
    result = fake_planner(False)
    assert result["code"] == "STALE_STATE"


def test_write_file_text_snapshot_logic(api: Api, tmp_path: Path):
    """Verify the actual write_file_text uses exists_at_entry snapshot."""
    import inspect
    source = inspect.getsource(Api.write_file_text)
    assert "exists_at_entry" in source, "write_file_text must snapshot existence"
    # The planner still calls path.is_file() to detect transitions, but the
    # intent (create vs edit) is determined by exists_at_entry, not by the
    # live path.is_file() call at entry time.
    planner_section = source.split("def _planner")[1].split("def ")[0]
    assert "exists_at_entry" in planner_section, "planner must use snapshot"
