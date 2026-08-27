"""T-594 / PERF-005: the live agent console must bound its DOM.

The backend already rolls its in-memory line buffer at 5000 and caps the
transcript at 5 MiB, but the WebView appended one ``.agent-output-line`` div
per line forever. A long/noisy run grew the live DOM without limit even after
storage had stopped caring -- degrading the primary console. Now
``appendOutputLines`` batches into a fragment and prunes the oldest excess so
``#agentOutputLines`` plateaus at ``MAX_LIVE_OUTPUT_NODES``, while the cumulative
line count (tracked elsewhere) and ``parseTestLine``'s per-line inspection are
never affected.

This is a pure-function regression: ``appendOutputLines`` is extracted verbatim
from app.js and exercised against a tiny DOM shim under Node, exactly like the
source-shape tests use for the frontend (there is no JS test runner; ``node``
is the gate).
"""

from __future__ import annotations

import re
import subprocess
import sys
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
    try:
        subprocess.run(
            [sys.executable, "-c", "import shutil; print(shutil.which('node'))"],
            check=True,
            capture_output=True,
        )
        return (
            subprocess.run(["node", "--version"], capture_output=True).returncode == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_live_dom_plateaus_while_line_count_grows(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("appendOutputLines", src)
    max_nodes = _max_nodes(src)
    # A tiny DOM shim sufficient for appendOutputLines; the container tracks a
    # children array and exposes childElementCount + firstChild semantics.
    harness = f"""
globalThis.document = {{
  createDocumentFragment: () => {{ const f = new FakeNode(); f.isFragment = true; return f; }},
  createElement: (tag) => new FakeNode(tag),
}};
globalThis.window = {{}};
globalThis.parseTestLine = (root, line) => {{ globalThis.__parsed = (globalThis.__parsed || 0) + 1; }};
const MAX_LIVE_OUTPUT_NODES = {max_nodes};
class FakeNode {{
  constructor(tag) {{
    this.tagName = tag; this.className = ""; this.textContent = "";
    this.children = []; this.parent = null; this.isFragment = false;
  }}
  appendChild(node) {{
    if (node.isFragment) {{
      for (const c of node.children) this.appendChild(c);
      node.children = [];
      return node;
    }}
    node.parent = this; this.children.push(node); return node;
  }}
  removeChild(node) {{ this.children.shift(); return node; }}
  get childElementCount() {{ return this.children.length; }}
  get firstChild() {{ return this.children[0] || null; }}
}}
{fn}
const container = new FakeNode("div");
const TOTAL = 100000;
for (let i = 0; i < TOTAL; i++) {{
  appendOutputLines(container, ["line " + i], "root");
}}
const out = {{
  count: container.childElementCount,
  parsed: globalThis.__parsed,
  max: {max_nodes},
}};
if (container.childElementCount > {max_nodes}) {{
  console.error("DOM exceeded cap: " + container.childElementCount);
  process.exit(1);
}}
// The last line appended must still be the newest node; the oldest are gone.
const last = container.children[container.children.length - 1];
if (last.textContent !== "line " + (TOTAL - 1)) {{
  console.error("newest line lost: " + last.textContent); process.exit(2);
}}
if (globalThis.__parsed !== TOTAL) {{
  console.error("parseTestLine not called per line: " + globalThis.__parsed); process.exit(3);
}}
console.log(JSON.stringify(out));
"""
    script = tmp_path / "perf005.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(
        ["node", str(script)], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr
    import json

    out = json.loads(res.stdout.strip())
    assert out["count"] == max_nodes, out
    assert out["parsed"] == 100000, out


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_append_batches_preserve_order_within_window(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("appendOutputLines", src)
    max_nodes = _max_nodes(src)
    harness = f"""
globalThis.document = {{
  createDocumentFragment: () => {{ const f = new FakeNode(); f.isFragment = true; return f; }},
  createElement: (tag) => new FakeNode(tag),
}};
globalThis.window = {{}};
globalThis.parseTestLine = () => {{}};
const MAX_LIVE_OUTPUT_NODES = {max_nodes};
class FakeNode {{
  constructor(tag) {{ this.tagName = tag; this.children = []; this.isFragment = false; }}
  appendChild(node) {{
    if (node.isFragment) {{ for (const c of node.children) this.appendChild(c); node.children = []; return node; }}
    this.children.push(node); return node;
  }}
  removeChild(node) {{ this.children.shift(); return node; }}
  get childElementCount() {{ return this.children.length; }}
  get firstChild() {{ return this.children[0] || null; }}
}}
{fn}
const c = new FakeNode("div");
appendOutputLines(c, ["a", "b", "c"], "r");
const tail = c.children.map(n => n.textContent).join(",");
if (tail !== "a,b,c") {{ console.error("order wrong: " + tail); process.exit(1); }}
console.log("ok");
"""
    script = tmp_path / "perf005b.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(
        ["node", str(script)], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout
