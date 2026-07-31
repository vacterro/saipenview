"""Claude Code CLI engine adapter.

Wraps Anthropic's ``claude`` CLI tool.  Supports both one-shot
(``--print``) and interactive (stdin-piped) modes.
"""

from __future__ import annotations

import json
import shutil

from saipenview.engines.base import AgentEngine, AgentEvent


class ClaudeCodeEngine(AgentEngine):
    """Adapter for the ``claude`` CLI (Anthropic Claude Code)."""

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def detect(self) -> bool:
        return shutil.which("claude") is not None

    def build_command(
        self,
        project_root: str,
        instruction: str,
        *,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        cmd = [
            "claude",
            "--project-dir",
            project_root,
            "--print",
            instruction,
            "--output-format",
            "stream-json",
        ]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @property
    def supports_stdin(self) -> bool:
        return False

    @property
    def default_env(self) -> dict[str, str] | None:
        # Disable interactive prompts, force non-interactive output
        return {"CLAUDE_CODE_ENTRYPOINT": "saipenview"}

    def parse_event(self, line: str) -> AgentEvent | None:
        """Parse Claude Code's stream-json output format."""
        line = line.strip()
        if not line:
            return None

        # Try to parse as JSON (stream-json format)
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Plain text line — return as raw output
            return AgentEvent(kind="output", text=line)

        msg_type = data.get("type", "")

        if msg_type == "assistant":
            # Assistant text response
            content = data.get("content", "")
            if isinstance(content, list):
                # Content blocks: extract text
                texts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = "\n".join(texts)
            return AgentEvent(kind="output", text=str(content))

        if msg_type == "tool_use":
            tool_name = data.get("name", "unknown")
            tool_input = data.get("input", {})
            return AgentEvent(
                kind="tool_call",
                text=f"[{tool_name}] {json.dumps(tool_input, ensure_ascii=False)[:200]}",
                metadata={"tool": tool_name, "input": tool_input},
            )

        if msg_type == "tool_result":
            return AgentEvent(
                kind="info",
                text=f"[result] {str(data.get('content', ''))[:200]}",
                metadata=data,
            )

        if msg_type == "error":
            return AgentEvent(
                kind="error",
                text=data.get("message", str(data)),
                metadata=data,
            )

        # Unknown type — pass through as raw
        return AgentEvent(kind="output", text=line)
