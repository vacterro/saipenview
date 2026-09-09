"""T-831: the pure startup-document renderer and its delivery contracts.

The renderer (``saipenview/ui/index_page.py``) is the ONE owner of locale-aware
startup HTML. The original T-816 wave put rendering inside ``ui/window.py``,
which the headless service cannot import (it would drag in ``webview`` and the
Windows window stack) -- so the service kept serving the raw 34-locale
template. These tests pin the renderer contract itself; the T-816 semantics
(lazy runtime, hydration, closed vocabulary) stay in
``test_t816_lazy_locales.py`` and ``test_t816_locale_capture.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from saipenview.ui import index_page
from saipenview.ui.index_page import (
    LOCALE_CODES,
    IndexPageError,
    canonical_index_path,
    generated_index_path,
    render_index_html,
)

STATIC = Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static"

# The canonical template's tail order, extracted once for the ordering claims.
_TEMPLATE_TAIL = {
    m.group(1)
    for m in re.finditer(
        r'<script src="((?:sai-api|transport-boot|app)\.js)"></script>',
        (STATIC / "index.html").read_text(encoding="utf-8"),
    )
}
assert _TEMPLATE_TAIL == {"sai-api.js", "transport-boot.js", "app.js"}


class TestPureRenderer:
    def test_en_is_exactly_one_locale_tag(self):
        tags = re.findall(r'src="(locale-[^"]+\.js)"', render_index_html("en"))
        assert tags == ["locale-en.js"]

    def test_ru_is_exactly_en_plus_ru(self):
        tags = re.findall(r'src="(locale-[^"]+\.js)"', render_index_html("ru"))
        assert tags == ["locale-en.js", "locale-ru.js"]

    def test_unknown_locale_is_en_only(self):
        tags = re.findall(
            r'src="(locale-[^"]+\.js)"', render_index_html("klingon")
        )
        assert tags == ["locale-en.js"]

    def test_injection_looking_locale_is_en_only(self):
        html = render_index_html('en"><script>alert(1)</script>')
        assert "alert" not in html
        assert "<script src=" in html  # the page still carries its real scripts
        tags = re.findall(r'src="(locale-[^"]+\.js)"', html)
        assert tags == ["locale-en.js"]

    def test_canonical_index_html_is_unchanged(self, tmp_path):
        before = canonical_index_path().read_bytes()
        for loc in ("en", "ru", 'x"><b>'):
            render_index_html(loc)
        assert canonical_index_path().read_bytes() == before

    def test_locale_tags_precede_the_app_scripts(self):
        """Startup ordering is part of the contract: the locale block must sit
        BEFORE sai-api.js / transport-boot.js / app.js, exactly where the
        canonical template has it -- the generated page must not depend on
        app.js's later recovery logic merely to survive."""
        html = render_index_html("ru")
        positions = {
            name: html.find(f'src="{name}"')
            for name in ("sai-api.js", "transport-boot.js", "app.js")
        }
        assert all(p >= 0 for p in positions.values())
        for tag_pos in (html.find('src="locale-en.js"'), html.find('src="locale-ru.js"')):
            for name, p in positions.items():
                assert tag_pos < p, f"locale tag must precede {name}"

    def test_every_non_locale_byte_of_the_template_is_preserved(self):
        """Strip locale tags from both template and render; what remains must
        be byte-identical (in-place block replacement, nothing else moves)."""
        template = (STATIC / "index.html").read_text(encoding="utf-8")
        rendered = render_index_html("et")
        strip = lambda s: re.sub(  # noqa: E731
            r'[ \t]*<script src="locale-[^"]+\.js"></script>[ \t]*\r?\n?', "", s
        )
        assert strip(rendered) == strip(template)

    def test_missing_template_is_an_explicit_renderer_error(self, tmp_path, monkeypatch):
        """A missing template must fail LOUDLY -- never fabricate a page that
        looks like success (the old ``<body></body>`` fallback)."""
        monkeypatch.setattr(index_page, "_STATIC_DIR", tmp_path)
        with pytest.raises(IndexPageError):
            render_index_html("en")

    def test_template_without_locale_block_is_an_error(self, tmp_path, monkeypatch):
        """A structurally different template must be refused, not silently
        rendered with tags bolted on somewhere else."""
        (tmp_path / "index.html").write_text(
            "<html><body><p>no locales here</p></body></html>", encoding="utf-8"
        )
        monkeypatch.setattr(index_page, "_STATIC_DIR", tmp_path)
        with pytest.raises(IndexPageError):
            render_index_html("ru")

    def test_every_known_locale_code_has_a_shipped_file(self):
        shipped = {p.stem.removeprefix("locale-") for p in STATIC.glob("locale-*.js")}
        missing = [c for c in LOCALE_CODES if c not in shipped]
        assert not missing, f"LOCALE_CODES names a file that does not ship: {missing}"

    def test_renderer_writes_no_filesystem_state(self, tmp_path, monkeypatch):
        """Purity: rendering must not create or modify anything on disk. Run
        it with the static dir pointed at an empty temp dir with a template
        that renders fine, and assert the dir stays untouched."""
        template = (STATIC / "index.html").read_text(encoding="utf-8")
        d = tmp_path / "static"
        d.mkdir()
        (d / "index.html").write_text(template, encoding="utf-8")
        before = sorted(str(p) for p in d.rglob("*"))
        monkeypatch.setattr(index_page, "_STATIC_DIR", d)
        for loc in ("en", "ru", "klingon"):
            render_index_html(loc)
        after = sorted(str(p) for p in d.rglob("*"))
        assert after == before


class TestAtomicGeneratedWriter:
    """The optional generated-file writer: temp sibling + os.replace."""

    def test_successful_write_lands_at_the_generated_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(index_page, "_STATIC_DIR", tmp_path)
        html = "<html>fresh</html>"
        target = index_page.write_index_lite(html)
        assert target == tmp_path / index_page.INDEX_LITE_NAME
        assert target.read_text(encoding="utf-8") == html
        assert not list(tmp_path.glob(".*tmp*")), "temp residue left behind"

    def test_never_writes_the_canonical_template(self, tmp_path, monkeypatch):
        monkeypatch.setattr(index_page, "_STATIC_DIR", tmp_path)
        (tmp_path / "index.html").write_text("canonical", encoding="utf-8")
        index_page.write_index_lite("<html>fresh</html>")
        assert (tmp_path / "index.html").read_text(encoding="utf-8") == "canonical"


class TestModuleIsolation:
    def test_renderer_module_imports_no_gui_or_service_stack(self):
        """The renderer must stay importable from the headless service: no
        webview, no MainWindow/Api, no service module, no Windows window APIs."""
        import subprocess
        import sys

        code = (
            "import sys; import saipenview.ui.index_page as ip; "
            "print(','.join(sorted(m for m in sys.modules if m in {"
            "'webview', 'saipenview.ui.window', 'saipenview.service'})))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "", (
            f"renderer pulled in GUI/service modules: {proc.stdout}"
        )
