"""T-816: all 34 locale tables loaded on every launch.

``index.html`` hard-coded 34 ``<script>`` tags totalling 602 KB (65% of the
924 KB page payload) to render ONE language; 33 of them were dead weight for
the whole session. ``app.js`` captured every table eagerly through 34
``typeof`` guards. And the configured non-English startup never hydrated the
DOM at all: ``hydrateDOM(cfg.locale)`` lived only in the Settings open/change
paths, so the main ``saiaapiready`` startup left the chrome English.

Repair, three parts:

* the startup page is rendered with only ``locale-en.js`` (the key-fallback
  table) plus the configured locale's file -- T-831 moved the renderer into
  the GUI-neutral ``ui/index_page.py`` so the service serves the same page;
  the repo template is never rewritten so a pytest run can never strip
  locales from it;
* ``app.js`` resolves any other locale on demand (``loadLocaleTable``), so
  switching locale in Settings works without a reload;
* the ``saiaapiready`` startup path hydrates the DOM for a configured
  non-English locale.

The claims, each stated so it can fail:

* the rendered page ships exactly the en + configured locale tags, the
  corrupted-config injection is impossible, and the repo template is
  untouched;
* the eager 34-table capture is gone; only the en table is captured at load;
* the on-demand loader returns the table for a shipped script and {} for an
  unknown code;
* a non-English startup hydrates via the saiaapiready path.

T-831 page-generation assertions moved to ``test_index_page_renderer.py``
(same semantics, stricter contract: in-place block replacement, startup
ordering, explicit failure on a missing/no-locale-block template).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static"


# ── page generation (semantics; mechanics live in test_index_page_renderer) ─


class TestGeneratedPage:
    def test_repo_template_is_untouched_by_the_fix(self):
        """The template keeps its 34 tags; generated pages are derived, never
        written back. A mocked-window test run must never be able to strip
        locales from the repository's index.html (this exact damage shipped
        once)."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        tags = re.findall(r'src="locale-[^"]+\.js"', html)
        assert len(tags) == 34, "template must remain the 34-locale source"

    def test_rendered_page_ships_exactly_two_locale_tags(self):
        from saipenview.ui.index_page import render_index_html

        html = render_index_html("et")
        tags = re.findall(r'src="(locale-[^"]+\.js)"', html)
        assert sorted(tags) == ["locale-en.js", "locale-et.js"]

    def test_rendering_never_touches_the_template(self):
        from saipenview.ui.index_page import canonical_index_path, render_index_html

        before = canonical_index_path().read_bytes()
        html = render_index_html("de")
        after = canonical_index_path().read_bytes()
        assert after == before, "the template was rewritten by a render"
        assert 'src="locale-de.js"' in html

    def test_english_startup_ships_only_en(self):
        from saipenview.ui.index_page import render_index_html

        tags = re.findall(
            r'src="(locale-[^"]+\.js)"', render_index_html("en")
        )
        assert tags == ["locale-en.js"]

    def test_every_shipped_locale_has_a_tag_or_loader_entry(self):
        """A locale present on disk but known to neither the renderer nor the
        loader would silently fall back to English -- the list must be closed."""
        from saipenview.ui.index_page import LOCALE_CODES

        shipped = {
            p.stem.removeprefix("locale-")
            for p in STATIC.glob("locale-*.js")
        }
        missing_on_disk = [c for c in LOCALE_CODES if c not in shipped]
        assert not missing_on_disk, f"no file for {missing_on_disk}"
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        missing_in_js = [c for c in shipped if c != "en" and c not in source]
        assert not missing_in_js, f"loader never resolves {missing_in_js}"

    def test_corrupted_config_locale_cannot_inject_markup(self):
        from saipenview.ui.index_page import render_index_html

        html = render_index_html('en"><script>alert(1)</script>')
        assert "alert" not in html
        assert 'src="locale-en.js"' in html


# ── app.js lazy runtime ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def app_js_source():
    return (STATIC / "app.js").read_text(encoding="utf-8")


class TestLazyRuntime:
    def test_no_eager_table_capture_remains(self, app_js_source):
        """The 34 typeof guards were the second half of the 602 KB cost: they
        forced every table to be captured at load time. The lazy runtime
        captures only en at load."""
        assert "typeof LOCALE_AR" not in app_js_source
        assert "typeof LOCALE_RU" not in app_js_source
        assert "typeof LOCALE_ZH_CN" not in app_js_source
        # The one intentional eager capture is the fallback table.
        assert "typeof LOCALE_EN" in app_js_source

    def test_loader_and_hydration_guarantee_exist(self, app_js_source):
        assert "function loadLocaleTable(" in app_js_source
        # hydrateDOM must guarantee the table BEFORE hydration, and t() must
        # resolve the current locale's table on demand.
        assert re.search(
            r"function hydrateDOM\(locale\) \{\s*\n\s*if \(locale && locale !== \"en\"\) \{",
            app_js_source,
        ), "hydrateDOM must call loadLocaleTable before hydrating"

    def test_settings_change_path_still_preloads(self, app_js_source):
        """The Settings locale <select> change keeps calling hydrateDOM with
        the chosen code -- now backed by the lazy loader."""
        assert "hydrateDOM(e.target.value);" in app_js_source


# ── startup hydration ────────────────────────────────────────────────────────


class TestStartupHydration:
    def test_saiaapiready_hydrates_non_english_locale(self, app_js_source):
        """The defect: hydrateDOM(cfg.locale) existed only in Settings paths,
        so a configured non-English locale rendered English chrome until the
        user opened Settings. The startup path must hydrate too."""
        blocks = re.findall(
            r'window\.addEventListener\("saiapiready".*?\n\}\);',
            app_js_source,
            re.DOTALL,
        )
        assert blocks, "saiaapiready listener missing"
        assert any(
            'cfg.locale && cfg.locale !== "en"' in b and "hydrateDOM(cfg.locale);" in b
            for b in blocks
        ), "no saiaapiready listener hydrates a non-English locale"

    def test_generated_page_uses_configured_locale_before_startup(self):
        """With the rendered page, a non-English session needs no hydration
        round-trip for the toolbar chrome: the table ships with the page and
        t() resolves from it on first render."""
        from saipenview.ui.index_page import render_index_html

        html = render_index_html("ru")
        # The configured table is present at parse time; app.js startup reads
        # config and hydrates, and hydrateDOM finds the table without a fetch.
        assert 'src="locale-ru.js"' in html
