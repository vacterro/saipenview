"""Engine-verified check of the T-816 audit fix (IMP-001 capture path).

Audit RUN-1 of cycle imp-vacterro-saipenview-20260908-1 proved -- with a V8
repro, not a string grep -- that ``loadLocaleTable``'s ``window[globalName]``
probe can never see the locale tables: every ``locale-*.js`` declares its
table with a top-level ``const``, and a classic script's top-level ``const``
is a global LEXICAL binding, never a property of the global object. The old
string-presence tests passed while every non-English locale rendered English.

These tests execute the actual ``app.js`` i18n runtime in Node's V8 (the same
engine family as the app's WebView2) with the SAME sequence the shipped page
produces: the loader block first, then a classic script whose top-level
``const LOCALE_X = {...}`` (the locale file), then the loader call. They fail
against the pre-fix loader and pass after it -- the red/green pair the
original T-816 wave lacked.

jsdom is not a project dependency; the DOM-dependent branches (dynamic
script append, re-hydration) are exercised through a stub and kept out of
the capture assertions.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static"
APP_JS = STATIC / "app.js"

NODE = shutil.which("node")


def _run_i18n_block(extra_locale_script: str, loader_calls: str) -> dict:
    """Extract app.js's i18n block, run it in V8 with a locale script, and
    return the JSON console output. Raises with the engine's stderr on a
    thrown error so a broken runtime cannot silently pass."""
    app = APP_JS.read_text(encoding="utf-8")
    start = app.index("let currentLocale")
    hydrate = app.index("function hydrateDOM(locale)")
    # The i18n block ends where hydrateDOM's querySelectorAll loops end; take
    # everything up to the next top-level function AFTER hydrateDOM's body.
    nxt = app.find("\nfunction ", hydrate + 10)
    block = app[start:nxt]
    stub = (
        "const document = { querySelectorAll: () => [] };\n"
        "const window = globalThis;\n"
    )
    script = (
        "const __out = [];\n"
        "const __emit = (x) => __out.push(x);\n"
        + stub
        + block
        + "\n"
        + extra_locale_script
        + "\n"
        + loader_calls
        + "\n__emit(JSON.stringify({ out: __out }));\n"
        "console.log(__out[__out.length - 1]);\n"
    )
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        pytest.fail(f"i18n runtime threw in V8:\n{proc.stderr}")
    match = re.search(r"\{.*\}", proc.stdout, re.DOTALL)
    if not match:
        pytest.fail(f"no JSON output from V8 run:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(match.group(0))


@pytest.mark.skipif(NODE is None, reason="node not available")
class TestLocaleCaptureEngineVerified:
    def test_capture_after_const_locale_script(self):
        """IMP-001: the loader must capture a table declared with top-level
        `const` by a classic script that ran BEFORE the loader call -- the
        generated page's exact order (app.js first, locale tags after).
        Pre-fix this returned {} because only window[globalName] was probed."""
        result = _run_i18n_block(
            'const LOCALE_ET = { hello: "tere" };',
            (
                'const table = loadLocaleTable("et");\n'
                '__emit(JSON.stringify({ captured: table && table.hello === "tere" }));\n'
            ),
        )
        assert result["out"][-1] == '{"captured":true}'

    def test_t_resolves_through_the_captured_table(self):
        """The end-user contract: with currentLocale set to a non-English code,
        t(key) returns that language's string, not the English fallback."""
        result = _run_i18n_block(
            'const LOCALE_ET = { hello: "tere" };',
            (
                'hydrateDOM("et");\n'
                '__emit(JSON.stringify({ translated: t("hello") }));\n'
            ),
        )
        assert json.loads(result["out"][-1])["translated"] == "tere"

    def test_window_probe_still_empty_const_does_not_leak(self):
        """The capture must not depend on the table becoming a window property
        (it never does for const): assert the pre-fix probe would still find
        nothing, so this test cannot pass by accident on the old loader."""
        result = _run_i18n_block(
            'const LOCALE_ET = { hello: "tere" };',
            '__emit(JSON.stringify({ onWindow: typeof window.LOCALE_ET }));\n',
        )
        assert json.loads(result["out"][-1])["onWindow"] == "undefined"

    def test_unknown_locale_returns_empty_object(self):
        """A code unknown to the closed vocabulary returns {} and must not
        throw -- the missing-table contract is preserved."""
        result = _run_i18n_block(
            "",
            '__emit(JSON.stringify({ empty: Object.keys(loadLocaleTable("nope")).length === 0 }));\n',
        )
        assert json.loads(result["out"][-1])["empty"] is True

    def test_english_table_still_eager(self):
        """With the tables declared BEFORE the i18n block (template order),
        the eager-style capture path still works: t() falls back to English
        for a key missing in the active table. NOTE: the real generated page
        does NOT have this order -- that case is pinned separately by
        test_english_fallback_recovers_in_shipped_page_order below."""
        app = APP_JS.read_text(encoding="utf-8")
        start = app.index("let currentLocale")
        hydrate = app.index("function hydrateDOM(locale)")
        nxt = app.find("\nfunction ", hydrate + 10)
        block = app[start:nxt]
        script = (
            'const __out = [];\n'
            'const __emit = (x) => __out.push(x);\n'
            'const document = { querySelectorAll: () => [] };\n'
            'const window = globalThis;\n'
            'const LOCALE_EN = { fallback_key: "english" };\n'
            'const LOCALE_ET = { hello: "tere" };\n'
            + block
            + '\n'
            'hydrateDOM("et");\n'
            '__emit(JSON.stringify({ fallback: t("fallback_key") }));\n'
            '__emit(JSON.stringify({ translated: t("hello") }));\n'
            'console.log(__out[__out.length - 2] + "|" + __out[__out.length - 1]);\n'
        )
        proc = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, timeout=30
        )
        if proc.returncode != 0:
            pytest.fail(f"i18n runtime threw in V8:\n{proc.stderr}")
        fallback_part, translated_part = proc.stdout.strip().split("|", 1)
        assert json.loads(fallback_part)["fallback"] == "english"
        assert json.loads(translated_part)["translated"] == "tere"

    def test_english_fallback_recovers_in_shipped_page_order(self):
        """AUDIT cycle-2 IMP-001: the generated page loads app.js BEFORE
        locale-en.js (index.lite.html lines 379-380; window.py injects the
        locale tags before </body>). The eager initializer therefore captured
        {} into _localeTables.en forever and t() returned raw keys in every
        language. The lazy _ensureEnTable capture must recover: define
        LOCALE_EN only AFTER the i18n block (the shipped order) and assert
        the English fallback resolves."""
        result = _run_i18n_block(
            'const LOCALE_EN = { fallback_key: "english" };\n',
            '__emit(JSON.stringify({ fallback: t("fallback_key") }));\n',
        )
        assert json.loads(result["out"][-1])["fallback"] == "english"

    def test_english_startup_hydrate_resolves_keys(self):
        """AUDIT cycle-2 IMP-001, end-user contract: a session configured for
        English (the default) must translate keys, not show them raw."""
        result = _run_i18n_block(
            'const LOCALE_EN = { toolbar_start: "Start" };\n',
            (
                'hydrateDOM("en");\n'
                '__emit(JSON.stringify({ translated: t("toolbar_start") }));\n'
            ),
        )
        assert json.loads(result["out"][-1])["translated"] == "Start"

    def test_failed_dynamic_load_does_not_wedge_locale(self):
        """AUDIT cycle-2 IMP-003: a failed dynamic locale load (onerror, or an
        onload whose parse produced nothing) must clear _localeLoading so the
        next loadLocaleTable call retries. Pre-fix the flag was set forever
        and the locale stayed wedged for the whole session (probe: two calls
        appended exactly one script and the second still returned {})."""
        app = APP_JS.read_text(encoding="utf-8")
        start = app.index("let currentLocale")
        hydrate = app.index("function hydrateDOM(locale)")
        nxt = app.find("\nfunction ", hydrate + 10)
        block = app[start:nxt]
        script = (
            "const __appended = [];\n"
            "const document = {\n"
            "  querySelectorAll: () => [],\n"
            "  createElement: () => ({}),\n"
            "  head: {\n"
            "    appendChild: (s) => __appended.push(s),\n"
            "  },\n"
            "};\n"
            "const window = globalThis;\n"
            + block
            + "\n"
            "const a = loadLocaleTable(\"et\");\n"
            "const b = loadLocaleTable(\"et\");\n"
            "const afterTwoCalls = __appended.length;\n"
            # Simulate the transport failure of the first dynamic script.
            "if (__appended[0].onerror) __appended[0].onerror();\n"
            "const c = loadLocaleTable(\"et\");\n"
            "const afterFailure = __appended.length;\n"
            "console.log(JSON.stringify({ afterTwoCalls, afterFailure }));\n"
        )
        proc = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, timeout=30
        )
        if proc.returncode != 0:
            pytest.fail(f"i18n runtime threw in V8:\n{proc.stderr}")
        data = json.loads(re.search(r"\{.*\}", proc.stdout, re.DOTALL).group(0))
        assert data["afterTwoCalls"] == 1  # in-flight de-dup still holds
        assert data["afterFailure"] == 2  # ...but a failed load is retried

    def test_node_check_app_js(self):
        proc = subprocess.run(
            ["node", "--check", str(APP_JS)], capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stderr
