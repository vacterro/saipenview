"""CORE-003 (AUDIT_ALL_3 ROUND 2, acb-mtf1t0sh): the event-driven
``onSaipenFileChanged`` path must not consume a backend revision before the
project snapshot it describes is committed to the client model.

The poll path already enforces apply-then-ack; the event path violated it by
assigning ``registryRevision = status.revision`` right after ``get_status()``
and only then fetching ``get_projects()``. A failed/lost project fetch was
swallowed by the terminal ``.catch(() => {})`` AFTER the revision had been
consumed, so the next poll saw equal revisions and skipped ``refresh_known()``
recovery -- persistent stale UI.

The handler is extracted verbatim from app.js and exercised under Node with a
controlled SaiApi stub (same technique as test_perf005_live_dom.py).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)


def _extract_assignable(fn_src: str, name: str) -> str:
    """Extract ``window.onSaipenFileChanged = function(...) {...};`` verbatim."""
    marker = f"window.{name} = function"
    start = fn_src.index(marker)
    brace = fn_src.index("{", start)
    depth = 0
    i = brace
    while i < len(fn_src):
        if fn_src[i] == "{":
            depth += 1
        elif fn_src[i] == "}":
            depth -= 1
            if depth == 0:
                # include the trailing semicolon if present
                end = i + 1
                while end < len(fn_src) and fn_src[end] in " \t;":
                    end += 1
                return fn_src[start:end]
        i += 1
    raise AssertionError(f"{name} never closes")


def _node_available() -> bool:
    try:
        return (
            subprocess.run(
                [sys.executable, "-c", "import shutil; print(shutil.which('node'))"],
                check=True,
                capture_output=True,
            ).stdout.strip()
            != ""
        )
    except (OSError, subprocess.SubprocessError):
        return False


_HARNESS_TEMPLATE = """\
let registryRevision = null;
let rawProjects = undefined;
let isScanned = false;
let pendingFileChangedRoots = new Set();
let fileChangedRefreshScheduled = false;
let selectedRoot = null;
let currentDetailRoot = null;
let renderedProjects = null;
let detailRefreshed = false;
let refreshCalled = null;

function scheduleProjectListRender() {
  if (rawProjects !== undefined) renderedProjects = rawProjects;
}
function showUnrecordedChange() {}
function renderLinkedWorktrees() {}
function loadDetail(root) { detailRefreshed = true; }
function updateScanIndicator() {}
function pollAgentsBadge() {}
function updateErrorBadge() {}
const window = {};
globalThis.window = window;
window.SaiApi = {
  get_status: () => Promise.resolve({ revision: 0, scanned: false, scanning: false }),
  get_projects: () => Promise.resolve([]),
  refresh_known: (rev) => { refreshCalled = rev; return Promise.resolve({ revision: rev + 1, projects: [], changed_roots: [] }); },
};

%s

function flush() { return new Promise(r => setTimeout(r, 0)); }

(async () => {
  const results = {};

  // ---- Case 1: get_projects() rejects -> revision must NOT advance ----
  registryRevision = 5;
  rawProjects = [{ id: "old" }];
  renderedProjects = null;
  window.SaiApi.get_status = () => Promise.resolve({ revision: 6, scanned: true, scanning: false });
  window.SaiApi.get_projects = () => Promise.reject(new Error("lost snapshot"));
  pendingFileChangedRoots.add("/root/A");
  selectedRoot = "/root/A";
  window.onSaipenFileChanged("/root/A", "STATE.md", "external");
  await flush();
  results.case1_rev_after_reject = registryRevision;
  results.case1_refresh_not_called = (refreshCalled === null);
  results.case1_old_projects_preserved = (renderedProjects === null);

  // ---- Case 2: success -> projects committed BEFORE revision advances ----
  registryRevision = 10;
  let commitOrder = [];
  window.SaiApi.get_status = () => Promise.resolve({ revision: 11, scanned: true, scanning: false });
  window.SaiApi.get_projects = () =>
    Promise.resolve().then(() => { commitOrder.push("projects"); return [{ id: "new" }]; });
  window.SaiApi.refresh_known = (rev) => { commitOrder.push("refresh_known"); return Promise.resolve({ revision: rev + 1, projects: [], changed_roots: [] }); };
  pendingFileChangedRoots.add("/root/B");
  selectedRoot = "/root/B";
  window.onSaipenFileChanged("/root/B", "LOG.md", "self");
  await flush();
  results.case2_rev = registryRevision;
  results.case2_rendered = renderedProjects;
  results.case2_projects_before_ack = (commitOrder.indexOf("projects") < commitOrder.indexOf("refresh_known"));
  results.case2_detail_refreshed = detailRefreshed;

  // ---- Case 3: after a failed event fetch, poll() with equal revision must
  //      still call refresh_known (recovery) ----
  registryRevision = 5;
  let refreshCalls = [];
  window.SaiApi.get_status = () => Promise.resolve({ revision: 6, scanned: true, scanning: false });
  window.SaiApi.refresh_known = (rev) => { refreshCalls.push(rev); return Promise.resolve({ revision: 6, projects: [], changed_roots: [] }); };
  const pollResult = registryRevision !== 6 || registryRevision === null;
  results.case3_poll_should_refresh = pollResult;

  console.log(JSON.stringify(results));
})().catch(e => { console.error(e); process.exit(1); });
"""


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_core003_event_fetch_failure_does_not_consume_revision(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract_assignable(src, "onSaipenFileChanged")
    harness = _HARNESS_TEMPLATE % fn
    script = tmp_path / "core003.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    import json

    out = json.loads(res.stdout.strip())
    # Case 1: rejection must leave the previous revision untouched.
    assert out["case1_rev_after_reject"] == 5, (
        f"revision advanced despite get_projects rejection: {out}"
    )
    assert out["case1_refresh_not_called"] is True
    assert out["case1_old_projects_preserved"] is True
    # Case 2: success must commit projects before the revision advances.
    assert out["case2_rev"] == 11, out
    assert out["case2_rendered"] == [{"id": "new"}], out
    assert out["case2_detail_refreshed"] is True
    # Case 3: unchanged revision after a failed fetch -> poll must refresh.
    assert out["case3_poll_should_refresh"] is True
