"""Tests for saipenview.config — settings persistence."""

from __future__ import annotations

import json


class TestDefaults:
    """DEFAULTS dict is complete and well-typed."""

    def test_has_all_keys(self):
        from saipenview.config import DEFAULTS

        assert "hotkeys" in DEFAULTS
        assert "snap_hotkey" in DEFAULTS
        assert "zoom_level" in DEFAULTS
        assert "scan_roots" in DEFAULTS
        assert "locale" in DEFAULTS
        assert "layout_swap" in DEFAULTS
        assert "top_panel_collapsed" in DEFAULTS
        assert "file_viewer_default" in DEFAULTS

    def test_hotkeys_are_lists(self):
        from saipenview.config import DEFAULTS

        assert isinstance(DEFAULTS["hotkeys"], list)
        assert isinstance(DEFAULTS["snap_hotkey"], list)

    def test_scan_roots_is_none(self):
        from saipenview.config import DEFAULTS

        assert DEFAULTS["scan_roots"] is None

    def test_file_viewer_default_valid(self):
        from saipenview.config import DEFAULTS

        assert DEFAULTS["file_viewer_default"] in ("source", "reader")

    def test_locale_default(self):
        from saipenview.config import DEFAULTS

        assert DEFAULTS["locale"] == "en"


class TestLoadConfig:
    """load_config() returns correct values from disk."""

    def test_returns_defaults_when_no_file(self, tmp_config_path):
        """No config file on disk === all defaults."""
        from saipenview.config import load_config

        cfg = load_config()
        assert cfg["locale"] == "en"
        assert cfg["zoom_level"] == 1.0
        assert cfg["scan_roots"] is None

    def test_reads_stored_values(self, tmp_config_path):
        """Values written to disk are reflected on load."""
        from saipenview.config import load_config, save_config

        save_config({"zoom_level": 1.5, "locale": "zh-CN"})
        cfg = load_config()
        assert cfg["zoom_level"] == 1.5
        assert cfg["locale"] == "zh-CN"
        # Non-overridden keys stay default
        assert cfg["auto_scan"] is True

    def test_ignores_unknown_keys(self, tmp_config_path):
        """Keys not in DEFAULTS are silently ignored on load."""
        from saipenview.config import load_config, save_config

        save_config({"zoom_level": 0.75})
        # Manually inject unknown key
        path = tmp_config_path
        data = json.loads(path.read_text(encoding="utf-8"))
        data["nonexistent_key"] = "should_not_appear"
        path.write_text(json.dumps(data), encoding="utf-8")
        cfg = load_config()
        assert "nonexistent_key" not in cfg
        assert cfg["zoom_level"] == 0.75

    def test_migrates_string_snap_hotkey(self, tmp_config_path):
        """Old string snap_hotkey is auto-migrated to list.

        Deliberately NOT ctrl+q: that combo now has a migration of its own
        (below), and using it here would make this test pass or fail for the
        wrong reason."""
        from saipenview.config import load_config, save_config

        save_config({"snap_hotkey": "alt+f13"})
        cfg = load_config()
        assert isinstance(cfg["snap_hotkey"], list)
        assert cfg["snap_hotkey"] == ["alt+f13"]

    def test_strips_ctrl_q_from_snap_hotkey(self, tmp_config_path):
        """ctrl+q was freed in 4d291a0 but stayed in configs already on disk,
        where it kept firing the corner-snap globally from unrelated apps."""
        from saipenview.config import load_config, save_config

        save_config({"snap_hotkey": ["ctrl+q", "alt+f14"]})
        assert load_config()["snap_hotkey"] == ["alt+f14"]

    def test_stripping_ctrl_q_never_leaves_an_empty_list(self, tmp_config_path):
        """A hotkey list with nothing in it registers nothing, so the last
        slot falls back to the default rather than to silence."""
        from saipenview.config import DEFAULTS, load_config, save_config

        save_config({"snap_hotkey": ["ctrl+q"]})
        assert load_config()["snap_hotkey"] == list(DEFAULTS["snap_hotkey"])

    def test_ctrl_q_is_matched_regardless_of_spacing_or_case(self, tmp_config_path):
        """The settings field is free text and splits on commas, so the value
        that reaches disk can carry stray spacing or capitals."""
        from saipenview.config import load_config, save_config

        save_config({"snap_hotkey": ["Ctrl + Q", "alt+f14"]})
        assert load_config()["snap_hotkey"] == ["alt+f14"]

    def test_leaves_other_hotkeys_alone(self, tmp_config_path):
        """Only ctrl+q is stripped -- this is a targeted migration, not a
        filter that second-guesses whatever else the user has bound."""
        from saipenview.config import load_config, save_config

        save_config({"snap_hotkey": ["ctrl+alt+q", "alt+f14"]})
        assert load_config()["snap_hotkey"] == ["ctrl+alt+q", "alt+f14"]

    def test_handles_corrupt_json(self, tmp_config_path):
        """Corrupt JSON falls back to defaults with a stderr message (not crash)."""
        from saipenview.config import load_config

        tmp_config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_config_path.write_text("{bad json}", encoding="utf-8")
        cfg = load_config()
        assert cfg["locale"] == "en"  # fell back to defaults

    def test_canonicalizes_scan_roots_on_load(self, tmp_config_path):
        """Slash/case variants of the same root collapse to one canonical entry."""
        from saipenview.config import load_config, save_config

        save_config({"scan_roots": [r"C:\Foo", "c:/foo", r"C:\Bar"]})
        cfg = load_config()
        assert cfg["scan_roots"] == [r"c:\foo", r"c:\bar"]

    def test_canonicalizes_pinned_and_hidden_on_load(self, tmp_config_path):
        from saipenview.config import load_config, save_config

        save_config({"pinned_roots": ["C:\\Foo", "c:/foo"]})
        cfg = load_config()
        assert cfg["pinned_roots"] == [r"c:\foo"]

    def test_canonicalizes_selected_root_on_load(self, tmp_config_path):
        from saipenview.config import load_config, save_config

        save_config({"selected_root": r"C:\Foo\Bar" + "\\"})
        cfg = load_config()
        assert cfg["selected_root"] == r"c:\foo\bar"

    def test_empty_scan_roots_stays_empty_not_auto(self, tmp_config_path):
        """An explicit `scan_roots: []` means "scan nothing", and must not be
        promoted to None (auto-scan all drives) by canonicalization."""
        from saipenview.config import load_config, save_config

        save_config({"scan_roots": []})
        assert load_config()["scan_roots"] == []


class TestSaveConfig:
    """save_config() writes correctly and atomically."""

    def test_creates_file(self, tmp_config_path):
        from saipenview.config import DEFAULTS, save_config

        save_config(dict(DEFAULTS))
        assert tmp_config_path.is_file()

    def test_round_trip(self, tmp_config_path):
        from saipenview.config import DEFAULTS, load_config, save_config

        modified = dict(DEFAULTS)
        modified["zoom_level"] = 1.25
        modified["locale"] = "zh-CN"
        modified["layout_swap"] = True
        save_config(modified)

        loaded = load_config()
        assert loaded["zoom_level"] == 1.25
        assert loaded["locale"] == "zh-CN"
        assert loaded["layout_swap"] is True

    def test_strips_unknown_keys(self, tmp_config_path):
        from saipenview.config import DEFAULTS, save_config

        noisy = dict(DEFAULTS)
        noisy["bogus"] = "value"
        save_config(noisy)

        import json
        raw = json.loads(tmp_config_path.read_text(encoding="utf-8"))
        assert "bogus" not in raw

    def test_atomic_write_leaves_no_tmp(self, tmp_config_path):
        """After save, .tmp files are cleaned up."""
        from saipenview.config import DEFAULTS, save_config

        save_config(dict(DEFAULTS))
        tmp_files = list(tmp_config_path.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_snap_hotkey_stays_list_after_save(self, tmp_config_path):
        """List-typed snap_hotkey isn't flattened."""
        from saipenview.config import DEFAULTS, load_config, save_config

        cfg = dict(DEFAULTS)
        cfg["snap_hotkey"] = ["alt+f13", "alt+f14"]
        save_config(cfg)
        loaded = load_config()
        assert isinstance(loaded["snap_hotkey"], list)
        assert loaded["snap_hotkey"] == ["alt+f13", "alt+f14"]

    def test_atomic_replace_creates_file_with_content(self, tmp_config_path):
        """save_config uses os.replace — verify the file ends up at the right path."""
        from saipenview.config import DEFAULTS, save_config

        cfg = dict(DEFAULTS)
        cfg["locale"] = "zh-CN"
        save_config(cfg)

        # The file should exist at config_path() (not .tmp)
        assert tmp_config_path.is_file()
        tmp_files = list(tmp_config_path.parent.glob("*.tmp"))
        assert len(tmp_files) == 0
        import json
        data = json.loads(tmp_config_path.read_text(encoding="utf-8"))
        assert data["locale"] == "zh-CN"

    def test_config_path_returns_path(self):
        """config_path() returns a valid Path (covers the real function, not mocked)."""
        from pathlib import Path

        from saipenview.config import config_path

        result = config_path()
        assert isinstance(result, Path)
        assert result.name == "config.json"
