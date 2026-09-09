"""T-803 / PERF-004: the running-agents badge is count-only and coalesced.

The ticket promised three things and the tree it shipped delivered one and a
half:

* "count-only backend from _processes under lock, no psutil" -- real, and now
  pinned: `ProcessManager.count_running` must never touch the psutil surface
  `get_status` uses, and `Api.running_agent_count` must not route through
  `list_running_agents`.
* "fleet dashboard still collects metrics" -- real, and pinned here so the
  cheap path is never mistaken for a licence to strip the dashboard's data.
* "coalesce badge refreshes" -- NOT implemented. `pollAgentsBadge` opened one
  RPC per caller, and it has three independent callers: the 5s registry poll,
  the output ticker's periodic status pass while an agent runs, and every
  launch/stop/kill handler. Overlapping calls each fetched and each painted,
  so the badge could also settle on an out-of-order value.

The JS half is exercised the way the rest of this suite exercises frontend
behaviour: the function is extracted verbatim from `app.js` and run under
`node` with a controlled stub. There is no JS test runner in this project.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from saipenview.runtime import AgentProcess, ProcessManager

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)


def _extract(name: str, src: str) -> str:
    """The `function <name>` declaration, verbatim, brace-balanced."""
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


def _extract_let(name: str, src: str) -> str:
    """The `let <name> = ...;` statement the guard needs to exist at all."""
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"let {name}"):
            return stripped
    raise AssertionError(f"let {name} not found in app.js")


def _node_available() -> bool:
    try:
        return subprocess.run(["node", "--version"], capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ── backend: the count path must not be the metrics path ─────────────────────


class _FakeProc:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid

    def poll(self):
        return None


def _agent(root: str, status: str) -> AgentProcess:
    ap = AgentProcess(
        engine=None,  # never touched by count_running
        project_root=root,
        instruction="go",
        process=_FakeProc(),
        status=status,
    )
    ap.run_id = f"run-{root}"
    ap.control_id = f"ctl-{root}"
    return ap


def _manager_with(states: list[str]) -> ProcessManager:
    """A ProcessManager carrying synthetic entries, no real subprocesses.

    ``object.__new__``: a real construction reaches SessionStore and the write
    coordinator's ownership registry, neither of which this ticket is about,
    and both of which would put unrelated I/O in front of the assertion.
    """
    pm = object.__new__(ProcessManager)
    pm._lock = threading.Lock()
    pm._processes = {
        f"root{i}": _agent(f"root{i}", status) for i, status in enumerate(states)
    }
    pm._buffer_size = 100
    pm._stuck_agents = set()
    return pm


class TestCountPathTouchesNoMetrics:
    def test_count_running_never_calls_psutil(self, monkeypatch):
        """psutil is the whole cost being avoided, so its absence is the test.

        A count that reached ``get_status`` would prime a CPU sampler and read
        ``memory_info`` per agent -- process-API work for one toolbar integer.
        """
        import psutil

        def explode(*args, **kwargs):
            raise AssertionError("count path invoked psutil")

        monkeypatch.setattr(psutil, "Process", explode)
        pm = _manager_with(["running", "running", "done", "killed", "failed"])
        monkeypatch.setattr(
            pm.__class__,
            "get_status",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("count path invoked get_status")
            ),
        )
        assert pm.count_running() == 2

    def test_count_matches_list_running_length(self, monkeypatch):
        """Cheaper must not mean different.

        ``list_running`` is the reference answer; a count that disagreed with
        it would make the badge lie about the fleet the dashboard shows.
        """
        pm = _manager_with(["running", "done", "running", "failed", "running"])
        monkeypatch.setattr(
            pm.__class__,
            "get_status",
            lambda self, root, expected_run_id=None: {"status": "running"},
        )
        assert pm.count_running() == len(pm.list_running())

    def test_empty_and_all_terminal_are_zero(self):
        assert _manager_with([]).count_running() == 0
        assert _manager_with(["done", "failed", "killed"]).count_running() == 0


class TestFleetDashboardStillCollectsMetrics:
    def test_list_running_still_reports_cpu_and_memory(self, monkeypatch):
        """The dashboard is the reason the expensive path still exists."""
        pm = _manager_with(["running", "done"])
        monkeypatch.setattr(
            pm.__class__,
            "get_status",
            lambda self, root, expected_run_id=None: {
                "status": "running",
                "cpu_percent": 12.5,
                "memory_mb": 64.0,
            },
        )
        rows = pm.list_running()
        assert len(rows) == 1
        assert rows[0]["cpu_percent"] == 12.5
        assert rows[0]["memory_mb"] == 64.0
        assert rows[0]["root"] == "root0"


# ── frontend: the badge must coalesce ────────────────────────────────────────

_HARNESS = """\
%(guard_flags)s

let calls = 0;
let resolvers = [];
let painted = [];

const document = {
  getElementById: () => ({ style: {}, set textContent(v) { painted.push(v); } }),
};
globalThis.document = document;
const window = {};
globalThis.window = window;
window.SaiApi = {
  running_agent_count: () => {
    calls++;
    return new Promise(res => resolvers.push(res));
  },
};

%(fn)s

function flush() { return new Promise(r => setTimeout(r, 0)); }

(async () => {
  const out = {};

  // Burst: five callers while the first request is still open.
  for (let i = 0; i < 5; i++) pollAgentsBadge();
  out.calls_during_burst = calls;

  // Settle the in-flight request: the folded callers must produce exactly ONE
  // trailing refresh, not five.
  resolvers.shift()(3);
  await flush();
  out.calls_after_settle = calls;

  // Settle the trailing refresh; nothing further may be scheduled.
  resolvers.shift()(4);
  await flush();
  await flush();
  out.calls_after_trailing = calls;
  out.painted = painted;

  // A later, non-overlapping transition must still be read back.
  pollAgentsBadge();
  out.calls_after_idle_call = calls;
  resolvers.shift()(0);
  await flush();
  out.painted_final = painted;

  // A rejected count must not wedge the guard for the rest of the session.
  window.SaiApi.running_agent_count = () => {
    calls++;
    return Promise.reject(new Error("bridge down"));
  };
  pollAgentsBadge();
  await flush();
  await flush();
  window.SaiApi.running_agent_count = () => {
    calls++;
    return new Promise(res => resolvers.push(res));
  };
  const before = calls;
  pollAgentsBadge();
  out.recovered_after_rejection = (calls === before + 1);

  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_badge_refreshes_are_coalesced(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    harness = _HARNESS % {
        "guard_flags": "\n".join(
            [
                _extract_let("_badgeInFlight", src),
                _extract_let("_badgeRefreshPending", src),
            ]
        ),
        "fn": _extract("pollAgentsBadge", src),
    }
    script = tmp_path / "badge.js"
    script.write_text(harness, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip())

    assert out["calls_during_burst"] == 1, (
        f"five overlapping callers opened {out['calls_during_burst']} RPCs -- "
        "badge refreshes are not coalesced"
    )
    assert out["calls_after_settle"] == 2, (
        f"folded callers produced {out['calls_after_settle'] - 1} trailing "
        "refreshes; exactly one is required so the last transition is read back"
    )
    assert out["calls_after_trailing"] == 2, (
        "the trailing refresh scheduled another refresh -- unbounded chain"
    )
    assert [p.split()[-1] for p in out["painted"]] == ["3", "4"], out
    assert out["calls_after_idle_call"] == 3, (
        "a non-overlapping call was swallowed; the badge would stop updating"
    )
    assert out["recovered_after_rejection"] is True, (
        "a failed count left the single-flight guard set -- the badge would "
        "never update again for the session"
    )


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_badge_uses_the_count_endpoint_not_the_metrics_endpoint():
    """Source-shape guard: the cheap endpoint must be the one on the badge path.

    Behavioural tests above stub the bridge, so they cannot notice the badge
    being rewired back to `list_running_agents`. This can. Comments are
    stripped first -- the function's own comment NAMES the expensive endpoint
    to say why it is not used, and a check that reads prose would be satisfied
    by the wrong code and broken by the right explanation.
    """
    src = APP_JS.read_text(encoding="utf-8")
    fn = _extract("pollAgentsBadge", src)
    code = "\n".join(
        line for line in fn.splitlines() if not line.strip().startswith("//")
    )
    assert "running_agent_count()" in code
    assert "list_running_agents" not in code
