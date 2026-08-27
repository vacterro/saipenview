"""T-27 / W2-017: read_file_text ordinary-file branch returns text.

The ordinary file path decoded text into `text` but never returned it —
only the protocol branch had a return statement. Allowed notes.md reads
returned None instead of the file content.

Fix: add `return text` after the protocol branch for ordinary files.
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
        mock_coord.return_value.is_protocol_file.return_value = False
        mock_coord.return_value.root_for.return_value = None

        instance = Api(debounce_delay=0.0)
        try:
            yield instance
        finally:
            instance.stop()


def test_read_ordinary_md_returns_text(api: Api, tmp_path: Path):
    """Allowed .md file returns decoded string, not None."""
    (tmp_path / ".saipen").mkdir()
    (tmp_path / ".saipen" / "STATE.md").write_text("---\nphase: PLAN\n---\n", encoding="utf-8")
    api._config["pinned_roots"] = [str(tmp_path)]
    f = tmp_path / "notes.md"
    f.write_text("hello world\n", encoding="utf-8")
    result = api.read_file_text(str(f))
    assert result == "hello world\n", f"expected text, got {result!r}"


def test_read_ordinary_json_returns_text(api: Api, tmp_path: Path):
    """Allowed .json file returns decoded string, not None."""
    (tmp_path / ".saipen").mkdir()
    (tmp_path / ".saipen" / "STATE.md").write_text("---\nphase: PLAN\n---\n", encoding="utf-8")
    api._config["pinned_roots"] = [str(tmp_path)]
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}\n', encoding="utf-8")
    result = api.read_file_text(str(f))
    assert result == '{"key": "value"}\n', f"expected text, got {result!r}"


def test_read_nonexistent_returns_none(api: Api, tmp_path: Path):
    """Non-existent file returns None."""
    (tmp_path / ".saipen").mkdir()
    (tmp_path / ".saipen" / "STATE.md").write_text("---\nphase: PLAN\n---\n", encoding="utf-8")
    api._config["pinned_roots"] = [str(tmp_path)]
    result = api.read_file_text(str(tmp_path / "missing.md"))
    assert result is None


def test_read_file_text_source_has_return(api: Api):
    """Verify the source code contains the ordinary-file return path."""
    import inspect
    source = inspect.getsource(Api.read_file_text)
    # After the protocol branch, there must be a return text for ordinary files
    assert "return text" in source, "read_file_text must return text for ordinary files"
