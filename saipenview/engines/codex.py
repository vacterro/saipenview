"""OpenAI Codex CLI engine adapter."""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class CodexEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "OpenAI Codex"

    def detect(self) -> bool:
        return shutil.which("codex") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        cmd = ["codex", "exec", instruction]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        # T-167: build_command uses codex exec <instr> (one-shot headless); no live evidence the process reads later stdin
        return False
