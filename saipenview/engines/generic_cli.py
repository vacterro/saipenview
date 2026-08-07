"""Generic CLI engine adapter.

Runs any user-specified command as an agent process.  No structured
event parsing -- stdout/stderr lines are passed through as-is.
This is the universal fallback for agent tools that don't have a
dedicated adapter.
"""

from __future__ import annotations

from saipenview.engines.base import AgentEngine, AgentEvent


class GenericCLIEngine(AgentEngine):
    """Run an arbitrary shell command as an agent process.

    The ``instruction`` parameter to build_command() is the FULL shell
    command -- quotes, pipes, ``&&`` and all -- run through
    ``cmd.exe /d /s /c`` on Windows with the project root as the working
    directory. It is a shell command, never a whitespace-split argv
    (T-168): a promise of shell syntax fulfilled with a bare ``split()``
    is how a quoted path with spaces becomes four arguments.
    """

    @property
    def name(self) -> str:
        return "generic-cli"

    @property
    def display_name(self) -> str:
        return "Generic CLI (shell command)"

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
        # Reject empty before cmd.exe sees it -- an empty shell command would
        # open and immediately close a cmd window with no error anyone sees.
        if not instruction.strip():
            raise ValueError("empty command: the generic CLI needs a command to run")
        command = instruction
        if extra_args:
            command = command + " " + " ".join(extra_args)
        # The command is a single STRING command line, not an argv list:
        # `cmd.exe /d /s /c <command>` with the working directory set by
        # runtime.py's Popen(cwd=project_root). Passing it through a Python
        # argv would re-quote it (an inner quote becomes `\"`), which cmd's
        # /c parser misreads -- that is how `if exist "C:\Program Files" ...`
        # silently stopped existing. A string command line reaches cmd raw.
        # The project root is never interpolated here (T-168).
        return f"cmd.exe /d /s /c {command}"

    @property
    def supports_stdin(self) -> bool:
        # T-167: launched as one shell command; whether it reads stdin is command-dependent, no generic evidence
        return False

    def parse_event(self, line: str) -> AgentEvent | None:
        """No structured parsing -- everything is raw output."""
        stripped = line.strip()
        if not stripped:
            return None
        return AgentEvent(kind="output", text=stripped)
