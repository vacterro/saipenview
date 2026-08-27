"""T-589 / W2-010: Settings runSeq must not count semantic failures as success.

``runSeq`` applied a batch of config setters and counted every *resolved*
Promise as success. But several backend setters resolve with a failure
payload -- ``set_engine_overrides`` returns ``{ok:false}``,
``set_autostart_enabled`` returns a bare ``false``, and the hotkey setters
(now) return ``{ok:false}`` on a binding failure. The modal then closed green
having written nothing. ``setterFailed`` is the explicit result contract that
classifies those as failures so they land in ``failed`` (keeping Settings
open with a visible error) instead of ``applied``.

No JS test runner exists; ``node --check`` is the gate and a Node harness
exercises the extracted classifier (mirrors the source-shape tests).
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
def test_setter_failed_classifies_semantic_failures(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("setterFailed", src)
    harness = f"""
{fn}
const cases = [
  [false, true, "bare false autostart"],
  [{{ok:false}}, true, "engine overrides ok:false"],
  [{{ok:false, error:"x"}}, true, "hotkey ok:false"],
  [{{ok:true}}, false, "engine overrides ok:true"],
  [{{}}, false, "get_config() without ok"],
  [undefined, false, "undefined result"],
  [true, false, "bare true"],
  ["ok", false, "non-object truthy"],
];
let bad = 0;
for (const [res, expect, label] of cases) {{
  const got = setterFailed(res);
  if (got !== expect) {{ console.error("MISMATCH " + label + ": got " + got + " want " + expect); bad++; }}
}}
if (bad > 0) process.exit(1);
console.log("ok");
"""
    script = tmp_path / "w2010.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout
