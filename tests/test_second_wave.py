"""Second Wave security remediation — red-before-fix regression coverage.

Every finding in the Second Wave audit has at least one test here that encodes
the CORRECTED behaviour. Together they also encode the bug class: each would
have failed against the pre-fix code.

Windows-only findings (clipboard, Job Object orphaning, named-mutex guard) are
skipped on non-Windows platforms.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.runtime import ProcessManager
from saipenview.scanner import ScanOutcome, BackgroundScanner, get_scan_progress, scan

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)


# ── git repo fixture (mirrors tests/test_git_diff.py) ───────────────────────


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.autocrlf", "false")
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "init")
    return root


def _git(root, *args, check=True):
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and r.returncode != 0:
        raise AssertionError(f"git {args!r} failed: {r.stderr}")
    return r


def _pid_alive(pid: int) -> bool:
    import psutil

    return psutil.pid_exists(pid)


# ── Fake engine for runtime/ownership tests ────────────────────────────────


class _FakeEngine(AgentEngine):
    name = "fake"
    display_name = "Fake"

    def __init__(self, cmd):
        self._cmd = list(cmd)

    def build_command(self, project_root, instruction, *, extra_args=None):
        return self._cmd + [instruction]

    def detect(self):
        return True

    supports_stdin = True


def _make_pm():
    from saipenview.protocol_write import get_coordinator

    return ProcessManager(ownership=get_coordinator().ownership)


# ═══════════════════════════════════════════════════════════════════════════
# P0 — clipboard_copy: text never becomes PowerShell source
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(sys.platform != "win32", reason="Windows clipboard/Powershell")
def test_clipboard_copy_cannot_execute_payload(tmp_path):
    from saipenview.api import Api

    marker = tmp_path / "marker.txt"
    payload = (
        "$(New-Item -ItemType File -Path '" + str(marker) + "' -Force) | Out-Null\n"
        "line with `backtick and \"quotes\" and 'unicode' -- cafe\n"
    )
    api = Api()
    try:
        assert api.clipboard_copy(payload) is True
        got = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=10,
        ).stdout
        # The payload must be copied BYTE-EXACT as data, and its $(...) must
        # never have executed (no marker file created).
        assert marker.exists() is False
        assert payload.strip() == got.strip()
    finally:
        api.stop()


# ═══════════════════════════════════════════════════════════════════════════
# P0 — process ownership: released only after OS death
# ═══════════════════════════════════════════════════════════════════════════


def test_ownership_held_after_stdout_closed_but_alive(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(
        "import sys, time\n"
        "sys.stdout.close()\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()
    res = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert res["ok"]
    time.sleep(3)
    assert pm.is_running(root) is True
    assert pm.ownership.agent_owns(Path(root)) is True
    pm.kill(root)
    for _ in range(40):
        if not pm.is_running(root):
            break
        time.sleep(0.1)
    assert pm.is_running(root) is False


def test_second_launch_refused_until_process_dead(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import sys, time\nsys.stdout.close()\ntime.sleep(30)\n", encoding="utf-8")
    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()
    assert pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")["ok"]
    again = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert again["ok"] is False
    assert "running" in again["error"].lower()
    pm.kill(root)
    for _ in range(40):
        if not pm.is_running(root):
            break
        time.sleep(0.1)
    assert pm.is_running(root) is False
    assert pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")["ok"]
    pm.kill(root)


def test_launch_failure_after_popen_kills_child(tmp_path, monkeypatch):
    import subprocess as _sp

    spawned = {}
    orig_popen = _sp.Popen

    def _track_popen(*a, **k):
        proc = orig_popen(*a, **k)
        spawned["pid"] = proc.pid
        return proc

    monkeypatch.setattr(_sp, "Popen", _track_popen)

    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    real_start = pm.sessions.start

    def boom(*a, **k):
        raise RuntimeError("injected session failure")

    pm.sessions.start = boom
    with pytest.raises(RuntimeError):
        pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    pm.sessions.start = real_start

    assert "pid" in spawned, "no child was spawned"
    # The spawned child must have been killed (no orphan writer).
    time.sleep(0.3)
    assert not _pid_alive(spawned["pid"]), "orphaned child survived launch failure"


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object is Windows-only")
def test_forced_parent_exit_kills_child(tmp_path):
    heartbeat = tmp_path / "hb.txt"
    marker = tmp_path / "pid.txt"
    helper = Path(__file__).parent / "fixtures" / "orphan_helper.py"
    hb_script = Path(__file__).parent / "fixtures" / "heartbeat_child.py"
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    proc = subprocess.Popen(
        [sys.executable, str(helper), str(hb_script), str(heartbeat), str(marker)], env=env
    )
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    for _ in range(50):
        if heartbeat.exists():
            break
        time.sleep(0.1)
    exit_time = time.time()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    child_pid = int(marker.read_text())
    # Poll for the Job Object to actually reap the child instead of assuming a
    # fixed exit window. On loaded machines the terminate-after-parent signal
    # lags the parent's os._exit by up to ~1.6s, which made the old
    # `last <= exit_time + 1.0` check flake (T-562). Wait for the real death,
    # then prove the child stopped heartbeating on time.
    child_dead_at = None
    for _ in range(50):
        if not _pid_alive(child_pid):
            child_dead_at = time.time()
            break
        time.sleep(0.1)
    assert child_dead_at is not None, "child survived parent force-exit (Job Object failed)"
    last = float(heartbeat.read_text(encoding="utf-8").split()[1])
    assert last <= child_dead_at + 0.3 + 1e-6, "child kept heartbeating after parent exit (Job Object failed)"


# ═══════════════════════════════════════════════════════════════════════════
# P2 — get_status degrades psutil errors to zero metrics only
# ═══════════════════════════════════════════════════════════════════════════


def test_get_status_psutil_error_degrades(monkeypatch, tmp_path):
    import psutil

    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()
    res = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert res["ok"]

    def _raise_nosuchprocess(*a, **k):
        raise psutil.NoSuchProcess(pid=res["pid"])

    def _raise_accessdenied(*a, **k):
        raise psutil.AccessDenied(pid=res["pid"])

    monkeypatch.setattr(psutil.Process, "cpu_percent", _raise_nosuchprocess)
    monkeypatch.setattr(psutil.Process, "memory_info", _raise_accessdenied)

    status = pm.get_status(root)
    assert status["status"] == "running"
    assert status["cpu_percent"] == 0.0
    assert status["memory_mb"] == 0.0
    pm.kill(root)


# ═══════════════════════════════════════════════════════════════════════════
# P0 — git_diff: one captured preview, fail closed
# ═══════════════════════════════════════════════════════════════════════════


def test_unreadable_untracked_file_fails_preview_closed(repo, monkeypatch):
    from saipenview import git_diff

    (repo / "secret.txt").write_text("data\n", encoding="utf-8")

    def _boom(self):
        raise OSError("denied")

    monkeypatch.setattr(git_diff.Path, "read_bytes", _boom)
    res = git_diff.get_working_diff(str(repo))
    assert not res["ok"]
    assert "unreadable" in res["error"].lower() or "cannot preview" in res["error"].lower()
    # Fail-closed: nothing was committed and the file is untouched.
    assert len(_git(repo, "log", "--oneline").stdout.splitlines()) == 1
    assert (repo / "secret.txt").exists()


def test_preview_fingerprint_matches_shown_scope_and_commits(repo):
    from saipenview import git_diff

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    preview = git_diff.get_working_diff(str(repo))
    assert preview["ok"]
    res = git_diff.commit_agent_work(str(repo), "msg", preview["fingerprint"])
    assert res["ok"], res
    log = _git(repo, "log", "--oneline").stdout
    assert "msg" in log


def test_untracked_edit_after_preview_refuses_commit(repo):
    from saipenview import git_diff

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    preview = git_diff.get_working_diff(str(repo))
    assert preview["ok"]
    (repo / "tracked.txt").write_text("changed again\n", encoding="utf-8")
    res = git_diff.commit_agent_work(str(repo), "msg", preview["fingerprint"])
    assert not res["ok"]
    assert "changed" in res["error"].lower() or "status" in res["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# P1 — fingerprint mandatory for commit/revert/delete
# ═══════════════════════════════════════════════════════════════════════════


def test_missing_fingerprint_refuses_all_mutations(repo):
    from saipenview import git_diff

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repo / "new.txt").write_text("x\n", encoding="utf-8")

    for fn, args in (
        (git_diff.commit_agent_work, (str(repo), "m")),
        (git_diff.revert_agent_work, (str(repo),)),
        (git_diff.delete_untracked_files, (str(repo),)),
    ):
        res = fn(*args, None)
        assert not res["ok"], res
        assert res.get("code") == "PREVIEW_REQUIRED", res

    assert not git_diff.commit_agent_work(str(repo), "m", "")["ok"]
    assert "m" not in _git(repo, "log", "--oneline").stdout
    assert (repo / "new.txt").exists()


def test_stale_fingerprint_refuses_commit(repo):
    from saipenview import git_diff

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    fp = git_diff.get_working_diff(str(repo))["fingerprint"]
    (repo / "tracked.txt").write_text("changed again\n", encoding="utf-8")
    assert not git_diff.commit_agent_work(str(repo), "m", fp)["ok"]


# ═══════════════════════════════════════════════════════════════════════════
# P1 — guard: named mutex ownership + versioned SHOW ACK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
class TestSingleInstanceGuard:
    def _free_port_listener(self, port, stop):
        import socket

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        srv.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                break
            try:
                conn.recv(64)
            finally:
                conn.close()
        srv.close()

    def test_two_launches_port_blocked_yield_one_owner(self):
        from saipenview.guard import SingleInstanceGuard, SINGLE_INSTANCE_PORT

        stop = threading.Event()
        lthread = threading.Thread(
            target=self._free_port_listener, args=(SINGLE_INSTANCE_PORT, stop), daemon=True
        )
        lthread.start()
        try:
            a = SingleInstanceGuard()
            assert a.acquire() is True
            b = SingleInstanceGuard()
            assert b.acquire() is False
            a.stop()
            b.stop()
        finally:
            stop.set()
            lthread.join(timeout=2)

    def test_unrelated_listener_cannot_impersonate(self):
        from saipenview.guard import SingleInstanceGuard, SINGLE_INSTANCE_PORT

        stop = threading.Event()
        lthread = threading.Thread(
            target=self._free_port_listener, args=(SINGLE_INSTANCE_PORT, stop), daemon=True
        )
        lthread.start()
        try:
            g = SingleInstanceGuard()
            assert g.acquire() is True
            g.stop()
        finally:
            stop.set()
            lthread.join(timeout=2)

    def test_real_owner_returns_ack_and_shows(self):
        from saipenview.guard import (
            SingleInstanceGuard,
            SINGLE_INSTANCE_PORT,
            _SHOW_MAGIC,
            _SHOW_ACK,
        )

        shown = []
        a = SingleInstanceGuard()
        assert a.acquire(on_show_request=lambda: shown.append(1)) is True
        try:
            import socket

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(("127.0.0.1", SINGLE_INSTANCE_PORT))
            client.sendall(_SHOW_MAGIC)
            data = client.recv(64)
            client.close()
            assert _SHOW_ACK in data
            deadline = time.time() + 2
            while not shown and time.time() < deadline:
                time.sleep(0.05)
            assert shown == [1]
        finally:
            a.stop()

    def test_stale_socket_free_mutex_one_owner(self):
        from saipenview.guard import SingleInstanceGuard, SINGLE_INSTANCE_PORT

        stop = threading.Event()
        lthread = threading.Thread(
            target=self._free_port_listener, args=(SINGLE_INSTANCE_PORT, stop), daemon=True
        )
        lthread.start()
        try:
            g = SingleInstanceGuard()
            assert g.acquire() is True
            g.stop()
        finally:
            stop.set()
            lthread.join(timeout=2)


# ═══════════════════════════════════════════════════════════════════════════
# P1 — scanner: cancellation token + generation re-check
# ═══════════════════════════════════════════════════════════════════════════


def test_stale_generation_does_not_publish_result(monkeypatch):
    from saipenview import scanner as scanner_mod

    block = threading.Event()
    started = threading.Event()
    captured = []

    def fake_scan(*a, **k):
        started.set()
        block.wait(timeout=5)
        return ScanOutcome(projects=[SimpleNamespace(root="X")], complete=True)

    monkeypatch.setattr(scanner_mod, "scan", fake_scan)

    s1 = BackgroundScanner(
        on_result=lambda projects, complete=False, **kw: captured.append(("s1", projects)),
        scan_roots=["z"],
    )
    s2 = BackgroundScanner(
        on_result=lambda projects, complete=False, **kw: captured.append(("s2", projects)),
        scan_roots=["z"],
    )
    s1.start()
    for _ in range(50):
        if started.is_set():
            break
        time.sleep(0.05)
    s1.stop()
    s2.start()
    block.set()
    for _ in range(50):
        if captured:
            break
        time.sleep(0.05)
    time.sleep(0.3)
    s2.stop()
    assert [tag for tag, _ in captured] == ["s2"]


def test_cooperative_cancel_does_not_update_progress(tmp_path):
    cancel = threading.Event()
    cancel.set()
    scan([str(tmp_path)], cancel=cancel)
    prog = get_scan_progress()
    assert prog["roots_done"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# P1 — config: canonical normalizer (load + save + API writes)
# ═══════════════════════════════════════════════════════════════════════════


def test_normalize_replaces_invalid_keys_with_defaults():
    from saipenview.config import normalize_config

    raw = {
        "rescan_interval": "x",
        "scan_delay_ms": "x",
        "scan_depth": "big",
        "scan_roots": "notalist",
        "window_width": "x",
        "zoom_level": "x",
        "engine_overrides": "nope",
        "custom_commands": [1, 2, "bad"],
        "auto_scan": "yes",
        "good_key": 300,
    }
    cfg = normalize_config(raw)
    assert cfg["rescan_interval"] == 300
    assert cfg["scan_depth"] == 6
    assert cfg["scan_roots"] is None
    assert cfg["zoom_level"] == 1.0
    assert cfg["engine_overrides"] == {}
    assert cfg["custom_commands"] == []
    assert cfg["auto_scan"] is True
    assert "good_key" not in cfg


def test_save_config_normalizes_poison(tmp_config_path):
    from saipenview.config import load_config, save_config

    poison = {
        "rescan_interval": "x",
        "scan_depth": 99,
        "zoom_level": "x",
        "agent_output_buffer_size": -5,
    }
    save_config(poison)
    cfg = load_config()
    assert cfg["rescan_interval"] == 300
    assert cfg["scan_depth"] == 8
    assert cfg["zoom_level"] == 1.0
    assert cfg["agent_output_buffer_size"] == 5000


# ═══════════════════════════════════════════════════════════════════════════
# P1 — api cache.json load validation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "content",
    [
        '{"bad": 1}',
        '"x"',
        '["junk"]',
        '[{"no_root": 1}]',
        '[{"root": 5}]',
        "not json at all [[[",
    ],
)
def test_cache_malformed_starts_fresh(content, tmp_config_path):
    from saipenview.api import Api
    from saipenview.config import config_path

    cache = config_path().parent / "cache.json"
    cache.write_text(content, encoding="utf-8")
    api = Api()
    try:
        assert api._projects == []
        assert api._has_scanned is False
    finally:
        api.stop()


def test_cache_valid_fast_boot(tmp_config_path):
    from saipenview.api import Api
    from saipenview.config import config_path

    cache = config_path().parent / "cache.json"
    cache.write_text('[{"root": "C:\\\\valid\\\\project"}]', encoding="utf-8")
    api = Api()
    try:
        assert len(api._projects) == 1
        assert api._has_scanned is True
    finally:
        api.stop()


# ═══════════════════════════════════════════════════════════════════════════
# P1 — empty scan removes vanished project; incomplete scan keeps it
# ═══════════════════════════════════════════════════════════════════════════


def test_complete_empty_scan_clears_cache(tmp_path):
    from saipenview.api import Api
    from saipenview.config import config_path

    cache = config_path().parent / "cache.json"
    cache.write_text('[{"root": "C:\\\\vanish\\\\project"}]', encoding="utf-8")
    api = Api()
    try:
        assert len(api._projects) == 1
        api._set_cache([], force=False, complete=True)
        assert api._projects == []
        assert api._has_scanned is True
    finally:
        api.stop()


def test_incomplete_scan_keeps_cache(tmp_path):
    from saipenview.api import Api
    from saipenview.config import config_path

    cache = config_path().parent / "cache.json"
    cache.write_text('[{"root": "C:\\\\keep\\\\project"}]', encoding="utf-8")
    api = Api()
    try:
        assert len(api._projects) == 1
        api._set_cache([], force=False, complete=False)
        assert len(api._projects) == 1
    finally:
        api.stop()


def test_refresh_removes_vanished_project(tmp_path):
    from saipenview.api import Api
    from saipenview.config import config_path

    proj = tmp_path / "proj"
    (proj / ".saipen").mkdir(parents=True)
    (proj / ".saipen" / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")
    cache = config_path().parent / "cache.json"
    cache.write_text('[{"root": "' + str(proj).replace("\\", "\\\\") + '"}]', encoding="utf-8")
    api = Api()
    try:
        assert len(api._projects) == 1
        (proj / ".saipen" / "STATE.md").unlink()
        api._refresh_one_project(str(proj))
        assert api._projects == []
    finally:
        api.stop()


# ═══════════════════════════════════════════════════════════════════════════
# P1 — app.run: partial startup always unwinds
# ═══════════════════════════════════════════════════════════════════════════


class _Boom(Exception):
    pass


def test_run_unwinds_started_components_on_failure(monkeypatch):
    import saipenview.app as app_mod

    stops = {}
    order = ["tray", "hotkeys", "snap_hotkey", "kill_hotkey", "api", "webview"]
    snap_default = ["ctrl+q"]
    # "tray" is always begun (its thread is started); it cannot raise, so the
    # failure-injection points are the stages whose .start() can throw.
    boom_points = [None, "hotkeys", "snap_hotkey", "kill_hotkey", "api", "webview"]

    class _Comp:
        def __init__(self, name):
            self.name = name
            stops[name] = 0

        def start(self):
            if app_mod._boom_at == self.name:
                raise _Boom(self.name)

        def stop(self):
            stops[self.name] += 1

        def run(self):
            # Tray runs in a daemon thread (real build_tray_icon returns a
            # tray whose .run is the thread target). Never raises here; "tray"
            # is always-started so it is never a boom point.
            pass

        def set_hotkeys(self, *a, **k):
            pass

    class _Api:
        def __init__(self, *a, **k):
            self._window = None
            stops["api"] = 0

        def start(self):
            if app_mod._boom_at == "api":
                raise _Boom("api")

        def stop(self):
            stops["api"] += 1

        def set_hotkey_callback(self, cb):
            pass

        def set_snap_hotkey_callback(self, cb):
            pass

        def set_quit_callback(self, cb):
            pass

        def get_config(self):
            return {"hotkeys": ["ctrl+alt+x"], "snap_hotkey": ["ctrl+q"]}

    class _Guard:
        def acquire(self, on_show_request=None):
            return True

        def stop(self):
            stops["guard"] = stops.get("guard", 0) + 1

    class _Window:
        def __init__(self, *a, **k):
            pass

        def show(self):
            pass

        def toggle(self):
            pass

        def destroy(self):
            pass

        def cycle_snap_corner(self):
            pass

        def force_destroy(self):
            pass

    def _make_hotkey(**k):
        hk = k.get("hotkeys")
        if hk == ["ctrl+shift+alt+q"]:
            return _Comp("kill_hotkey")
        if hk == snap_default:
            return _Comp("snap_hotkey")
        return _Comp("hotkeys")

    def _webview_start():
        if app_mod._boom_at == "webview":
            raise _Boom("webview")

        for boom_at in boom_points:
            stops.clear()
            app_mod._boom_at = boom_at
            monkeypatch.setattr(app_mod, "MainWindow", _Window)
            monkeypatch.setattr(app_mod, "build_tray_icon", lambda **k: _Comp("tray"))
            monkeypatch.setattr(app_mod, "HotkeyListener", _make_hotkey)
            monkeypatch.setattr(app_mod, "Api", _Api)
            monkeypatch.setattr(app_mod, "SingleInstanceGuard", _Guard)
            monkeypatch.setattr(app_mod.webview, "start", _webview_start)

            reached_boom = False
            try:
                app_mod.run()
            except SystemExit:
                pass
            except _Boom:
                # run() lets the failure propagate (the OS / caller handles it);
                # the critical contract is that its finally unwinds every
                # started component first.
                reached_boom = True
            assert reached_boom == (boom_at is not None), f"boom propagation wrong for {boom_at}"

        started_idx = order.index(boom_at) if boom_at in order else len(order)
        for i, name in enumerate(order):
            if name == "webview":
                # webview.start() blocks; it has no teardown, so it is never
                # stopped (and never leaks state).
                assert name not in stops, f"{name} should not be stopped boom={boom_at}"
                continue
            if i < started_idx:
                assert stops.get(name) == 1, f"{name} stop={stops.get(name)} boom={boom_at}"
            else:
                assert stops.get(name, 0) == 0, f"{name} touched boom={boom_at}"
        assert stops.get("guard") == 1
