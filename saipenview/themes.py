"""Colour palettes, shipped inside the app.

The 16 palettes here came from the Wintage themer, which until now applied them
by REWRITING `saipenview/ui/static/style.css` on disk from a PowerShell script.
That mechanism destroyed the stylesheet twice (T-096, T-142) and neither
accident was visible in review, because the file it produced still parsed and
still looked like itself. Nothing outside this repo needs to edit CSS to change
a colour: a theme is a set of custom-property values, and custom properties can
be set at runtime.

Two rules this module exists to enforce:

- **A theme is data, not a computation.** The files in `assets/themes/` are
  complete and checked in. The ten tokens SAIPENVIEW adds on top of Wintage's
  21 (`surfaceSoft`, `goldStar`, the eight `phase-*` hues) were derived once, by
  a generator, and the result was reviewed. Deriving them at startup would mean
  shipping palettes no one has ever looked at, which is the same failure mode in
  a new costume.
- **A theme is complete or it is rejected.** An undefined custom property does
  not fail loudly -- it falls back to the initial value, so one missing token is
  a transparent background or black-on-black text, with no error anywhere.
  `load_theme` checks the full token set up front and refuses a partial palette
  rather than rendering one.

`style.css`'s own `:root` block stays as the last-resort default, and
`goldendefault` reproduces it token for token, so a machine that cannot read
this directory renders exactly what it rendered before themes existed.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent / "assets" / "themes"

DEFAULT_THEME = "goldendefault"

#: Every custom property `style.css` reads that a theme is responsible for.
#: `--uiFont` is not here: it is a font, set from the `font_family` config key.
REQUIRED_TOKENS = frozenset(
    {
        "background",
        "backgroundSoft",
        "surface",
        "surfaceRaised",
        "surfaceAlt",
        "surfaceSoft",
        "borderDark",
        "borderHighlight",
        "borderMuted",
        "textPrimary",
        "textSecondary",
        "textMuted",
        "accentTeal",
        "accentTealDeep",
        "success",
        "warning",
        "danger",
        "dangerText",
        "selection",
        "compareBack",
        "goldStar",
        "phase-init",
        "phase-plan",
        "phase-scout",
        "phase-hunt",
        "phase-add",
        "phase-clean",
        "phase-translate",
        "phase-validate",
    }
)

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ThemeError(ValueError):
    """A palette on disk is unusable. Never raised for a merely unknown slug."""


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    slug = data.get("slug")
    if not slug:
        raise ThemeError(f"{path.name}: no slug")
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        raise ThemeError(f"{slug}: no tokens object")

    missing = REQUIRED_TOKENS - set(tokens)
    if missing:
        raise ThemeError(f"{slug}: missing {sorted(missing)}")
    # A value that is not a colour is worse than a missing one: the browser
    # discards the declaration and the property silently keeps its old value,
    # so half the theme applies and half of it does not.
    bad = {k: v for k, v in tokens.items() if not _HEX.match(str(v))}
    if bad:
        raise ThemeError(f"{slug}: not #rrggbb: {sorted(bad)}")
    return data


@lru_cache(maxsize=1)
def _all() -> dict[str, dict]:
    if not THEMES_DIR.is_dir():
        return {}
    found: dict[str, dict] = {}
    for path in sorted(THEMES_DIR.glob("*.json")):
        data = _read(path)
        found[data["slug"]] = data
    return found


def list_themes() -> list[dict]:
    """Slug, label and order for every readable palette, in menu order."""
    themes = sorted(_all().values(), key=lambda t: (t.get("order", 999), t["slug"]))
    return [
        {
            "slug": t["slug"],
            "label": t.get("label", t["slug"]),
            "order": t.get("order", 999),
        }
        for t in themes
    ]


def load_theme(slug: str) -> dict[str, str] | None:
    """The token map for `slug`, or None if there is no such theme.

    None rather than an exception: an unknown slug is an ordinary thing to find
    in a config file that a human has edited, or that a downgrade wrote, and the
    right response is to fall back to the stylesheet's own defaults, not to
    refuse to start.
    """
    theme = _all().get(slug)
    return dict(theme["tokens"]) if theme else None


def resolve(slug: str | None) -> tuple[str, dict[str, str]]:
    """The tokens to apply, and the slug they actually came from.

    Returns the requested theme, else the default, else `("", {})` when the
    directory is unreadable -- at which point the caller applies nothing and
    `style.css` renders its own `:root`, which is the shipped look.
    """
    for candidate in (slug, DEFAULT_THEME):
        if not candidate:
            continue
        tokens = load_theme(candidate)
        if tokens is not None:
            return candidate, tokens
    return "", {}
