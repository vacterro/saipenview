"""T-164: file boundary and write semantics.

The T-138 boundary was closed over `_known_roots()`, but that set included
scan roots -- which can be whole drives (`V:\\`). A scan root is discovery
scope, not file-access scope: nothing the viewer may read or write may be
reached through it. This locks the boundary to verified project roots and
locks write semantics to encoding/newline-preserving atomic replacement.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.api import Api
from saipenview.config import DEFAULTS

pytestmark = pytest.mark.skipif(
    __import__("conftest", fromlist=["canonical_home"]).canonical_home() is None,
    reason="canonical SAIPEN home unreachable (protocol writes are journaled "
    "through it)",
)

# ── Fixtures (mirror tests/test_api.py's mocking, without importing it) ──


@pytest.fixture
def api(tmp_path) -> Api:
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    with (
        patch("saipenview.api.config_path"),
        patch("saipenview.api.load_config", return_value=cfg),
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner"),
    ):
        api = Api()
        try:
            yield api
        finally:
            api.stop()


def _seed_project(root: Path, state_bytes: bytes | None = None) -> Path:
    from conftest import canonical_home

    home = canonical_home()
    saipen = root / ".saipen"
    saipen.mkdir(parents=True, exist_ok=True)
    payload = state_bytes or b"---\nphase: DONE\ntask: none\n---\n"
    # The canonical writer pipeline needs a resolvable saipen_home + a real
    # seat; inject them while preserving the seeded byte encoding/BOM/newline.
    if home is not None and b"saipen_home:" not in payload:
        import tempfile

        from saipenview import saio as _saio_mod

        fd, probe_name = tempfile.mkstemp()
        probe = Path(probe_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        codec = _saio_mod._load_codec_from(home)
        doc = codec.read_document(probe)
        probe.unlink()
        text = doc.text_norm.replace(
            "---\n", f"---\nsaipen_home: '{home}'\nagent: testseat\n", 1
        )
        payload = doc.encode(text)
    (saipen / "STATE.md").write_bytes(payload)
    (saipen / "BOARD.md").write_text(
        "# BOARD\n\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (saipen / "LOG.md").write_text(
        "- 11.08.26 00:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    return root


def _register(api: Api, root: Path) -> Path:
    api._config["pinned_roots"] = [str(root)]
    return root


class TestScanRootIsNotFileAccess:
    def test_scan_root_grants_no_read_access(self, api, tmp_path):
        """A bare scan root (whole dir with no .saipen/STATE.md) grants nothing."""
        api._config["scan_roots"] = [str(tmp_path)]
        secret = tmp_path / "secret.md"
        secret.write_text("secret\n", encoding="utf-8")
        assert api.read_file_text(str(secret)) is None
        assert api.write_file_text(str(secret), "pwned") is False
        assert secret.read_text(encoding="utf-8") == "secret\n"

    def test_scan_root_does_not_make_actions_work(self, api, tmp_path):
        """open_folder etc. refuse a root that is only a scan root."""
        api._config["scan_roots"] = [str(tmp_path)]
        with patch("os.startfile") as mock:
            assert api.open_folder(str(tmp_path)) is False
            mock.assert_not_called()

    def test_pinned_root_without_state_md_is_rejected(self, api, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        api._config["pinned_roots"] = [str(plain)]
        assert api.open_folder(str(plain)) is False


class TestVerifiedRootAccess:
    def test_protocol_files_readable_under_verified_root(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        board = root / ".saipen" / "BOARD.md"
        assert api.read_file_text(str(board)) is not None

    def test_unknown_root_is_controlled_error(self, api, tmp_path):
        _seed_project(tmp_path / "proj")  # has STATE.md but is not registered
        with patch("os.startfile") as mock:
            assert api.open_folder(str(tmp_path / "proj")) is False
            mock.assert_not_called()
        assert api.get_diff(str(tmp_path / "proj")) == {
            "ok": False,
            "error": "unknown or unverified project root",
        }

    def test_sibling_project_rejected(self, api, tmp_path):
        _register(api, _seed_project(tmp_path / "alpha"))
        sibling = _seed_project(tmp_path / "beta")
        assert api.read_file_text(str(sibling / ".saipen" / "STATE.md")) is None

    def test_dot_dot_escape_rejected(self, api, tmp_path):
        _register(api, _seed_project(tmp_path / "alpha"))
        target = tmp_path / "alpha" / ".." / "outside.md"
        target.write_text("x\n", encoding="utf-8")
        assert api.read_file_text(str(target)) is None


class TestWritePreservesEncodingAndNewline:
    def test_utf16le_is_preserved(self, api, tmp_path):
        raw = "---\nphase: DONE\ntask: none\n---\n".encode("utf-16-le")
        root = _register(api, _seed_project(tmp_path / "proj", raw))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        assert (
            api.write_file_text(
                str(f), "---\nphase: BUILD\ntask: T-1\n---\n", read["edit_version"]
            )
            is True
        )
        assert f.read_bytes() == "---\nphase: BUILD\ntask: T-1\n---\n".encode(
            "utf-16-le"
        )

    def test_utf8_bom_is_preserved(self, api, tmp_path):
        raw = b"\xef\xbb\xbf" + b"---\nphase: DONE\n---\n"
        root = _register(api, _seed_project(tmp_path / "proj", raw))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        assert (
            api.write_file_text(str(f), "---\nphase: BUILD\n---\n", read["edit_version"])
            is True
        )
        assert f.read_bytes() == b"\xef\xbb\xbf" + b"---\nphase: BUILD\n---\n"

    def test_crlf_is_preserved(self, api, tmp_path):
        raw = b"---\r\nphase: DONE\r\ntask: none\r\n---\r\n"
        root = _register(api, _seed_project(tmp_path / "proj", raw))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        assert (
            api.write_file_text(str(f), "---\r\nphase: BUILD\r\n---\r\n", read["edit_version"])
            is True
        )
        assert f.read_bytes() == b"---\r\nphase: BUILD\r\n---\r\n"

    def test_new_file_defaults_to_utf8_lf(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / ".saipen" / "MANIFEST.md"
        assert api.write_file_text(str(f), "- sub -- x\n") is True
        assert f.read_bytes() == b"- sub -- x\n"


class TestAtomicWriteFailure:
    def test_simulated_replace_failure_leaves_original_byte_identical(
        self, api, tmp_path
    ):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / ".saipen" / "STATE.md"
        seeded = f.read_bytes()  # the conformant seeded bytes (saipen_home added)
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        with patch("pathlib.Path.replace", side_effect=OSError("disk full")):
            assert (
                api.write_file_text(str(f), "---\nphase: BUILD\n---\n", read["edit_version"])
                is False
            )
        # The original bytes survived; the failed commit left a recoverable
        # journal (nothing applied -> recovery aborts it cleanly).
        assert f.read_bytes() == seeded
        from saipenview.protocol_write import get_coordinator

        rec = get_coordinator().recover(root)
        assert rec.get("ok") is True, rec
        assert f.read_bytes() == seeded

    def test_no_temp_debris_after_failed_write(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        with patch("pathlib.Path.replace", side_effect=OSError("disk full")):
            api.write_file_text(str(f), "x\n", read["edit_version"])
        # The original file was never replaced.
        assert "phase: DONE" in f.read_text(encoding="utf-8")


class TestSymlinkEscape:
    @pytest.mark.skipif(
        os.name == "nt" and not hasattr(os, "symlink"),
        reason="no symlink privilege on this Windows host",
    )
    def test_symlink_escape_rejected(self, api, tmp_path):
        _register(api, _seed_project(tmp_path / "proj"))
        outside = tmp_path / "secret.md"
        outside.write_text("secret\n", encoding="utf-8")
        link = tmp_path / "proj" / ".saipen" / "link.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation failed on this host")
        # canonical() resolves the symlink to its target, which lives outside
        # every verified root, so the boundary must reject it.
        assert api.read_file_text(str(link)) is None
