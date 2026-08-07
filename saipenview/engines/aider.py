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
        # `--yes-always` is the real flag name; `--yes` only worked by
        # argparse prefix matching, which stops working the day aider adds any
        # other option starting with "--yes".
        cmd = ["aider", "-m", instruction, "--yes-always"]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        # T-167: build_command uses ider -m <instr> --yes-always (one-shot message); no live evidence the process reads later stdin
        return False
