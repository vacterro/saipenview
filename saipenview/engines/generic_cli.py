"""Generic CLI engine adapter.

Runs any user-specified command as an agent process.  No structured
event parsing -- stdout/stderr lines are passed through as-is.
This is the universal fallback for agent tools that don't have a
dedicated adapter.
"""

from __future__ import annotations

from saipenview.engines.base import AgentEngine, AgentEvent


class GenericCLIEngine(AgentEngine):
    """Run an arbitrary CLI command as an agent process.

    The ``instruction`` parameter to build_command() is treated as
    the full shell command to execute.  The project_root becomes the
    working directory (handled by runtime.py, not encoded in argv).
    """

    @property
    def name(self) -> str:
        return "generic-cli"

    @property
    def display_name(self) -> str:
        return "Generic CLI"

    def detect(self) -> bool:
        # Always available -- it's just a subprocess wrapper
        return True

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        # instruction IS the command -- split on whitespace for Popen
        # For complex commands with quotes/pipes, user should use
        # shell syntax and we'll wrap in cmd.exe /c
        parts = instruction.split()
        if extra_args:
            parts.extend(extra_args)
        return parts

    @property
    def supports_stdin(self) -> bool:
        return True

    def parse_event(self, line: str) -> AgentEvent | None:
        """No structured parsing -- everything is raw output."""
        stripped = line.strip()
        if not stripped:
            return None
        return AgentEvent(kind="output", text=stripped)
