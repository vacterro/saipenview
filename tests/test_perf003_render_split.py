"""T-592 / PERF-003: a burst of project-list updates must collapse to ONE paint.

Previously every file-change notification (and overlapping scan/poll results)
called ``render()`` synchronously, rebuilding the entire list N times within a
single frame. ``scheduleProjectListRender`` now coalesces them onto the next
animation frame: N calls in one tick -> exactly one ``render`` invocation.

There is no JS test runner; ``node --check`` is the gate and a Node harness
exercises the extracted scheduler against a tiny DOM shim (mirrors the
source-shape tests).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)


def _extract(name: str, src: str) -> str:
    start = src.index(f"function {name}")
    brace = src.index("{", start)
    depth = 0
    i = brace
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError(f"function {name} never closes")


def _node_available() -> bool:
    return subprocess.run(["node", "--version"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_coalescer_collapses_burst_to_single_paint(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("scheduleProjectListRender", src)
    harness = f"""
globalThis.window = {{}};
globalThis.__renderCalls = 0;
function render() {{ globalThis.__renderCalls++; }}
globalThis.rawProjects = [];
globalThis.isScanned = true;
// The scheduler's module-level guard flag must exist in the harness.
let _listRenderScheduled = false;
// Capture the rAF callback instead of executing it, so we control the tick.
let _rafCb = null;
globalThis.window.requestAnimationFrame = (cb) => {{ _rafCb = cb; return 1; }};
{fn}
// Fire a burst of 10 notifications in the same tick.
for (let i = 0; i < 10; i++) scheduleProjectListRender();
if (globalThis.__renderCalls !== 0) {{ console.error("painted before tick"); process.exit(1); }}
if (_rafCb === null) {{ console.error("no frame scheduled"); process.exit(2); }}
// One tick fires -> exactly one render.
_rafCb();
if (globalThis.__renderCalls !== 1) {{
  console.error("expected 1 paint, got " + globalThis.__renderCalls); process.exit(3);
}}
// A second burst after the flag reset must schedule + paint again.
scheduleProjectListRender();
if (_rafCb === null) {{ console.error("second frame not scheduled"); process.exit(4); }}
_rafCb();
if (globalThis.__renderCalls !== 2) {{
  console.error("expected 2 paints total, got " + globalThis.__renderCalls); process.exit(5);
}}
console.log("ok");
"""
    script = tmp_path / "perf003.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_coalescer_falls_back_to_settimeout_when_no_raf(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("scheduleProjectListRender", src)
    harness = f"""
globalThis.window = {{}};  // no requestAnimationFrame
globalThis.__renderCalls = 0;
function render() {{ globalThis.__renderCalls++; }}
globalThis.rawProjects = [];
globalThis.isScanned = true;
let _listRenderScheduled = false;
let _timeoutCb = null;
globalThis.setTimeout = (cb, ms) => {{ _timeoutCb = cb; return 1; }};
{fn}
scheduleProjectListRender();
if (_timeoutCb === null) {{ console.error("no setTimeout fallback"); process.exit(1); }}
_timeoutCb();
if (globalThis.__renderCalls !== 1) {{ console.error("fallback did not paint: " + globalThis.__renderCalls); process.exit(2); }}
console.log("ok");
"""
    script = tmp_path / "perf003b.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout
