"""The shipped palettes are complete, and the default one is the shipped look.

An undefined CSS custom property is the quietest bug this codebase has: there
is no error, no warning and no console message -- the property falls back to
its initial value, so the element renders with a transparent background or
black-on-black text and everything else looks fine. Four such tokens had been
live in `style.css` for two releases before anyone noticed (T-158).

So a theme is checked before it is applied, and these tests check that the
check cannot be bypassed by a palette that simply omits something.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from saipenview import themes

REPO = Path(__file__).resolve().parent.parent
CSS = (REPO / "saipenview" / "ui" / "static" / "style.css").read_text(encoding="utf-8")


def _root_block() -> str:
    match = re.search(r":root \{(.*?)\n\}", CSS, re.DOTALL)
    assert match, "style.css has no :root block"
    return match.group(1)


def _declared_in_root() -> dict[str, str]:
    # Comments first: the `:root` block carries long explanations that contain
    # colons and semicolons, and a naive scan reads prose as a declaration.
    block = re.sub(r"/\*.*?\*/", "", _root_block(), flags=re.DOTALL)
    return {name: value.strip()
            for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", block)}


def test_all_sixteen_palettes_load() -> None:
    """Sixteen is not a magic number -- it is the Wintage set, vendored whole.

    A palette that fails validation raises rather than being skipped, so a
    silently shrinking menu cannot happen: this asserts the count so a dropped
    file is a red test rather than a theme that quietly stops existing.
    """
    listed = themes.list_themes()
    assert len(listed) == 16, [t["slug"] for t in listed]
    assert {t["slug"] for t in listed} == {
        "antigravity", "claudecode", "codenomad", "custom", "dracula",
        "fpdefault", "freebuff", "golden", "goldendefault", "goldenvintage",
        "klite", "nord", "oled", "solarized", "vintageclassic", "vintagedark",
    }


@pytest.mark.parametrize("slug", sorted(t["slug"] for t in themes.list_themes()))
def test_every_palette_defines_every_token(slug: str) -> None:
    tokens = themes.load_theme(slug)
    assert tokens is not None
    missing = themes.REQUIRED_TOKENS - set(tokens)
    assert not missing, f"{slug} would render {sorted(missing)} as the initial value"


@pytest.mark.parametrize("slug", sorted(t["slug"] for t in themes.list_themes()))
def test_every_value_is_a_colour(slug: str) -> None:
    """A malformed value is worse than a missing one.

    The browser discards a declaration it cannot parse and the property keeps
    whatever it had, so half the theme applies and half of it does not -- which
    looks like a rendering glitch rather than a bad palette file.
    """
    tokens = themes.load_theme(slug) or {}
    bad = {k: v for k, v in tokens.items() if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v)}
    assert not bad, bad


def test_the_stylesheet_fallback_names_every_token_a_theme_sets() -> None:
    """`:root` is what renders when `assets/themes/` cannot be read.

    If a theme sets a property the stylesheet never declares, that property has
    no fallback at all and the no-themes path renders it as the initial value.
    """
    declared = set(_declared_in_root())
    assert themes.REQUIRED_TOKENS <= declared, sorted(themes.REQUIRED_TOKENS - declared)


def test_the_default_theme_is_byte_for_byte_the_shipped_look() -> None:
    """Selecting the default must not change a single colour.

    This is the property that makes the whole feature safe to ship: the app
    with themes and the app without them are the same app until the user picks
    something else.
    """
    declared = _declared_in_root()
    tokens = themes.load_theme(themes.DEFAULT_THEME)
    assert tokens is not None
    drift = {name: (declared[name], tokens[name])
             for name in themes.REQUIRED_TOKENS
             if declared[name].upper() != tokens[name].upper()}
    assert not drift, f"default theme differs from style.css :root: {drift}"


def test_an_unknown_slug_falls_back_instead_of_failing() -> None:
    """Config files get hand-edited and downgrades write slugs we removed.

    Refusing to start over a colour name would be the wrong trade every time.
    """
    slug, tokens = themes.resolve("no-such-theme")
    assert slug == themes.DEFAULT_THEME
    assert tokens


def test_a_partial_palette_is_rejected_not_half_applied(tmp_path: Path) -> None:
    """The control for every test above: prove the validation actually fires."""
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({
        "slug": "broken", "label": "Broken", "order": 1,
        "tokens": {"background": "#000000"},
    }), encoding="utf-8")
    with pytest.raises(themes.ThemeError) as excinfo:
        themes._read(broken)
    assert "missing" in str(excinfo.value)

    malformed = tmp_path / "malformed.json"
    full = {name: "#101010" for name in themes.REQUIRED_TOKENS}
    full["borderHighlight"] = "goldenrod"
    malformed.write_text(json.dumps({
        "slug": "malformed", "label": "Malformed", "order": 1, "tokens": full,
    }), encoding="utf-8")
    with pytest.raises(themes.ThemeError) as excinfo:
        themes._read(malformed)
    assert "borderHighlight" in str(excinfo.value)


def _strip_css_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


@pytest.mark.parametrize("filename", ["style.css", "index.html", "app.js"])
def test_every_var_reference_resolves(filename: str) -> None:
    """No `var(--x)` may name a token nothing declares (T-158).

    This is the audit that found four dead references living in the shipped app
    across two releases: `--bgRaised` (a misremembering of `--surfaceRaised`,
    4 sites), plus `--surfaceBase` and `--text`, which never existed at all.
    None of them produced an error. An undefined custom property with no
    fallback computes to the initial value, so `background: var(--bgRaised)`
    rendered transparent and `color: var(--text)` rendered as the inherited
    colour -- both of which look like a design choice.

    Checked across all three files, not just the stylesheet: two of the three
    dead tokens were in inline styles in `index.html` and `app.js`, which is
    exactly where nobody looks for a colour bug.
    """
    static = REPO / "saipenview" / "ui" / "static"
    declared = set(_declared_in_root()) | {"uiFont"}
    body = _strip_css_comments((static / filename).read_text(encoding="utf-8"))
    used = {}
    for match in re.finditer(r"var\(\s*--([\w-]+)", body):
        used.setdefault(match.group(1), body[: match.start()].count("\n") + 1)
    unknown = {name: line for name, line in used.items() if name not in declared}
    assert not unknown, (
        f"{filename} references tokens nothing declares (they render as the "
        f"initial value, silently): {unknown}"
    )
