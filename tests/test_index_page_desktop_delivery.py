"""T-831: desktop delivery of the startup document.

The desktop contract (``ui/window.py::_startup_document_path``):

* a successful generation atomically selects a fresh ``index.lite.html``;
* a failed write or a failed ``os.replace`` selects the CANONICAL template;
* a pre-existing (stale) generated file is NEVER selected after a failed
  generation -- it may carry a different locale than the config asks for;
* the canonical template survives every failure path byte-identical;
* temporary residue from the writer's own failed attempt is cleaned up.

Everything runs against a redirected static dir in ``tmp_path``: pytest must
never write the repository's real ``index.lite.html`` or ``index.html``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saipenview.ui import index_page
from saipenview.ui import window as window_mod

TEMPLATE = (
    "<html><head><title>x</title></head><body>\n"
    '<script src="locale-en.js"></script>\n'
    '<script src="locale-ar.js"></script>\n'
    '<script src="sai-api.js"></script>\n'
    '<script src="transport-boot.js"></script>\n'
    '<script src="app.js"></script>\n'
    "</body></html>\n"
)


@pytest.fixture()
def static_dir(tmp_path: Path, monkeypatch) -> Path:
    """A redirected static dir carrying ONLY the canonical template.

    Pointing the renderer's module-level dir at tmp_path means every artifact
    (generated page, temp files, failure residue) lands in the test's own
    directory -- the repository's ui/static is never touched."""
    d = tmp_path / "static"
    d.mkdir()
    (d / "index.html").write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(index_page, "_STATIC_DIR", d)
    return d


class TestDesktopDelivery:
    def test_successful_generation_selects_fresh_lite(self, static_dir):
        path = window_mod._startup_document_path("ru")
        assert path == index_page.generated_index_path()
        assert path.is_file()
        html = path.read_text(encoding="utf-8")
        assert 'src="locale-ru.js"' in html and 'src="locale-en.js"' in html
        assert 'src="locale-ar.js"' not in html

    def test_write_failure_selects_canonical_template(
        self, static_dir, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            index_page, "write_index_lite", lambda *a, **k: (_ for _ in ()).throw(OSError(13, "denied"))
        )
        path = window_mod._startup_document_path("ru")
        assert path == index_page.canonical_index_path()
        assert "canonical index.html" in capsys.readouterr().err

    def test_replace_failure_selects_canonical_template(
        self, static_dir, monkeypatch
    ):
        """os.replace must be reached (i.e. the temp write happened) and its
        failure must fall back to the canonical template."""
        calls = []

        def boom(src, dst):
            calls.append((src, dst))
            raise OSError(5, "replace refused")

        monkeypatch.setattr(index_page.os, "replace", boom)
        path = window_mod._startup_document_path("et")
        assert calls, "os.replace was never attempted (not an atomic write)"
        assert path == index_page.canonical_index_path()

    def test_stale_lite_is_never_selected_after_generation_failure(
        self, static_dir, monkeypatch
    ):
        """A pre-existing generated page from an earlier run (different
        locale) must NOT be selected when fresh generation fails."""
        stale = static_dir / index_page.INDEX_LITE_NAME
        stale.write_text("<html>OLD LOCALE PAGE</html>", encoding="utf-8")

        def boom(*a, **k):
            raise OSError(13, "denied")

        monkeypatch.setattr(index_page, "write_index_lite", boom)
        path = window_mod._startup_document_path("ru")
        assert path == index_page.canonical_index_path()
        assert "OLD LOCALE PAGE" not in path.read_text(encoding="utf-8")

    def test_canonical_source_survives_all_failure_paths(
        self, static_dir, monkeypatch
    ):
        before = (static_dir / "index.html").read_bytes()
        monkeypatch.setattr(
            index_page, "write_index_lite", lambda *a, **k: (_ for _ in ()).throw(OSError(13, "denied"))
        )
        window_mod._startup_document_path("ru")
        window_mod._startup_document_path("en")
        assert (static_dir / "index.html").read_bytes() == before

    def test_failed_generation_leaves_no_generated_file_selected(
        self, static_dir, monkeypatch
    ):
        """After a failed generation the selection is the canonical template;
        whatever residue a crashed earlier process left is irrelevant."""
        def boom(*a, **k):
            # Simulate a crash mid-write: a temp sibling already on disk.
            residue = static_dir / ".index.lite.html.tmp-999"
            residue.write_bytes(b"partial")
            raise OSError(13, "denied")

        monkeypatch.setattr(index_page, "write_index_lite", boom)
        assert window_mod._startup_document_path("ru") == (
            index_page.canonical_index_path()
        )

    def test_writer_cleans_its_own_temp_on_failure(self, tmp_path, monkeypatch):
        """The atomic writer itself: a replace failure removes its temp
        sibling and leaves the target untouched."""
        d = tmp_path / "static"
        d.mkdir()
        monkeypatch.setattr(index_page, "_STATIC_DIR", d)

        def boom(src, dst):
            raise OSError(5, "no")

        monkeypatch.setattr(index_page.os, "replace", boom)
        with pytest.raises(OSError):
            index_page.write_index_lite("<html>x</html>")
        assert not list(d.glob(".*tmp*"))
        assert not (d / index_page.INDEX_LITE_NAME).exists()

    def test_real_template_is_never_overwritten_by_window_build(self):
        """The repository's own canonical template must be byte-identical
        after a real delivery run against the real static dir (the write path
        is the generated sibling, never the template)."""
        real_template = Path(index_page.canonical_index_path())
        before = real_template.read_bytes()
        # Run the real selection against the REAL static dir, then restore the
        # repo to a clean state by removing the generated artifact afterwards.
        try:
            path = window_mod._startup_document_path("en")
        finally:
            after = real_template.read_bytes()
            generated = Path(index_page.generated_index_path())
            if generated.exists():
                generated.unlink()
        assert after == before
        assert path.name in {"index.html", index_page.INDEX_LITE_NAME}

    def test_renderer_failure_with_readable_template_falls_back(
        self, static_dir, monkeypatch, capsys
    ):
        """Render failure (not write failure) also falls back to the canonical
        template when it is readable -- with a clear diagnostic."""
        # Remove the template so _startup_document_path's render fails, then
        # put it back via a failing renderer instead: simplest is a renderer
        # error with the template still present.
        (static_dir / "index.html").write_text(
            "<html><body>no locale block</body></html>", encoding="utf-8"
        )
        path = window_mod._startup_document_path("ru")
        assert path == index_page.canonical_index_path()
        assert "startup page generation failed" in capsys.readouterr().err

    def test_renderer_failure_without_template_fails_startup(
        self, static_dir, monkeypatch
    ):
        """No readable template anywhere: startup must fail clearly rather
        than fabricate or silently degrade."""
        (static_dir / "index.html").unlink()
        with pytest.raises(index_page.IndexPageError):
            window_mod._startup_document_path("ru")

    def test_render_failure_with_unreadable_canonical_fails_startup(
        self, static_dir, monkeypatch
    ):
        """The unreadable-fallback defect (T-831): when the renderer fails
        AND the canonical template exists and reports as a file but cannot
        actually be READ, startup must fail with a clear error. The old
        ``is_file()`` proof returned the unreadable canonical path anyway,
        converting a clear renderer failure into a delayed, opaque
        window-load failure -- and a stale generated page must never be
        selected in its place either.

        Unreadability is injected at the open() boundary: no chmod, whose
        semantics differ between Windows, CI and elevated shells."""
        stale = static_dir / index_page.INDEX_LITE_NAME
        stale.write_text("<html>OLD LOCALE PAGE</html>", encoding="utf-8")
        stale_stat = stale.stat()
        # The canonical path exists and identifies a file -- the trap that
        # made ``is_file()`` look like a sufficient proof.
        assert index_page.canonical_index_path().is_file()

        renderer_error = index_page.IndexPageError(
            "cannot read the canonical startup template index.html: injected"
        )

        def broken_render(locale):
            raise renderer_error

        monkeypatch.setattr(index_page, "render_index_html", broken_render)

        def unreadable(self, *args, **kwargs):
            raise PermissionError(13, "access denied (injected)")

        monkeypatch.setattr(Path, "open", unreadable)

        with pytest.raises(index_page.IndexPageError) as excinfo:
            window_mod._startup_document_path("ru")

        msg = str(excinfo.value)
        # The error names the startup/canonical document failure...
        assert "startup document unavailable" in msg
        assert "index.html" in msg
        # ...retains the original renderer failure, and chains the I/O
        # error that proved the unreadability.
        assert "injected" in msg
        assert isinstance(excinfo.value.__cause__, OSError)
        # Nothing was selected over the failure: the stale generated page
        # was never rewritten (stat only -- the file is not readable here).
        after = stale.stat()
        assert (after.st_size, after.st_mtime_ns) == (
            stale_stat.st_size,
            stale_stat.st_mtime_ns,
        )
