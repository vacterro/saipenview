"""T-35 / W2-025: record_manual_work external-change ack scope too broad.

The UI sends no (path, token) set. Api snapshots get_registry().pending(root)
at RPC arrival and acknowledges every token in the server-side snapshot for
any result.get(ok). A delayed duplicate of a completed operation_id arriving
after a new external write receives ALREADY_RECORDED and clears the newer
event without creating LOG/BOARD evidence.

Fix: accept explicit ack_tokens from caller; bind to operation_id; replay
same set on retry. Without explicit set, fall back to all-pending for
backward compat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saipenview.api import Api
from saipenview.external_changes import get_registry
from tests.conftest import make_conformant_project


@pytest.fixture
def api(tmp_path: Path):
    from unittest.mock import MagicMock, patch
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
        m.is_running.return_value = False
        mock_scanner_cls.return_value = m
        mock_watcher_cls.return_value = m
        mock_pm_cls.return_value = m
        mock_coord.return_value.is_protocol_file.return_value = True
        mock_coord.return_value.root_for.return_value = str(tmp_path)
        # W2-025: _guard_protocol_write must return None (no agent running)
        type(mock_coord.return_value)._guard_protocol_write = property(
            lambda self: None
        )
        mock_coord.return_value.fingerprint.return_value = "abc123"

        instance = Api(debounce_delay=0.0)
        try:
            yield instance
        finally:
            instance.stop()


def test_ack_tokens_bounds_scope(api: Api, tmp_path: Path):
    """Only observed tokens acknowledged; newer token stays pending."""
    from tests.conftest import make_conformant_project
    root = make_conformant_project(tmp_path)

    # Register root so api knows about it
    api._config["pinned_roots"] = [str(root)]

    # Record an external change token A
    get_registry().record(str(root), "BOARD.md", "fp-a")
    tokens = get_registry().pending(str(root))
    token_a = tokens[0].token if tokens else None
    assert token_a is not None

    # Record a second external change token B
    get_registry().record(str(root), "STATE.md", "fp-b")
    tokens = get_registry().pending(str(root))
    token_b = [t for t in tokens if t.token != token_a][0].token

    # Call record_manual_work with ONLY token A in ack_tokens
    result = api.record_manual_work(
        str(root), "fixed docs", "mw-scoped-1",
        ack_tokens=[("BOARD.md", token_a)],
    )
    assert result["ok"] is True, result

    # Token A should be acknowledged (gone), token B should remain
    remaining = get_registry().pending(str(root))
    remaining_tokens = {t.token for t in remaining}
    assert token_a not in remaining_tokens, "token A should be acknowledged"
    assert token_b in remaining_tokens, "token B must remain pending"
