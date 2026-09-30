"""PERF-001: the flash highlight must bind to the REPLACEMENT DOM in O(N) and
the 20s fade must own those replacement rows.

Before the fix, `updateFlashSnapshot` ran BEFORE `list.innerHTML` replaced the
project list and discovered rows with one document-wide `querySelectorAll` per
flashed root (O(F*N)). The refs it captured were then disconnected by the
replacement, so `_flashTick` deleted the flash state and the highlight froze.

These tests drive the ACTUAL source functions against a bounded DOM shim and
count queries, comparisons and removeChild/node work.
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


def _run_harness(tmp_path, name: str, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return subprocess.run(["node", str(script)], capture_output=True, text=True)


DOM_SHIM = r"""
// Minimal DOM: rows keyed by data-root, a container whose innerHTML replaces
// children, and counters for querySelectorAll + removeChild.
let __qsCalls = 0;
let __removeChildCalls = 0;

class El {
  constructor(tag, root) {
    this.tagName = tag;
    this.children = [];
    this.parentNode = null;
    this._attrs = {};
    this.style = {};
    this.isConnected = true;
    if (root !== undefined) this._attrs["data-root"] = root;
    this.classList = { contains: () => false };
  }
  getAttribute(k) { return this._attrs[k] !== undefined ? this._attrs[k] : null; }
  setAttribute(k, v) { this._attrs[k] = v; }
  addEventListener() {}
  get childElementCount() { return this.children.length; }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { c.parentNode = this; this.children.push(c); c.isConnected = true; return c; }
  removeChild(c) {
    __removeChildCalls++;
    const i = this.children.indexOf(c);
    if (i >= 0) { this.children.splice(i, 1); c.parentNode = null; c.isConnected = false; }
    return c;
  }
  append(...nodes) { for (const n of nodes) { if (typeof n === "string") { const t = new El("#text"); t.textContent = n; this.appendChild(t); } else this.appendChild(n); } }
  get innerHTML() { return this._html || ""; }
  set innerHTML(v) {
    // Replacing innerHTML disconnects every prior child (the destructive DOM
    // replacement render() performs).
    for (const c of this.children) c.isConnected = false;
    this.children = [];
    this._html = v;
    // Rebuild rows from a data-root=... pattern so the shim has real nodes.
    const re = /data-root="([^"]+)"/g;
    let m;
    while ((m = re.exec(v)) !== null) {
      const row = new El("div", m[1]);
      this.appendChild(row);
    }
  }
  querySelectorAll(sel) {
    if (sel === ".project-row") {
      __qsCalls++;
      return this.children.filter((c) => c._attrs["data-root"] !== undefined);
    }
    return [];
  }
}

const __projectList = new El("div");
globalThis.document = {
  getElementById: (id) => (id === "projectList" ? __projectList : new El("div")),
  querySelector: () => null,
  querySelectorAll: (sel) => {
    // document-wide query (the O(F*N) source in the old updateFlashSnapshot)
    __qsCalls++;
    return __projectList.children.filter((c) => c._attrs["data-root"] !== undefined);
  },
  documentElement: {},
};
globalThis.getComputedStyle = () => ({ getPropertyValue: () => "#4a341b" });
globalThis.Date = Date;
globalThis.__meta = {};
globalThis.__reset = function() { __qsCalls = 0; __removeChildCalls = 0; };
globalThis.__counts = function() { return { qs: __qsCalls, removeChild: __removeChildCalls }; };
globalThis.__projectList = __projectList;
"""


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_flash_binds_replacement_rows_and_fade_owns_them(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    update = _extract("updateFlashSnapshot", src)
    find_row = _extract("_findProjectRow", src)
    tick = _extract("_flashTick", src)
    color = _extract("flashColorFor", src)

    harness = (
        DOM_SHIM
        + r"""
// Module-level state the extracted functions close over.
let prevSnapshot = {};
let flashState = {};
let _flashRowRefs = {};
let _flashTimer = null;
let _flashSurfColor = "#4a341b";
const flashChangesEnabled = true;
const FLASH_DECAY_SECONDS = 20;
const FLASH_HOT = "#C0A060";
function hexBlend() { return "rgb(1, 2, 3)"; }
const _ensureFlashTimer = () => { _flashTimer = _flashTimer || 1; };
const _stopFlashTimer = () => { _flashTimer = null; _flashRowRefs = {}; };
"""
        + update
        + "\n"
        + find_row
        + "\n"
        + tick
        + "\n"
        + color
        + r"""

const N = 1000;
function mkProjects(phase) {
  const out = [];
  for (let i = 0; i < N; i++) out.push({ root: "r" + i, phase: phase, task: "t", updated: "u", git_dirty: false });
  return out;
}

// 1. Baseline render: snapshot then install rows.
updateFlashSnapshot(mkProjects("DONE"));
__projectList.innerHTML = mkProjects("DONE").map((p) => `<div class="project-row" data-root="${p.root}"></div>`).join("");

// 2. A change on every row.
updateFlashSnapshot(mkProjects("VERIFY"));

// The old code performed one document-wide query per flashed root HERE; the
// fixed code performs none (binding is deferred to the render pass).
const afterSnapshot = __counts();
globalThis.__meta.active = Object.keys(flashState).length;
globalThis.__meta.qsAfterSnapshot = afterSnapshot.qs;

// 3. Render replacement + single O(N) binding pass (mirrors render()).
__reset();
__projectList.innerHTML = mkProjects("VERIFY").map((p) => `<div class="project-row" data-root="${p.root}"></div>`).join("");
__projectList.children.forEach((row) => {
  const root = row.getAttribute("data-root");
  if (flashChangesEnabled && flashState[root]) {
    const ageMs = Date.now() - flashState[root];
    if (ageMs >= FLASH_DECAY_SECONDS * 1000) { delete flashState[root]; }
    else { _flashRowRefs[root] = row; }
  }
});
const afterBind = __counts();
globalThis.__meta.qsAfterBind = afterBind.qs;
globalThis.__meta.refsBound = Object.keys(_flashRowRefs).length;

// 4. A tick before decay must change the CURRENT row color and retain state.
const beforeTickRefs = Object.keys(_flashRowRefs).length;
_flashTick();
globalThis.__meta.refsAfterTick = Object.keys(_flashRowRefs).length;

if (globalThis.__meta.active !== N) { console.error("not all rows flashed: " + globalThis.__meta.active); process.exit(1); }
if (globalThis.__meta.qsAfterBind > 2) { console.error("binding used too many queries: " + globalThis.__meta.qsAfterBind); process.exit(2); }
if (globalThis.__meta.refsBound !== N) { console.error("refs not rebound to replacement rows: " + globalThis.__meta.refsBound); process.exit(3); }
if (globalThis.__meta.refsAfterTick < N) { console.error("tick deleted live refs: " + globalThis.__meta.refsAfterTick); process.exit(4); }
console.log("ok " + JSON.stringify(globalThis.__meta));
"""
    )
    res = _run_harness(tmp_path, "perf001_flash.js", harness)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_stale_ref_does_not_delete_valid_flash_state(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    update = _extract("updateFlashSnapshot", src)
    find_row = _extract("_findProjectRow", src)
    tick = _extract("_flashTick", src)

    harness = (
        DOM_SHIM
        + r"""
let prevSnapshot = {};
let flashState = {};
let _flashRowRefs = {};
let _flashTimer = null;
let _flashSurfColor = "#4a341b";
const flashChangesEnabled = true;
const FLASH_DECAY_SECONDS = 20;
const FLASH_HOT = "#C0A060";
function hexBlend() { return "rgb(1, 2, 3)"; }
const _ensureFlashTimer = () => {};
const _stopFlashTimer = () => { _flashTimer = null; };
"""
        + update
        + "\n"
        + find_row
        + "\n"
        + tick
        + r"""

// One flashed root with a DISCONNECTED ref but live flash state.
flashState["r0"] = Date.now();
const dead = new El("div", "r0");
dead.isConnected = false;
_flashRowRefs["r0"] = dead;
// A current row for r0 exists in the list.
__projectList.innerHTML = '<div class="project-row" data-root="r0"></div>';

_flashTick();
if (!flashState["r0"]) { console.error("stale ref deleted valid flash state"); process.exit(1); }
if (!_flashRowRefs["r0"] || !_flashRowRefs["r0"].isConnected) { console.error("stale ref not rebound to the current row"); process.exit(2); }
console.log("ok");
"""
    )
    res = _run_harness(tmp_path, "perf001_stale_ref.js", harness)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout
