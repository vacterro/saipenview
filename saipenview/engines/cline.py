"""Cline CLI engine adapter."""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class ClineEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "cline"

    @property
    def display_name(self) -> str:
        return "Cline"

    def detect(self) -> bool:
        return shutil.which("cline") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        cmd = ["cline", "-y", instruction]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        return True
