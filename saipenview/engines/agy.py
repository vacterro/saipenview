"""Antigravity (agy) CLI engine adapter."""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class AgyEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "agy"

    @property
    def display_name(self) -> str:
        return "Antigravity (agy)"

    def detect(self) -> bool:
        return shutil.which("agy") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        cmd = ["agy", "-p", instruction, "--mode=accept-edits"]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        return True
