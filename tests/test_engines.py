"""The engine layer is the whole point of an agent-agnostic shell, and it had
no tests at all -- which is how `gemini prompt <instruction>` shipped.

Gemini CLI has no `prompt` subcommand, so that spelling fell through to the
default `gemini [query..]` positional and opened an INTERACTIVE session whose
query started with the literal word "prompt". A subprocess pipe never answers
it, so the launch just hung.

These tests cannot run the real CLIs (most are not installed on any given
machine), so they pin the two things that are checkable without one: the
command SHAPE each adapter builds, and the invariants that hold across every
adapter. The commands themselves were verified against each CLI's own --help
when it was present -- see the per-adapter comments.
"""

from __future__ import annotations

import pytest

from saipenview.engines import get_engine, list_engines
from saipenview.engines.base import AgentEngine

ROOT = "/tmp/project"
INSTR = "saipen continue"

# The exact argv each adapter must build. Verified against `--help` for the
# CLIs installed on the development machine (gemini, codex, aider, opencode);
# the rest are the documented invocations for their tool.
EXPECTED = {
    "claude-code": ["claude", "--print", INSTR, "--output-format", "stream-json", "--verbose"],
    "aider": ["aider", "-m", INSTR, "--yes-always"],
    "cline": ["cline", "-y", INSTR],
    "goose": ["goose", "run", "-t", INSTR],
    "agy": ["agy", "-p", INSTR, "--mode=accept-edits"],
    "codex": ["codex", "exec", INSTR],
    "gemini": ["gemini", "--prompt", INSTR, "--yolo"],
    "opencode": ["opencode", "run", INSTR],
}


class TestBuiltCommands:
    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_command_matches_the_verified_invocation(self, name):
        engine = get_engine(name)
        assert engine is not None, f"{name} is not registered"
        assert engine.build_command(ROOT, INSTR) == EXPECTED[name]

    def test_gemini_does_not_use_a_subcommand_that_does_not_exist(self):
        # The specific regression: `prompt` as argv[1] is not a subcommand, it
        # is the first word of an interactive query.
        cmd = get_engine("gemini").build_command(ROOT, INSTR)
        assert cmd[1] != "prompt"
        assert "--prompt" in cmd or "-p" in cmd

    def test_claude_code_passes_no_project_dir_flag(self):
        # Never a Claude Code flag. The project directory is the cwd, which
        # runtime.py sets from project_root.
        assert "--project-dir" not in get_engine("claude-code").build_command(ROOT, INSTR)

    def test_opencode_is_registered(self):
        # It was installed and already owned tickets on this project's board
        # while being the one agent SAIPENVIEW could not launch.
        assert get_engine("opencode") is not None


class TestRegistryInvariants:
    def test_every_registered_engine_builds_a_non_empty_command(self):
        for name, engine in list_engines():
            cmd = engine.build_command(ROOT, INSTR)
            assert cmd and all(isinstance(a, str) for a in cmd), name

    def test_no_adapter_leaves_the_instruction_out(self):
        for name, engine in list_engines():
            if name == "generic-cli":
                continue  # splits the instruction into argv itself
            assert INSTR in engine.build_command(ROOT, INSTR), name

    def test_extra_args_are_appended_not_replaced(self):
        for name, engine in list_engines():
            base = engine.build_command(ROOT, INSTR)
            with_extra = engine.build_command(ROOT, INSTR, extra_args=["--zzz"])
            assert with_extra == base + ["--zzz"], name

    def test_names_are_unique_and_match_the_registry_key(self):
        pairs = list_engines()
        assert len({n for n, _ in pairs}) == len(pairs)
        for name, engine in pairs:
            assert engine.name == name

    def test_every_engine_declares_a_display_name(self):
        for name, engine in list_engines():
            assert engine.display_name.strip(), name

    def test_detect_returns_a_bool_and_never_raises(self):
        for name, engine in list_engines():
            assert isinstance(engine.detect(), bool), name

    def test_every_engine_is_an_agent_engine(self):
        for _name, engine in list_engines():
            assert isinstance(engine, AgentEngine)


class TestEnvironmentGrants:
    def test_gemini_trusts_the_workspace(self):
        # Without it Gemini downgrades --yolo and refuses: "not running in a
        # trusted directory". Reproduced live in an untrusted scratch dir.
        env = get_engine("gemini").default_env
        assert env and env.get("GEMINI_CLI_TRUST_WORKSPACE") == "true"

    def test_default_env_is_a_string_map_or_none(self):
        for name, engine in list_engines():
            env = engine.default_env
            if env is None:
                continue
            assert all(
                isinstance(k, str) and isinstance(v, str) for k, v in env.items()
            ), name
