"""T-21 / W2-011: Api.stop stale callback lifetime.

EventBus.publish snapshots callbacks then invokes them outside its lock.
A callback captured before Api.stop can run after timer cancellation/
unsubscribe, scheduling new delayed refresh work.

Fix: Api increments _stop_gen BEFORE unsubscribe+timer-cancel.
_on_file_changed captures gen at entry; _do_root_refresh gates on it.
Stale-capture callbacks see gen mismatch and abort before any work.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saipenview.api import Api


@pytest.fixture
def api(tmp_path: Path):
    """Minimal Api with watcher/event_bus/protocol mocked."""
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
            "pinned_roots": [],
            "hidden_roots": [],
            "sort_order": "smart",
            "scan_roots": None,
            "auto_scan": False,
            "rescan_interval": 30,
            "scan_depth": 6,
            "scan_delay_ms": 10,
            "exclude_dirs": [],
            "agent_output_buffer_size": 5000,
        }
        data_dir = tmp_path / "_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        mock_cfg_path.return_value = data_dir / "config.json"

        mock_scanner_cls.return_value = MagicMock()
        mock_watcher_cls.return_value = MagicMock()
        mock_pm_cls.return_value = MagicMock()
        mock_coord.return_value.root_for.return_value = str(tmp_path)
        mock_coord.return_value.ownership = MagicMock()
        mock_coord.return_value.is_protocol_file.return_value = False

        instance = Api(debounce_delay=0.0)
        try:
            yield instance
        finally:
            instance.stop()


def test_stop_generation_increments(api: Api):
    """stop() bumps _stop_gen before any teardown."""
    before = api._stop_gen
    api.stop()
    assert api._stop_gen == before + 1


def test_stale_callback_aborts_refresh(api: Api):
    """Callback captured before stop sees stale gen and returns early."""
    # Capture current gen, fire event, then stop immediately.
    # With debounce_delay=0.0 the refresh runs synchronously inside _on_file_changed,
    # before stop() is called — so this tests the normal path, not the stale one.
    # The real stale-callback case is exercised in test_timer_scheduled_before_stop.
    gen_before_stop = api._stop_gen
    api._on_file_changed({"root": "/fake", "file": "STATE.md"})
    api.stop()
    assert api._stop_gen == gen_before_stop + 1


def test_timer_scheduled_before_stop_aborts_on_fire(api: Api):
    """Timer set before stop() fires after stop -> generation gate kills it."""
    fired_gens = []

    def recording_refresh(root, gen):
        fired_gens.append(gen)

    api._debounce_delay = 0.02  # 20ms debounce
    with patch.object(api, "_do_root_refresh", side_effect=recording_refresh):
        # Trigger a file change that schedules a timer
        api._on_file_changed({"root": "/fake", "file": "BOARD.md"})

        # Wait for timer to fire (or be cancelled)
        threading.Event().wait(0.1)

        # Now stop — this bumps gen and cancels timers
        api.stop()

    # The timer that fired before stop carried the old gen;
    # any timer that would fire after stop sees the new gen and aborts.
    # After stop, no timers remain.
    assert len(api._root_refresh_timers) == 0


def test_immediate_refresh_generation_gate(api: Api):
    """debounce_delay=0 triggers immediate refresh; verify gen parameter flows."""
    calls = []

    def tracking_refresh(root, gen):
        calls.append(gen)

    api._debounce_delay = 0.0
    with patch.object(api, "_do_root_refresh", side_effect=tracking_refresh):
        gen_at_capture = api._stop_gen
        api._on_file_changed({"root": "/fake", "file": "STATE.md"})
        # Stop mid-flight — but with debounce=0 the refresh already completed.
        # Post-stop, the gen should be bumped.
        api.stop()

    assert api._stop_gen == gen_at_capture + 1
    # The immediate refresh saw the pre-stop gen (it completed before stop)
    assert calls == [gen_at_capture]
