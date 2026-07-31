"""Agent engine adapters for SAIPENVIEW.

Each engine is a thin CLI adapter that knows how to launch one specific
agent tool (Claude Code, Aider, Codex, etc.) and optionally parse its
stdout into structured events.

Usage::

    from saipenview.engines import get_engine, list_engines

    for name, engine in list_engines():
        print(f"{name}: available={engine.detect()}")

    engine = get_engine("claude-code")
    cmd = engine.build_command("/path/to/project", "saipen continue")
"""

from __future__ import annotations

from saipenview.engines.agy import AgyEngine
from saipenview.engines.aider import AiderEngine
from saipenview.engines.base import AgentEngine, AgentEvent
from saipenview.engines.claude_code import ClaudeCodeEngine
from saipenview.engines.cline import ClineEngine
from saipenview.engines.codex import CodexEngine
from saipenview.engines.gemini import GeminiEngine
from saipenview.engines.generic_cli import GenericCLIEngine
from saipenview.engines.goose import GooseEngine

_REGISTRY: dict[str, AgentEngine] = {}


def _register_builtins() -> None:
    """Register all built-in engines once."""
    if _REGISTRY:
        return
    for engine_cls in (
        ClaudeCodeEngine,
        AiderEngine,
        ClineEngine,
        GooseEngine,
        AgyEngine,
        CodexEngine,
        GeminiEngine,
        GenericCLIEngine,
    ):
        eng = engine_cls()
        _REGISTRY[eng.name] = eng


def get_engine(name: str) -> AgentEngine | None:
    """Return engine by name, or None if unknown."""
    _register_builtins()
    return _REGISTRY.get(name)


def list_engines() -> list[tuple[str, AgentEngine]]:
    """Return all registered engines as (name, engine) pairs."""
    _register_builtins()
    return list(_REGISTRY.items())


__all__ = [
    "AgentEngine",
    "AgentEvent",
    "get_engine",
    "list_engines",
]
