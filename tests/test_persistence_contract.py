"""T-172: the .saipen persistence contract holds.

The project is INTENTIONALLY local-only for .saipen/ by written contract
(docs/saipen-persistence.md). These tests pin the mechanical half: the
ignore rule matches the contract, nothing under .saipen is tracked, and no
machine-local absolute path reaches the repository.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)
class TestPersistenceContract:
    def test_board_is_ignored_by_decision(self):
        """check-ignore must match the local-only contract (it IS ignored)."""
        r = _git("check-ignore", ".saipen/BOARD.md")
        assert r.returncode == 0, "the contract says .saipen/ is local-only"
        assert ".saipen/BOARD.md" in r.stdout

    def test_state_is_ignored(self):
        r = _git("check-ignore", ".saipen/STATE.md")
        assert r.returncode == 0

    def test_no_saipen_files_tracked(self):
        r = _git("ls-files")
        tracked = r.stdout.splitlines()
        # Two deliberate tracked exceptions: the own-`.saipen` CI snapshot
        # (repair mission P1, CI validates a sanitized mechanically-generated
        # fixture because the live memory is gitignored) and the project
        # lineage carrier `.saipen/IDENTITY.md` (CORE-004 -- the canonical
        # validator FAILs when the lineage identity is untracked, and the
        # IDENTITY carrier carries no machine-local path). Everything else
        # under .saipen/ must stay untracked.
        _IDENTITY_EXCEPTION = ".saipen/IDENTITY.md"
        banned = [
            p
            for p in tracked
            if ("/.saipen/" in p or p.startswith(".saipen"))
            and not p.startswith("tests/fixtures/own_saipen_snapshot/")
            and p != _IDENTITY_EXCEPTION
        ]
        assert not banned, "canonical memory must not be tracked raw (machine paths)"
        snapshot = [
            p for p in tracked if p.startswith("tests/fixtures/own_saipen_snapshot/")
        ]
        assert snapshot, "the tracked own-.saipen CI snapshot is missing"

    def test_no_absolute_local_paths_in_tracked_content(self):
        # The ban is on MACHINE STATE, not prose: docstrings may say
        # `C:\Program Files` for illustration. Machine state lives in
        # saipenview/_data/ (config.json, cache.json) and in .saipen/ -- both
        # must be entirely absent from the tracked tree.
        r = _git("ls-files")
        tracked = r.stdout.splitlines()
        assert not [p for p in tracked if "saipenview/_data/" in p], (
            "runtime config/cache is tracked -- machine paths would leak"
        )
        data_files = [
            p
            for p in tracked
            if p.lower().endswith(".json") and not p.startswith("tests/")
        ]
        bad = []
        for rel in data_files:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            for match in re.findall(r"(?<![A-Za-z0-9])[A-Za-z]:\\", text):
                bad.append(f"{rel}: {match}")
        assert not bad, (
            "tracked JSON data carries absolute local drive paths:\n"
            + "\n".join(bad[:5])
        )

    def test_the_contract_document_exists_and_is_tracked(self):
        doc = ROOT / "docs" / "saipen-persistence.md"
        assert doc.is_file(), "the persistence contract document is missing"
        r = _git("ls-files", "--error-unmatch", "docs/saipen-persistence.md")
        assert r.returncode == 0, "the contract document itself must travel in git"
