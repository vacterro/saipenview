"""T-32 / W2-022: Api.__init__ partial initialization publishes global state.

Api subscribed _on_file_changed to global EventBus BEFORE SaipenWatcher
construction. A watcher-constructor failure left the callback registered
on the EventBus pointing at a partially initialized Api.

Fix: move event_bus.subscribe from __init__ to start(). Constructor is
side-effect free; callback only registered once fully built.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saipenview.api import Api
from saipenview.events import event_bus


def test_init_does_not_subscribe_to_eventbus(tmp_path: Path):
    """Constructing Api does NOT register on EventBus."""
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

        before = len(event_bus._subscribers.get("saipen.project_changed", []))
        api = Api(debounce_delay=0.0)
        after = len(event_bus._subscribers.get("saipen.project_changed", []))

        assert after == before, (
            "Api.__init__ must not subscribe to EventBus; "
            f"subscriber count changed {before} -> {after}"
        )
        api.stop()


def test_start_subscribes_to_eventbus(tmp_path: Path):
    """Api.start() registers the callback on EventBus."""
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

        before = len(event_bus._subscribers.get("saipen.project_changed", []))
        api = Api(debounce_delay=0.0)
        api.start()
        after = len(event_bus._subscribers.get("saipen.project_changed", []))

        assert after == before + 1, (
            f"Api.start() must subscribe; expected {before+1}, got {after}"
        )
        api.stop()
        # After stop, unsubscribe should remove the callback
        after_stop = len(event_bus._subscribers.get("saipen.project_changed", []))
        assert after_stop == before, (
            f"Api.stop() must unsubscribe; expected {before}, got {after_stop}"
        )


def test_source_has_no_subscribe_in_init():
    """Verify the source code moved subscribe out of __init__."""
    import inspect
    init_source = inspect.getsource(Api.__init__)
    assert "event_bus.subscribe" not in init_source, (
        "event_bus.subscribe must not be in __init__"
    )
    start_source = inspect.getsource(Api.start)
    assert "event_bus.subscribe" in start_source, (
        "event_bus.subscribe must be in start()"
    )
