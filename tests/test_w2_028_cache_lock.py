"""T-38 / W2-028: _write_cache shared cache.json multi-backend overwrites.

Every Api instance used the same _data/cache.json but _cache_lock was
instance-local. Two Api-like writers with rows A and B resulted in the
final cache containing only whichever snapshot wrote last.

Fix: promote _cache_lock to module-level so all Api instances serialize
cache writes through one shared lock.
"""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saipenview.api import Api, _cache_lock


def test_cache_lock_is_module_level():
    """_cache_lock is a module-level Lock, not instance-local."""
    import saipenview.api as api_mod

    assert hasattr(api_mod, "_cache_lock")
    assert isinstance(api_mod._cache_lock, type(threading.Lock()))


def test_concurrent_writers_to_same_cache_file(tmp_path: Path):
    """Two Api instances writing to same cache file -> final cache is valid."""
    cfg = {
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
    cache_file = tmp_path / "cache.json"

    apis = []
    for i in range(3):
        with (
            patch("saipenview.api.config_path") as mock_cfg_path,
            patch("saipenview.api.load_config") as mock_load,
            patch("saipenview.api.save_config"),
            patch("saipenview.api.BackgroundScanner") as mock_scanner,
        ):
            mock_load.return_value = cfg
            mock_cfg_path.return_value = tmp_path / f"config{i}.json"
            mock_scanner.return_value = MagicMock()
            api = Api(debounce_delay=0.0)
            api._cache_file = cache_file
            apis.append(api)

    errors = []

    def writer(api, offset, count):
        try:
            for i in range(count):
                with api._lock:
                    api._projects = [{"root": f"r{i+offset}", "n": i}]
                api._write_cache()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(apis[0], 0, 10)),
        threading.Thread(target=writer, args=(apis[1], 100, 10)),
        threading.Thread(target=writer, args=(apis[2], 200, 10)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"writer errors: {errors}"
    assert cache_file.exists(), "cache file was not written"
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    # All writes should have been serialized; final cache should have valid rows
    roots = {r["root"] for r in data}
    assert len(roots) == len(data), "duplicate roots in cache"
    for api in apis:
        api.stop()
