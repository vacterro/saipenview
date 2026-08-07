r"""T-169: async frontend project-switch guard.

`restoreLastTranscript` used to mark a root as restored BEFORE the promise
resolved, then wrote the old project's transcript into whatever panel was
showing at that moment. A project switch mid-flight dropped one project's
stored output into another project's pane, and a transient failure or a
found=false left the root permanently marked so it could never restore.

These run the REAL functions under node with a stubbed DOM and a manually
resolved promise, because the only honest proof of "a stale response cannot
touch the new panel" is a promise that resolves after the switch.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)

HARNESS = """\
const agentRestoredRoots = new Set();
let currentDetailRoot = "A";
const agentStatusCache = {{}};
const appended = [];
const datasetRoot = {{ value: "A" }};
const document = {{
  getElementById: (id) => {{
    if (id === "agentOutputLines") return {{
      childElementCount: 0,
      appendChild: (el) => appended.push(el.__kind || "node"),
      parentElement: {{ scrollTop: 0, scrollHeight: 100 }},
    }};
    if (id === "agentOutputMeta") return null;
    // T-177: the container itself carries NO data-root; the .agent-panel
    // child does. The stub must mirror the real DOM or the guard test is
    // testing a different element than the app reads.
    if (id === "agentPanelContainer") return {{
      querySelector: (sel) => sel === ".agent-panel"
        ? {{ dataset: {{ root: datasetRoot.value }} }}
        : null,
    }};
    return null;
  }},
  createElement: (tag) => ({{ __kind: tag, className: "", textContent: "", appendChild(){{}} }}),
}};
const window = {{ pywebview: {{ api: {{}} }} }};
function t() {{ return "RESTORED"; }}
function formatLocalTime() {{ return "now"; }}
{fn}
"""


def _extract(source: str, name: str) -> str:
    start = source.index(f"function {name}")
    brace = source.index("{", start)
    depth = 0
    i = brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
        i += 1
    raise AssertionError(f"function {name} never closes")


def _run(script_body: str) -> dict:
    source = APP_JS.read_text(encoding="utf-8")
    fn = (
        _extract(source, "isCurrentProjectPanel")
        + "\n"
        + _extract(source, "restoreLastTranscript")
    )
    harness = HARNESS.format(fn=fn)
    r = subprocess.run(
        ["node", "-e", harness + script_body],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(f"node harness failed: {r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


SCENARIOS = """\
{scenario}
setTimeout(() => {{
  console.log(JSON.stringify({{
    appended: appended.length,
    blocked: agentRestoredRoots.has("A"),
  }}));
}}, 150);
"""


@pytest.fixture(scope="module")
def node_ok() -> None:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        pytest.skip("node not available")


class TestProjectSwitchRace:
    def test_stale_response_cannot_touch_the_new_panel(self, node_ok):
        body = SCENARIOS.format(
            scenario=(
                "window.pywebview.api.get_last_agent_transcript = (root) => "
                "new Promise((res) => { window.__resolve = res; });\n"
                'restoreLastTranscript("A", {});\n'
                'currentDetailRoot = "B"; datasetRoot.value = "B";\n'
                'window.__resolve({ found: true, run: {}, total: 1, lines: ["OLD"] });'
            )
        )
        out = _run(body)
        assert out["appended"] == 0, (
            "the old project's transcript reached the new panel"
        )
        assert out["blocked"] is False, "root A was marked restored despite the switch"

    def test_no_switch_restores_and_marks(self, node_ok):
        body = SCENARIOS.format(
            scenario=(
                "window.pywebview.api.get_last_agent_transcript = (root) => "
                "new Promise((res) => { window.__resolve = res; });\n"
                'restoreLastTranscript("A", {});\n'
                'window.__resolve({ found: true, run: {}, total: 1, lines: ["L"] });'
            )
        )
        out = _run(body)
        assert out["appended"] > 0
        assert out["blocked"] is True

    def test_found_false_is_not_permanently_blocked(self, node_ok):
        body = SCENARIOS.format(
            scenario=(
                "window.pywebview.api.get_last_agent_transcript = (root) => "
                "new Promise((res) => { window.__resolve = res; });\n"
                'restoreLastTranscript("A", {});\n'
                "window.__resolve({ found: false });"
            )
        )
        out = _run(body)
        assert out["blocked"] is False, "found=false permanently blocked the root"

    def test_transient_failure_is_not_permanently_blocked(self, node_ok):
        body = SCENARIOS.format(
            scenario=(
                "window.pywebview.api.get_last_agent_transcript = (root) => "
                "new Promise((res, rej) => { window.__reject = rej; });\n"
                'restoreLastTranscript("A", {});\n'
                'window.__reject(new Error("boom"));'
            )
        )
        out = _run(body)
        assert out["blocked"] is False, (
            "a transient failure permanently blocked the root"
        )
