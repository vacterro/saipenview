"""Goose CLI engine adapter."""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class GooseEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "goose"

    @property
    def display_name(self) -> str:
        return "Goose"

    def detect(self) -> bool:
        return shutil.which("goose") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        cmd = ["goose", "run", "-t", instruction]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        # T-167: build_command uses goose run -t <instr> (one-shot run); no live evidence the process reads later stdin
        return False
