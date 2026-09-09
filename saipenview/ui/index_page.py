"""T-831: the ONE owner of locale-aware startup HTML.

Every defect this module closes comes from split ownership of the startup
document: the desktop generated ``index.lite.html`` in ``ui/window.py`` while
the service served the raw 34-locale template, the renderer fabricated a blank
``<body></body>`` page when the template could not be read, a failed generated
write still selected the intended filename, generated pages drifted to a
different script order than the canonical template, and the generated file was
eligible to leak into release inputs.

The contract here is pure: read the canonical template, locate its locale
script block, replace that block IN PLACE with ``locale-en.js`` plus the
configured non-English locale (when it belongs to the closed known set), and
return the page. No ``webview``, no ``MainWindow``, no ``Api``, no service, no
Windows APIs -- only stdlib. Delivery surfaces (desktop window hosting, the
headless HTTP service, the optional generated-file writer) consume it; none of
them duplicate the locale logic.

Startup ordering is part of the contract: locale scripts stay where the
canonical template puts them -- BEFORE ``sai-api.js``, ``transport-boot.js``
and ``app.js`` -- so startup never depends on the app's later recovery logic
merely to survive the generated page.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# The closed known-locale set. Must name every shipped locale file: validated
# by tests (every code has a locale-<code>.js; every shipped file has a code),
# so an unknown-but-shipped locale can never silently fall back to English.
LOCALE_CODES: tuple[str, ...] = (
    "ar", "bg", "cs", "da", "de", "ded", "el", "es", "et", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "nl", "no", "pl",
    "pt", "ro", "ru", "sk", "sv", "th", "tr", "uk", "vi", "zh", "zh-CN",
)

_STATIC_DIR = Path(__file__).parent / "static"
INDEX_NAME = "index.html"
INDEX_LITE_NAME = "index.lite.html"

# One locale script tag exactly as the canonical template writes it.
_LOCALE_TAG_RE = re.compile(r'<script src="locale-[^"]+\.js"></script>')


class IndexPageError(RuntimeError):
    """The canonical startup template is missing, unreadable, or does not
    carry the expected locale block. A missing template must produce a REAL
    failure, never a fabricated successful page."""


def static_dir() -> Path:
    """The directory holding the canonical template (and generated pages)."""
    return _STATIC_DIR


def canonical_index_path() -> Path:
    return _STATIC_DIR / INDEX_NAME


def generated_index_path() -> Path:
    return _STATIC_DIR / INDEX_LITE_NAME


def _locate_locale_block(html: str) -> tuple[int, int]:
    """The [start, end) span of the template's locale-script block.

    The template's contract: every locale tag sits in ONE contiguous run,
    only whitespace between tags. Anything else (scattered tags, interleaved
    markup) is a structurally different template and must be refused rather
    than half-rendered -- a partial replacement would leave most of the 34
    locales in the page and look like success.
    """
    tags = list(_LOCALE_TAG_RE.finditer(html))
    if not tags:
        raise IndexPageError(
            "canonical startup template carries no locale script block -- "
            "refusing to render a structurally different page"
        )
    for prev, nxt in zip(tags, tags[1:]):
        if html[prev.end() : nxt.start()].strip():
            raise IndexPageError(
                "locale script tags are not a single contiguous block -- "
                "refusing to render a structurally different page"
            )
    return tags[0].start(), tags[-1].end()


def locale_script_tag(locale: str) -> str:
    """One ``<script>`` tag for *locale*, or '' when it is not a known code.

    Emission happens only after an exact closed-set membership check, so a
    corrupted config value can never inject markup into the page."""
    if locale in LOCALE_CODES:
        return f'<script src="locale-{locale}.js"></script>'
    return ""


def _read_canonical_template() -> str:
    """The canonical template's text, or a clear failure.

    A missing/unreadable template is a renderer error -- it must never be
    papered over with a fabricated page that looks like success."""
    path = canonical_index_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise IndexPageError(
            f"cannot read the canonical startup template {path.name}: {e}"
        ) from e


def render_index_html(locale: str) -> str:
    """The effective startup document: canonical template with exactly one
    locale block -- ``locale-en.js`` plus the configured non-English locale
    when (and only when) it belongs to the closed known set.

    * unknown or injection-looking locale -> EN only (no interpolation of
      unchecked config text into HTML, ever);
    * the canonical template is never modified;
    * every non-locale byte of the template is preserved;
    * locale tags stay in the template's position, before sai-api.js /
      transport-boot.js / app.js;
    * a template without the expected locale block raises ``IndexPageError``
      rather than silently producing a structurally different page.
    """
    html = _read_canonical_template()
    start, end = _locate_locale_block(html)

    tags = ['<script src="locale-en.js"></script>']
    configured = locale_script_tag(locale)
    if configured:
        tags.append(configured)
    replacement = "\r\n".join(tags)

    # Replace the block IN PLACE: all bytes before and after it are kept
    # verbatim, so the canonical startup ordering is preserved by
    # construction instead of relying on re-insertion near </body>.
    return html[:start] + replacement + html[end:]


def write_index_lite(html: str, target_dir: Path | None = None) -> Path:
    """Atomically write the generated page beside the canonical template.

    Render -> write to a temporary sibling -> ``os.replace`` onto
    ``index.lite.html``. Only a successful replace makes the generated file
    eligible for startup; a failure here leaves the intended name untouched
    (so a stale generated page can never be mistaken for a fresh one) and
    cleans up its temporary residue. The canonical template is never written.
    """
    target = (target_dir or _STATIC_DIR) / INDEX_LITE_NAME
    tmp = target.with_name(f".{INDEX_LITE_NAME}.tmp-{os.getpid()}")
    try:
        tmp.write_bytes(html.encode("utf-8"))
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target
