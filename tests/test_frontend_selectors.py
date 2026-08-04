"""A filesystem path is not a CSS selector, and never was (T-159).

`renderAgentPanel` built element ids by concatenating the project root --
`id="agentControlTop-${root}"` -- and then read them back with
`container.querySelector('#agentControlTop-' + root)`. On Windows every root
carries a drive letter and backslashes, so the result was not a valid selector
and `querySelector` threw. `renderDetailPane` calls `renderAgentPanel` as its
last statement with no guard, so the throw did not stay inside the panel.

The bug survived review and shipped in two releases because nothing about it is
visible in the source: the ids look symmetric, the lookup looks like the
construction, and the failure is a thrown exception in a promise chain nobody
was watching. This test states the rule the code has to follow instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_JS = (Path(__file__).resolve().parent.parent
          / "saipenview" / "ui" / "static" / "app.js")


def _strip_comments(source: str) -> str:
    """Drop `//` and `/* */` comments, keeping line count intact.

    Necessary, not fastidious: the comments in `renderAgentPanel` quote the
    broken code verbatim so the next reader knows what not to do again, and a
    test that greps raw source would fire on the explanation of the bug rather
    than on the bug. Crude by design -- it does not parse strings or regex
    literals -- which is fine for greps that only ever look at code shape.
    """
    without_block = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"),
                           source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.MULTILINE)


@pytest.fixture(scope="module")
def app_js() -> str:
    return _strip_comments(APP_JS.read_text(encoding="utf-8"))


def test_no_selector_is_built_from_a_project_root(app_js: str) -> None:
    """`querySelector`/`querySelectorAll` arguments must not interpolate a root.

    `getElementById` is deliberately not covered: it takes a plain string and
    never parses a selector, so it cannot throw on a path. It is still a bad
    idea for a different reason -- see the next test.
    """
    offenders = []
    # `querySelector(?:All)?`, not `querySelectorAll?` -- the second one reads
    # as "querySelectorAl" plus an optional "l", which matches neither call.
    for match in re.finditer(r"querySelector(?:All)?\(([^;]*?)\)", app_js):
        arg = match.group(1)
        # Only an INTERPOLATED root is the bug. A literal class name that
        # happens to contain the word -- `.remove-root` -- is not.
        interpolated = (re.search(r"\$\{[^}]*\broot\b", arg)
                        or re.search(r"\+\s*(?:escapeHtml\(\s*)?root\b", arg))
        if interpolated:
            line = app_js[: match.start()].count("\n") + 1
            offenders.append(f"app.js:{line}: {arg.strip()[:70]}")
    assert not offenders, (
        "a project root is being interpolated into a CSS selector:\n"
        + "\n".join(offenders)
    )


def test_agent_panel_ids_are_static(app_js: str) -> None:
    """There is one agent panel in the document, so its ids need no key.

    Keying them on the root also broke `getElementById`, quietly and
    differently: the id written into the HTML goes through `escapeHtml`, the
    browser decodes those entities when it parses the attribute, and the lookup
    then searched for the still-escaped string. Identical for most paths, wrong
    for any path containing `&`.
    """
    for element_id in ["agentControlTop", "agentControlBottom",
                       "agentOutputLines", "agentOutputMeta",
                       "agentOutputPanel", "agentSubtitle"]:
        assert f'id="{element_id}"' in app_js, f"{element_id} is no longer a static id"
        assert f'id="{element_id}-' not in app_js, (
            f"{element_id} is keyed on something again"
        )


def test_the_panel_still_knows_which_project_it_is_showing(app_js: str) -> None:
    """Dropping the key from the ids must not drop the information.

    The root moved to a data attribute; without it, a panel rebuilt for another
    project is indistinguishable from a stale one.
    """
    panel = re.search(r'<div class="agent-panel[^>]*>', app_js)
    assert panel, "the agent panel skeleton is gone"
    assert 'data-root=' in panel.group(0), (
        "the panel no longer records which project it is showing"
    )
