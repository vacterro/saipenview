"""Aider CLI engine adapter."""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class AiderEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "aider"

    @property
    def display_name(self) -> str:
        return "Aider"

    def detect(self) -> bool:
        return shutil.which("aider") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        cmd = ["aider", "-m", instruction, "--yes"]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        return True
