"""OpenCode CLI engine adapter.

Added because opencode was already doing work in this project -- it owns
tickets on SAIPENVIEW's own BOARD -- while being the one installed agent
SAIPENVIEW could not launch.
"""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class OpenCodeEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "opencode"

    @property
    def display_name(self) -> str:
        return "OpenCode"

    def detect(self) -> bool:
        return shutil.which("opencode") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        # `opencode run <message>` is the headless form; the bare `opencode`
        # default positional starts the TUI, which a subprocess pipe cannot
        # drive. Checked against `opencode run --help`.
        cmd = ["opencode", "run", instruction]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        return True
