"""Gemini CLI engine adapter."""

from __future__ import annotations

import shutil

from saipenview.engines.base import AgentEngine


class GeminiEngine(AgentEngine):
    @property
    def name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Gemini"

    def detect(self) -> bool:
        return shutil.which("gemini") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        # NOT `gemini prompt <instruction>`. Gemini CLI has no `prompt`
        # subcommand -- `gemini --help` lists mcp/extensions/skills/hooks/gemma
        # and a default `gemini [query..]` positional. So that spelling fell
        # through to the default and started an INTERACTIVE session whose query
        # began with the literal word "prompt", then sat waiting for a human
        # that a subprocess pipe never provides.
        #
        # `-p/--prompt` is the documented headless flag. `--yolo` auto-approves
        # tool calls, matching what every other adapter here already does
        # (aider --yes-always, cline -y, agy --mode=accept-edits): an agent
        # launched from this panel has no terminal to approve anything from.
        cmd = ["gemini", "--prompt", instruction, "--yolo"]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        # T-167: build_command uses gemini --prompt <instr> --yolo (one-shot headless); no live evidence the process reads later stdin
        return False

    @property
    def default_env(self) -> dict[str, str] | None:
        # Without this, `--yolo` is silently downgraded and the run dies with
        # "Gemini CLI is not running in a trusted directory" -- Gemini's own
        # message names this variable as the answer for headless and automated
        # environments. Reproduced live in an untrusted scratch directory:
        # exit 0 with no work done before, "OK" after.
        #
        # It does auto-trust the folder, which is a real grant. The gate it
        # replaces is a human confirming they meant this directory, and that
        # confirmation is what pressing Launch on a project the user picked in
        # this UI already is. Same reasoning as --yolo above; if either stops
        # being acceptable, both should move behind a setting together.
        return {"GEMINI_CLI_TRUST_WORKSPACE": "true"}
