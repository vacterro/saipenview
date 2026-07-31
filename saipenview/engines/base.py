"""Base classes for agent engine adapters.

An engine knows how to launch a specific agent CLI tool and optionally
parse its stdout into structured AgentEvent objects.  Engines know
nothing about the SAIPEN protocol -- they are pure CLI wrappers.
Protocol knowledge lives in parser.py + conformance.py.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class AgentEvent:
    """A single parsed event from an agent's output stream."""

    kind: Literal["output", "tool_call", "file_edit", "test_run", "error", "info"]
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict | None = None


class AgentEngine(ABC):
    """Contract for any agent backend SAIPENVIEW can launch.

    Each subclass is a thin adapter (~50-100 lines) for one specific
    agent CLI tool.  The engine's responsibilities are narrow:

    1. Detect whether the tool is installed on this machine.
    2. Build the CLI command to launch it.
    3. Optionally parse stdout lines into structured events.

    The engine does NOT:
    - Know about SAIPEN protocol (STATE/BOARD/LOG).
    - Make HTTP API calls.
    - Manage the subprocess lifecycle (that's runtime.py's job).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short unique identifier, e.g. 'claude-code', 'aider', 'codex'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the UI, e.g. 'Claude Code'."""

    @abstractmethod
    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Return the full argv list to launch this agent.

        Args:
            project_root: Absolute path to the project directory.
            instruction: The instruction/prompt to send to the agent.
            extra_args: Optional additional CLI flags.

        Returns:
            A list suitable for subprocess.Popen(cmd, ...).
        """

    def detect(self) -> bool:
        """Return True if this engine's CLI tool is installed and reachable.

        Default implementation checks shutil.which() for the first token
        of a dummy build_command().  Override for engines that need a
        more specific check (version probe, API key validation, etc.).
        """
        try:
            cmd = self.build_command(".", "test")
            return shutil.which(cmd[0]) is not None
        except OSError:
            return False

    def parse_event(self, line: str) -> AgentEvent | None:
        """Parse one stdout/stderr line into a structured event.

        Returns None if the line is not interesting or the engine
        doesn't support structured parsing.  Default: returns None.
        """
        return None

    @property
    def supports_stdin(self) -> bool:
        """Whether this engine's process accepts stdin input mid-run.

        If True, runtime.py will keep stdin open and allow
        send_agent_input() to write to it.  Default: False.
        """
        return False

    @property
    def default_env(self) -> dict[str, str] | None:
        """Extra environment variables to set for the agent process.

        Returns None for no extra env.  Override to set API keys,
        disable color output, etc.
        """
        return None

    def to_dict(self) -> dict:
        """Serialize engine info for the frontend."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "available": self.detect(),
            "supports_stdin": self.supports_stdin,
        }
