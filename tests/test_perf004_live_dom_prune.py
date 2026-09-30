"""PERF-004: a maximum live-output catch-up must not remove DOM nodes one by one.

Before the fix, `appendOutputLines` appended the whole incoming batch and then
ran `while (count > MAX) container.removeChild(container.firstChild)`. A full
5,000-line catch-up delta on an already-full console therefore performed 5,000
synchronous `removeChild` calls in one UI turn.

The fix computes the retained tail first; when the incoming batch alone fills or
exceeds the cap it replaces the old window in ONE operation. `parseTestLine`
still observes every delivered line.

This extends the test_perf005_live_dom.py DOM-shim approach with an
operation-counting shim.
"""

from __future__ import annotations

import re
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


def _max_nodes(src: str) -> int:
    m = re.search(r"const MAX_LIVE_OUTPUT_NODES\s*=\s*(\d+)", src)
    assert m, "MAX_LIVE_OUTPUT_NODES constant missing"
    return int(m.group(1))


def _node_available() -> bool:
    return subprocess.run(["node", "--version"], capture_output=True).returncode == 0


SHIM = r"""
let __removeChild = 0;
let __textContentResets = 0;
class FakeNode {
  constructor(tag) {
    this.tagName = tag; this.className = ""; this._text = "";
    this.children = []; this.parent = null; this.isFragment = false;
  }
  set textContent(v) {
    if (this.isFragment) { this._text = v; return; }
    // Assigning textContent on an element clears children (one bulk op).
    if (v === "") { __textContentResets++; this.children = []; }
    this._text = v;
  }
  get textContent() { return this._text; }
  appendChild(node) {
    if (node.isFragment) { for (const c of node.children) this.appendChild(c); node.children = []; return node; }
    node.parent = this; this.children.push(node); return node;
  }
  removeChild(node) { __removeChild++; const i = this.children.indexOf(node); if (i >= 0) this.children.splice(i, 1); return node; }
  get childElementCount() { return this.children.length; }
  get firstChild() { return this.children[0] || null; }
  get nextSibling() {
    if (!this.parent) return null;
    const i = this.parent.children.indexOf(this);
    return this.parent.children[i + 1] || null;
  }
}
globalThis.document = {
  createDocumentFragment: () => { const f = new FakeNode(); f.isFragment = true; return f; },
  createElement: (tag) => new FakeNode(tag),
  createRange: () => {
    let start = null, end = null;
    return {
      setStartBefore(n) { start = n; },
      setEndAfter(n) { end = n; },
      deleteContents() {
        if (!start || !end || !start.parent) return;
        const parent = start.parent;
        const i = parent.children.indexOf(start);
        const j = parent.children.indexOf(end);
        const removed = j - i + 1;
        parent.children.splice(i, removed);
        for (const c of parent.children) c.parent = parent;
      },
    };
  },
};
globalThis.window = {};
globalThis.parseTestLine = (root, line) => { globalThis.__parsed = (globalThis.__parsed || 0) + 1; };
globalThis.__meta = () => ({ removeChild: __removeChild, resets: __textContentResets });
globalThis.__reset = () => { __removeChild = 0; __textContentResets = 0; };
"""


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_full_window_catchup_is_one_bulk_operation(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("appendOutputLines", src)
    max_nodes = _max_nodes(src)
    harness = (
        SHIM
        + f"const MAX_LIVE_OUTPUT_NODES = {max_nodes};\n"
        + fn
        + r"""
const container = new FakeNode("div");
// Pre-fill to the cap.
for (let i = 0; i < MAX_LIVE_OUTPUT_NODES; i++) {
  const d = new FakeNode("div"); d._text = "old " + i; container.appendChild(d);
}
__reset();
// A full-window catch-up delta.
const delta = [];
for (let i = 0; i < MAX_LIVE_OUTPUT_NODES; i++) delta.push("new " + i);
appendOutputLines(container, delta, "r");

const m = __meta();
if (container.childElementCount !== MAX_LIVE_OUTPUT_NODES) {
  console.error("wrong final count: " + container.childElementCount); process.exit(1);
}
// newest 5000 in order: first is "new 0", last is "new 4999".
const first = container.children[0]._text;
const last = container.children[container.childElementCount - 1]._text;
if (first !== "new 0" || last !== "new " + (MAX_LIVE_OUTPUT_NODES - 1)) {
  console.error("tail wrong: " + first + " .. " + last); process.exit(2);
}
// The whole point: NOT one removeChild per overflowed node.
if (m.removeChild > 10) {
  console.error("per-node removal not collapsed: " + m.removeChild); process.exit(3);
}
if (globalThis.__parsed !== MAX_LIVE_OUTPUT_NODES) {
  console.error("parseTestLine count wrong: " + globalThis.__parsed); process.exit(4);
}
console.log("ok " + JSON.stringify(m));
"""
    )
    script = tmp_path / "perf004_bulk.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_small_batch_overflow_is_bounded(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("appendOutputLines", src)
    max_nodes = _max_nodes(src)
    harness = (
        SHIM
        + f"const MAX_LIVE_OUTPUT_NODES = {max_nodes};\n"
        + fn
        + r"""
const container = new FakeNode("div");
for (let i = 0; i < MAX_LIVE_OUTPUT_NODES; i++) {
  const d = new FakeNode("div"); d._text = "old " + i; container.appendChild(d);
}
__reset();
appendOutputLines(container, ["a", "b", "c"], "r");
if (container.childElementCount !== MAX_LIVE_OUTPUT_NODES) {
  console.error("count drifted: " + container.childElementCount); process.exit(1);
}
const last = container.children[container.childElementCount - 1]._text;
if (last !== "c") { console.error("newest missing: " + last); process.exit(2); }
const m = __meta();
// A 3-line overflow must not cost 5000 removals.
if (m.removeChild > 10) { console.error("small overflow unbounded: " + m.removeChild); process.exit(3); }
console.log("ok");
"""
    )
    script = tmp_path / "perf004_small.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_empty_batch_is_noop(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("appendOutputLines", src)
    max_nodes = _max_nodes(src)
    harness = (
        SHIM
        + f"const MAX_LIVE_OUTPUT_NODES = {max_nodes};\n"
        + fn
        + r"""
const container = new FakeNode("div");
appendOutputLines(container, [], "r");
if (container.childElementCount !== 0) { console.error("empty batch mutated DOM"); process.exit(1); }
if (globalThis.__parsed) { console.error("empty batch parsed"); process.exit(2); }
console.log("ok");
"""
    )
    script = tmp_path / "perf004_empty.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout
