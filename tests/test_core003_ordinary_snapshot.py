"""CORE-003: an ordinary-file read snapshot is assembled from ONE byte read.

`read_file_text` used to perform two independent filesystem observations:

    raw = path.read_bytes()
    text = read_doc(path)          # reopens and re-reads the path

so an external write between them could return revision B's text carrying
revision A's CAS token. These tests pin the single-buffer contract and prove
the split-read race is impossible.
"""

from __future__ import annotations

import codecs
import hashlib
from unittest.mock import MagicMock, patch

import pytest

import saipenview.api as api_mod
from saipenview.config import DEFAULTS


def _viewer_cfg(roots):
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = list(roots)
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    return cfg


@pytest.fixture
def viewer_api(tmp_path):
    proj_dir = tmp_path / "p"
    (proj_dir / ".saipen").mkdir(parents=True, exist_ok=True)
    (proj_dir / ".saipen" / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\n---\n", encoding="utf-8"
    )
    with (
        patch.object(api_mod, "config_path", lambda: tmp_path / "config.json"),
        patch.object(api_mod, "load_config", return_value=_viewer_cfg([str(proj_dir)])),
        patch.object(api_mod, "save_config"),
        patch.object(api_mod, "BackgroundScanner", MagicMock()),
        patch.object(api_mod, "SaipenWatcher", MagicMock()),
    ):
        instance = api_mod.Api()
        try:
            yield instance, proj_dir
        finally:
            instance.stop()


def test_single_read_builds_text_and_token(viewer_api):
    """One underlying read is sufficient to construct text + edit_version."""
    api, root = viewer_api
    f = root / "notes.md"
    f.write_bytes(b"hello\n")

    reads = {"n": 0}
    real_read_bytes = type(f).read_bytes

    def spy(self, *a, **k):
        if self == f:
            reads["n"] += 1
        return real_read_bytes(self, *a, **k)

    with patch.object(type(f), "read_bytes", spy):
        snap = api.read_file_text(str(f))

    assert snap is not None
    assert snap["text"] == "hello\n"
    # edit_version is the hash of the EXACT raw bytes read (not of the
    # newline-normalized text).
    assert snap["edit_version"] == hashlib.sha256(b"hello\n").hexdigest()[:16]
    assert reads["n"] == 1, f"ordinary read performed {reads['n']} file reads"


def test_split_read_race_impossible(viewer_api):
    """The v1->v2 interleaving: it must be impossible to return v2 text with
    v1's token. With a single buffer the returned text and token always
    describe the same raw bytes.
    """
    api, root = viewer_api
    f = root / "notes.md"
    f.write_bytes(b"v1\n")

    from pathlib import Path

    calls = {"n": 0}
    captured: dict = {}
    real_read_bytes = Path.read_bytes

    def racy_read_bytes(self, *a, **k):
        data = real_read_bytes(self, *a, **k)
        if self == f:
            calls["n"] += 1
            if calls["n"] == 1:
                captured["raw"] = data
                # An external write landing AFTER the first read returned its
                # bytes: on the pre-fix code the second read sees "v2\n".
                Path(f).write_bytes(b"v2\n")
        return data

    with patch.object(Path, "read_bytes", racy_read_bytes):
        snap = api.read_file_text(str(f))

    assert snap is not None
    # The single read saw one revision; text and token must both describe it.
    raw = captured["raw"]
    assert snap["edit_version"] == hashlib.sha256(raw).hexdigest()[:16], snap
    assert snap["text"] == raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def test_utf8_bom_preserved(viewer_api):
    api, root = viewer_api
    f = root / "bom.md"
    raw = codecs.BOM_UTF8 + b"bom body\n"
    f.write_bytes(raw)
    snap = api.read_file_text(str(f))
    assert snap is not None
    assert snap["text"] == "bom body\n"
    assert snap["edit_version"] == hashlib.sha256(raw).hexdigest()[:16]


def test_utf16_bom_preserved(viewer_api):
    api, root = viewer_api
    f = root / "u16.md"
    raw = "utf16 body\n".encode("utf-16")  # emits a BOM
    f.write_bytes(raw)
    snap = api.read_file_text(str(f))
    assert snap is not None
    assert snap["text"] == "utf16 body\n"
    assert snap["edit_version"] == hashlib.sha256(raw).hexdigest()[:16]


def test_cp1251_preserved(viewer_api):
    api, root = viewer_api
    f = root / "ru.md"
    raw = "привет\n".encode("cp1251")
    f.write_bytes(raw)
    snap = api.read_file_text(str(f))
    assert snap is not None
    assert snap["text"] == "привет\n"
    assert snap["edit_version"] == hashlib.sha256(raw).hexdigest()[:16]


def test_newline_normalization_preserved(viewer_api):
    api, root = viewer_api
    f = root / "crlf.md"
    raw = b"a\r\nb\r\n"
    f.write_bytes(raw)
    snap = api.read_file_text(str(f))
    assert snap is not None
    assert snap["text"] == "a\nb\n"
    # Token is the hash of the RAW bytes (with CRLF), not the normalized text.
    assert snap["edit_version"] == hashlib.sha256(raw).hexdigest()[:16]
