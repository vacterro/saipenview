"""T-167: stdin framing and capability honesty.

Two defects closed here:

1. The frontend sent `text + "\\n"` and the backend wrote `text + "\\n"` --
   two newlines on the wire for one intended line. The backend is the single
   framing owner now: it strips trailing CR/LF and adds exactly one `\\n`.
2. Every engine declared `supports_stdin: True` on assumption. The honest
   matrix is False for all of them -- each launches with a one-shot headless
   flag (`codex exec`, `gemini --prompt`, `opencode run`, `agy -p`, ...) and
   there is no live evidence any of them reads later stdin. Send is offered
   only after such proof exists.
"""

from __future__ import annotations

import sys
import time

import pytest

from saipenview.engines import list_engines
from saipenview.engines.base import AgentEngine
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore

_READ_STDIN_SCRIPT = (
    "import sys\n"
    "for line in sys.stdin:\n"
    "    print('GOT:' + line.replace('\\n', '<NL>').replace('\\r', '<CR>'), flush=True)\n"
)


class _StdinEngine(AgentEngine):
    """Test-only: really reads stdin, so the framing can be verified end to end."""

    @property
    def name(self) -> str:
        return "stdin-test"

    @property
    def display_name(self) -> str:
        return "Stdin Test"

    def detect(self) -> bool:
        return True

    def build_command(self, project_root, instruction, *, extra_args=None):
        return [sys.executable, "-c", _READ_STDIN_SCRIPT]

    @property
    def supports_stdin(self) -> bool:
        # T-167: deliberately True -- this is the test probe that proves the
        # capability, the exact evidence real engines must produce first.
        return True


def _wait_for(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class TestFraming:
    @pytest.fixture
    def pm(self, tmp_path):
        pm = ProcessManager()
        pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
        yield pm
        pm.stop_all()

    def _launch_reader(self, pm, root):
        assert pm.launch(_StdinEngine(), root, "go")["ok"] is True
        assert _wait_for(lambda: pm.get_status(root)["status"] == "running")

    def _lines(self, pm, root):
        return pm.get_output(root)["lines"]

    def test_plain_text_gets_one_newline(self, pm, tmp_path):
        root = str(tmp_path)
        self._launch_reader(pm, root)
        assert pm.send_input(root, "hello")["ok"] is True
        assert _wait_for(
            lambda: any("GOT:hello<NL>" in line for line in self._lines(pm, root))
        )
        pm.stop_all()

    def test_text_with_newline_gets_one_newline(self, pm, tmp_path):
        root = str(tmp_path)
        self._launch_reader(pm, root)
        assert pm.send_input(root, "hello\n")["ok"] is True
        assert _wait_for(
            lambda: any("GOT:hello<NL>" in line for line in self._lines(pm, root))
        )
        pm.stop_all()

    def test_text_with_crlf_gets_one_lf(self, pm, tmp_path):
        root = str(tmp_path)
        self._launch_reader(pm, root)
        assert pm.send_input(root, "hello\r\n")["ok"] is True
        assert _wait_for(
            lambda: any("GOT:hello<NL>" in line for line in self._lines(pm, root))
        )
        pm.stop_all()

    def test_multiline_keeps_internal_newlines_plus_one_final(self, pm, tmp_path):
        root = str(tmp_path)
        self._launch_reader(pm, root)
        assert pm.send_input(root, "a\nb\n")["ok"] is True
        assert _wait_for(
            lambda: (
                any("GOT:a<NL>" in line for line in self._lines(pm, root))
                and any("GOT:b<NL>" in line for line in self._lines(pm, root))
            )
        )
        pm.stop_all()

    def test_empty_input_rejected(self, pm, tmp_path):
        root = str(tmp_path)
        self._launch_reader(pm, root)
        res = pm.send_input(root, "")
        assert res["ok"] is False
        assert "empty" in res["error"]

    def test_whitespace_only_input_rejected(self, pm, tmp_path):
        root = str(tmp_path)
        self._launch_reader(pm, root)
        res = pm.send_input(root, "   \n")
        assert res["ok"] is False
        assert "empty" in res["error"]


class TestCapabilityMatrix:
    def test_every_engine_claims_stdin_only_with_evidence(self):
        """All shipped engines launch one-shot headless; none has proven it
        reads later stdin, so none may offer Send (T-167)."""
        engines = dict(list_engines())
        assert engines, "engine registry is empty"
        one_shot = {
            "claude-code",
            "aider",
            "cline",
            "goose",
            "agy",
            "codex",
            "gemini",
            "opencode",
            "generic-cli",
        }
        for name, engine in engines.items():
            assert engine.supports_stdin is False, (
                f"{name} claims supports_stdin without evidence -- "
                "a one-shot build_command is not proof the process reads later stdin"
            )
        assert set(engines) == one_shot
